"""Аккаунты первой волны: почта, настройки, временные пароли и родители."""

from datetime import date, timedelta
import re

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event

from .models import Invite, ParentProfile, StudentProfile, User
from .services import create_invite


PASSWORD = "korova-9-luna"


def make_student(username: str, email: str = "") -> StudentProfile:
    return StudentProfile.objects.create(
        user=User.objects.create_user(
            username, email=email, password=PASSWORD, role=User.Role.STUDENT
        )
    )


class RegistrationEmailTests(TestCase):
    def setUp(self):
        self.methodist = User.objects.create_user("email-methodist", role=User.Role.METHODIST)
        self.invite = create_invite(self.methodist)

    def payload(self, **changes):
        data = {
            "code": self.invite.code,
            "username": "email-student",
            "email": "Student@Example.COM ",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "accept_terms": True,
            "accept_privacy": True,
            "age_declaration": True,
            "parent_child_consent": True,
        }
        data.update(changes)
        return data

    def test_email_is_required_validated_and_normalized(self):
        response = self.client.post(reverse("register"), self.payload(email="не-почта"))
        self.assertIn("email", response.context["form"].errors)

        response = self.client.post(reverse("register"), self.payload())
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(User.objects.get(username="email-student").email, "student@example.com")

    def test_active_user_email_is_rejected_with_clear_message(self):
        User.objects.create_user("email-owner", email="student@example.com")
        response = self.client.post(reverse("register"), self.payload())
        self.assertContains(
            response,
            "Этот адрес электронной почты уже используется другим активным пользователем.",
        )
        self.assertIsNone(Invite.objects.get(pk=self.invite.pk).used_at)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            "reset-user", email="reset@example.com", password=PASSWORD
        )

    def tearDown(self):
        cache.clear()

    def test_reset_sends_russian_email(self):
        response = self.client.post(reverse("password_reset"), {"email": self.user.email})
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Восстановление пароля в Матемации")
        self.assertIn("Задайте новый пароль", mail.outbox[0].body)
        self.assertNotIn("Django", mail.outbox[0].body)

    def test_unknown_email_has_the_same_public_answer(self):
        known = self.client.post(reverse("password_reset"), {"email": self.user.email})
        unknown = self.client.post(
            reverse("password_reset"), {"email": "nobody@example.com"}
        )
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.url, unknown.url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(
            self.client.get(unknown.url),
            "Если аккаунт с таким адресом существует",
        )

    def test_reset_link_changes_password_and_clears_temporary_flag(self):
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])
        self.client.post(reverse("password_reset"), {"email": self.user.email})
        path = re.search(r"http://testserver(\S+)", mail.outbox[0].body).group(1)
        redirect_response = self.client.get(path)
        response = self.client.post(redirect_response.url, {
            "new_password1": "N0vyi-parol-2026!",
            "new_password2": "N0vyi-parol-2026!",
        })
        self.assertRedirects(response, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("N0vyi-parol-2026!"))
        self.assertFalse(self.user.must_change_password)

    @override_settings(PASSWORD_RESET_MAX_ATTEMPTS=2)
    def test_reset_requests_are_throttled_without_disclosing_it(self):
        url = reverse("password_reset")
        for _ in range(3):
            response = self.client.post(url, {"email": self.user.email})
            self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 2)


class TemporaryPasswordTests(TestCase):
    def setUp(self):
        self.methodist = User.objects.create_user("temporary-methodist", role=User.Role.METHODIST)
        self.student = make_student("temporary-student")
        parent_user = User.objects.create_user("temporary-parent", role=User.Role.PARENT)
        self.parent = ParentProfile.objects.create(user=parent_user)

    def test_methodist_can_issue_student_and_parent_passwords_with_audit(self):
        self.client.force_login(self.methodist)
        for kind, profile in (("students", self.student), ("parents", self.parent)):
            with self.subTest(kind=kind):
                response = self.client.post(
                    f"/api/admin/{kind}/{profile.pk}/temporary-password/"
                )
                self.assertEqual(response.status_code, 200)
                password = response.json()["temporary_password"]
                profile.user.refresh_from_db()
                self.assertTrue(profile.user.check_password(password))
                self.assertTrue(profile.user.must_change_password)
        actions = Event.objects.filter(event_type=Event.Type.ADMIN_ACTION)
        self.assertEqual(actions.filter(payload__action="account.temporary_password").count(), 2)
        self.assertTrue(all(event.payload["actor"] == self.methodist.username for event in actions))

    def test_only_methodist_or_superuser_can_issue_password(self):
        outsider = User.objects.create_user("temporary-outsider", role=User.Role.PARENT)
        self.client.force_login(outsider)
        url = f"/api/admin/students/{self.student.pk}/temporary-password/"
        self.assertEqual(self.client.post(url).status_code, 403)

        superuser = User.objects.create_superuser("temporary-root", password=PASSWORD)
        self.client.force_login(superuser)
        self.assertEqual(self.client.post(url).status_code, 200)

    def test_required_change_redirects_pages_and_rejects_api(self):
        self.student.user.must_change_password = True
        self.student.user.save(update_fields=["must_change_password"])
        self.client.force_login(self.student.user)
        self.assertRedirects(
            self.client.get(reverse("dashboard")), reverse("account_password"),
            fetch_redirect_response=False,
        )
        response = self.client.get("/api/me/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "password_change_required")

    def test_successful_change_clears_flag_and_keeps_session(self):
        self.student.user.must_change_password = True
        self.student.user.save(update_fields=["must_change_password"])
        self.client.force_login(self.student.user)
        response = self.client.post(reverse("account_password"), {
            "old_password": PASSWORD,
            "new_password1": "N0vyi-parol-2026!",
            "new_password2": "N0vyi-parol-2026!",
        })
        self.assertRedirects(response, reverse("account_settings"))
        self.student.user.refresh_from_db()
        self.assertFalse(self.student.user.must_change_password)
        self.assertEqual(self.client.get(reverse("account_settings")).status_code, 200)


class AccountSettingsTests(TestCase):
    def test_student_can_save_profile_and_study_fields(self):
        student = make_student("settings-student", "old@example.com")
        self.client.force_login(student.user)
        response = self.client.post(reverse("account_settings"), {
            "first_name": " Анна ",
            "last_name": " Иванова ",
            "email": "ANNA@EXAMPLE.COM",
            "exam_date": "2027-06-01",
            "weekly_hours": 9,
        })
        self.assertRedirects(response, reverse("account_settings"))
        student.refresh_from_db()
        student.user.refresh_from_db()
        self.assertEqual(student.user.first_name, "Анна")
        self.assertEqual(student.user.email, "anna@example.com")
        self.assertEqual(student.exam_date, date(2027, 6, 1))
        self.assertEqual(student.weekly_hours, 9)

    def test_empty_weekly_hours_is_a_form_error_without_server_error(self):
        student = make_student("settings-empty-hours", "empty-hours@example.com")
        self.client.force_login(student.user)

        response = self.client.post(reverse("account_settings"), {
            "first_name": "",
            "last_name": "",
            "email": student.user.email,
            "exam_date": "",
            "weekly_hours": "",
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("weekly_hours", response.context["form"].errors)
        student.refresh_from_db()
        self.assertEqual(student.weekly_hours, 6)

    def test_earlier_exam_date_rebuilds_only_unfinished_schedule(self):
        from apps.knowledge.tests import make_node
        from apps.planning.models import PlanChangeLog, StudyPlanItem
        from apps.planning.services import build_study_plan, get_active_plan

        student = make_student("settings-earlier-exam", "earlier@example.com")
        student.weekly_hours = 1
        student.save(update_fields=["weekly_hours"])
        for index in range(6):
            make_node(f"settings-node-{index}")
        plan = build_study_plan(student)
        done_item = plan.items.first()
        done_item.status = StudyPlanItem.Status.DONE
        done_item.completed_at = timezone.now()
        done_item.save(update_fields=["status", "completed_at"])
        new_exam_date = timezone.localdate() + timedelta(days=3)
        self.assertTrue(
            plan.items.filter(
                status=StudyPlanItem.Status.PENDING,
                due_date__gt=new_exam_date,
            ).exists()
        )
        self.client.force_login(student.user)

        response = self.client.post(reverse("account_settings"), {
            "first_name": "",
            "last_name": "",
            "email": student.user.email,
            "exam_date": new_exam_date.isoformat(),
            "weekly_hours": 1,
        })

        self.assertRedirects(response, reverse("account_settings"))
        self.assertEqual(get_active_plan(student).pk, plan.pk)
        self.assertFalse(
            plan.items.filter(
                status__in=[StudyPlanItem.Status.PENDING, StudyPlanItem.Status.IN_PROGRESS],
                due_date__gt=new_exam_date,
            ).exists()
        )
        done_item.refresh_from_db()
        self.assertEqual(done_item.status, StudyPlanItem.Status.DONE)
        change = PlanChangeLog.objects.get(plan=plan, reason=PlanChangeLog.Reason.MANUAL)
        self.assertFalse(change.is_major)

    def test_unchanged_schedule_values_do_not_rebuild_or_log(self):
        from apps.events.models import Event
        from apps.knowledge.tests import make_node
        from apps.planning.models import PlanChangeLog
        from apps.planning.services import build_study_plan, get_active_plan

        student = make_student("settings-unchanged", "unchanged@example.com")
        student.exam_date = timezone.localdate() + timedelta(days=30)
        student.weekly_hours = 8
        student.save(update_fields=["exam_date", "weekly_hours"])
        make_node("settings-unchanged-node")
        plan = build_study_plan(student)
        changes_before = PlanChangeLog.objects.filter(plan=plan).count()
        rebuilds_before = Event.objects.filter(
            event_type=Event.Type.PLAN_REBUILT, student=student
        ).count()
        self.client.force_login(student.user)

        response = self.client.post(reverse("account_settings"), {
            "first_name": "",
            "last_name": "",
            "email": student.user.email,
            "exam_date": student.exam_date.isoformat(),
            "weekly_hours": student.weekly_hours,
        })

        self.assertRedirects(response, reverse("account_settings"))
        self.assertEqual(get_active_plan(student).pk, plan.pk)
        self.assertEqual(PlanChangeLog.objects.filter(plan=plan).count(), changes_before)
        self.assertEqual(
            Event.objects.filter(
                event_type=Event.Type.PLAN_REBUILT, student=student
            ).count(),
            rebuilds_before,
        )


class ParentInviteFlowTests(TestCase):
    def setUp(self):
        self.student = make_student("invite-child", "child@example.com")
        self.other_student = make_student("invite-other", "other@example.com")

    def test_student_generates_lists_and_revokes_parent_invite(self):
        self.client.force_login(self.student.user)
        response = self.client.post(reverse("parent_invite_create"))
        self.assertRedirects(response, reverse("account_settings"))
        invite = Invite.objects.get(for_student=self.student)
        self.assertContains(self.client.get(reverse("account_settings")), invite.code)

        self.client.post(reverse("parent_invite_revoke", args=[invite.pk]))
        invite.refresh_from_db()
        self.assertLessEqual(invite.expires_at, timezone.now())
        actions = Event.objects.values_list("payload__action", flat=True)
        self.assertIn("parent_invite.create", actions)
        self.assertIn("parent_invite.revoke", actions)

    def test_new_parent_registration_links_child(self):
        invite = create_invite(
            self.student.user, role=User.Role.PARENT, for_student=self.student
        )
        response = self.client.post(reverse("register_by_invite", args=[invite.code]), {
            "code": invite.code,
            "username": "new-parent",
            "email": "parent@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "accept_terms": True,
            "accept_privacy": True,
            "parent_child_consent": True,
        })
        self.assertRedirects(response, reverse("parent_dashboard"))
        parent = User.objects.get(username="new-parent").parent_profile
        self.assertIn(self.student, parent.children.all())

    def test_existing_parent_accepts_invite(self):
        parent_user = User.objects.create_user("existing-parent", role=User.Role.PARENT)
        parent = ParentProfile.objects.create(user=parent_user)
        invite = create_invite(
            self.student.user, role=User.Role.PARENT, for_student=self.student
        )
        self.client.force_login(parent_user)
        url = reverse("register_by_invite", args=[invite.code])
        self.assertContains(self.client.get(url), "Добавить ребёнка")
        self.assertRedirects(
            self.client.post(url, {"parent_child_consent": True}),
            reverse("parent_dashboard"),
        )
        self.assertIn(self.student, parent.children.all())

    def test_foreign_student_cannot_revoke_invite(self):
        invite = create_invite(
            self.student.user, role=User.Role.PARENT, for_student=self.student
        )
        self.client.force_login(self.other_student.user)
        self.client.post(reverse("parent_invite_revoke", args=[invite.pk]))
        invite.refresh_from_db()
        self.assertGreater(invite.expires_at, timezone.now())

    def test_methodist_can_target_parent_invite_to_student(self):
        methodist = User.objects.create_user("invite-panel", role=User.Role.METHODIST)
        self.client.force_login(methodist)
        response = self.client.post("/api/admin/invites/", {
            "role": User.Role.PARENT,
            "for_student": self.student.pk,
        }, "application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["for_student"], self.student.pk)
