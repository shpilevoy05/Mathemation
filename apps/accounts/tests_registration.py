"""Страница саморегистрации: код приглашения превращается в рабочий аккаунт."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Invite, StudentGroup, User
from .services import create_invite

PASSWORD = "korova-9-luna"


class RegisterByInviteTests(TestCase):
    def setUp(self):
        self.methodist = User.objects.create_user("reg-methodist", role=User.Role.METHODIST)
        self.group = StudentGroup.objects.create(title="Поток 2028")
        self.invite = create_invite(self.methodist, group=self.group)

    def post(self, **overrides):
        payload = {
            "code": self.invite.code,
            "username": "novichok",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        payload.update(overrides)
        return self.client.post(reverse("register"), payload)

    def test_link_with_code_prefills_the_form(self):
        response = self.client.get(reverse("register_by_invite", args=[self.invite.code]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial["code"], self.invite.code)

    def test_registration_creates_student_in_group_and_logs_in(self):
        response = self.post()

        self.assertRedirects(response, reverse("dashboard"))
        user = User.objects.get(username="novichok")
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertIn(user.student_profile, self.group.students.all())
        self.assertEqual(self.client.session["_auth_user_id"], str(user.id))
        self.assertEqual(Invite.objects.get(pk=self.invite.pk).used_by, user)

    def test_parent_invite_lands_on_the_parent_report(self):
        invite = create_invite(self.methodist, role=User.Role.PARENT)

        response = self.post(code=invite.code, username="roditel")

        self.assertRedirects(response, reverse("parent_dashboard"))
        self.assertTrue(hasattr(User.objects.get(username="roditel"), "parent_profile"))

    def test_expired_code_is_reported_on_the_form(self):
        self.invite.expires_at = timezone.now() - timedelta(hours=1)
        self.invite.save(update_fields=["expires_at"])

        response = self.post()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Срок действия кода истёк.", response.context["form"].errors["code"])
        self.assertFalse(User.objects.filter(username="novichok").exists())

    def test_used_code_cannot_register_a_second_account(self):
        self.post()
        self.client.logout()

        response = self.post(username="vtoroy")

        self.assertIn(
            "Код приглашения уже использован.", response.context["form"].errors["code"]
        )
        self.assertFalse(User.objects.filter(username="vtoroy").exists())

    def test_mismatched_passwords_do_not_burn_the_code(self):
        response = self.post(password2="drugoy-parol-77")

        self.assertIn("Пароли не совпадают.", response.context["form"].errors["password2"])
        self.assertIsNone(Invite.objects.get(pk=self.invite.pk).used_at)

    def test_weak_password_is_rejected(self):
        response = self.post(password1="12345678", password2="12345678")

        self.assertIn("password1", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="novichok").exists())

    def test_taken_username_is_rejected_before_the_code_is_spent(self):
        User.objects.create_user("novichok")

        response = self.post()

        self.assertIn("username", response.context["form"].errors)
        self.assertIsNone(Invite.objects.get(pk=self.invite.pk).used_at)

    def test_logged_in_user_is_sent_to_the_cabinet(self):
        self.client.force_login(self.methodist)

        self.assertRedirects(
            self.client.get(reverse("register")), reverse("dashboard"),
            fetch_redirect_response=False,
        )

    def test_login_page_offers_registration(self):
        self.assertContains(self.client.get(reverse("login")), reverse("register"))
