import json
import shutil
import tempfile
from pathlib import Path

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ParentProfile, StudentProfile, User
from apps.accounts.services import create_invite
from apps.ai_mentor.models import AiHintMessage, AiHintSession
from apps.events.models import Event
from apps.expert_review.models import ExpertReviewRequest
from apps.knowledge.tests import make_node
from apps.practice.models import Attempt
from apps.practice.tests import make_assignment

from .models import ConsentRecord, DataDeletionRequest, Feedback
from .services import record_current_consents


PASSWORD = "korova-9-luna"


def make_student(username: str) -> StudentProfile:
    return StudentProfile.objects.create(
        user=User.objects.create_user(
            username, email=f"{username}@example.com", password=PASSWORD,
            role=User.Role.STUDENT,
        )
    )


def registration_payload(invite, username: str, **changes):
    payload = {
        "code": invite.code,
        "username": username,
        "email": f"{username}@example.com",
        "password1": PASSWORD,
        "password2": PASSWORD,
        "accept_terms": True,
        "accept_privacy": True,
        "age_declaration": True,
        "parent_child_consent": True,
    }
    payload.update(changes)
    return payload


class RegistrationConsentTests(TestCase):
    def setUp(self):
        self.methodist = User.objects.create_user("legal-methodist", role=User.Role.METHODIST)

    def test_student_registration_creates_current_consents(self):
        invite = create_invite(self.methodist)
        response = self.client.post(
            reverse("register_by_invite", args=[invite.code]),
            registration_payload(invite, "legal-student"),
            HTTP_USER_AGENT="Test Browser",
            REMOTE_ADDR="192.0.2.10",
        )
        self.assertRedirects(response, reverse("dashboard"))
        user = User.objects.get(username="legal-student")
        records = ConsentRecord.objects.filter(user=user)
        self.assertEqual(
            set(records.values_list("kind", flat=True)),
            {ConsentRecord.Kind.TERMS, ConsentRecord.Kind.PERSONAL_DATA},
        )
        self.assertTrue(records.filter(ip="192.0.2.10", user_agent="Test Browser").exists())

    def test_parent_registration_for_child_creates_representative_consent(self):
        child = make_student("legal-child")
        invite = create_invite(
            self.methodist, role=User.Role.PARENT, for_student=child
        )
        response = self.client.post(
            reverse("register_by_invite", args=[invite.code]),
            registration_payload(invite, "legal-parent"),
        )
        self.assertRedirects(response, reverse("parent_dashboard"))
        parent = User.objects.get(username="legal-parent")
        consent = ConsentRecord.objects.get(
            user=parent, kind=ConsentRecord.Kind.PARENT_FOR_CHILD
        )
        self.assertEqual(consent.subject_student, child)
        self.assertIn(child, parent.parent_profile.children.all())

    def test_registration_without_required_checkboxes_is_rejected(self):
        invite = create_invite(self.methodist)
        payload = registration_payload(invite, "no-consent")
        payload.pop("accept_terms")
        payload.pop("accept_privacy")
        payload.pop("age_declaration")
        response = self.client.post(reverse("register"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("accept_terms", response.context["form"].errors)
        self.assertIn("accept_privacy", response.context["form"].errors)
        self.assertIn("age_declaration", response.context["form"].errors)
        self.assertFalse(User.objects.filter(username="no-consent").exists())


@override_settings(LEGAL_CONSENT_ENFORCED=True)
class ConsentMiddlewareTests(TestCase):
    def setUp(self):
        self.student = make_student("consent-gate")
        self.client.force_login(self.student.user)

    def test_page_redirect_and_api_forbidden(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("legal_accept")))
        api_response = self.client.get("/api/me/")
        self.assertEqual(api_response.status_code, 403)
        self.assertEqual(api_response.json()["code"], "consent_required")

    def test_staff_roles_are_exempt(self):
        methodist = User.objects.create_user("consent-staff", role=User.Role.METHODIST)
        self.client.force_login(methodist)
        self.assertEqual(self.client.get(reverse("methodist_dashboard")).status_code, 200)

    def test_version_bump_requires_acceptance_again(self):
        record_current_consents(self.student.user, ip=None, user_agent="")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        with self.settings(LEGAL_DOCUMENT_VERSIONS={
            "privacy": "2026-11-01", "terms": "2026-10-01"
        }):
            response = self.client.get(reverse("dashboard"))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse("legal_accept")))


class LegalDocumentTests(TestCase):
    def test_documents_are_public_and_show_draft_banner(self):
        for name in ("legal_privacy", "legal_terms"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response, "Черновик. Требует проверки юристом перед публикацией"
                )

    @override_settings(LEGAL_DOCS_DRAFT=False)
    def test_draft_banner_can_be_disabled(self):
        self.assertNotContains(
            self.client.get(reverse("legal_privacy")),
            "Черновик. Требует проверки юристом перед публикацией",
        )


class DataExportTests(TestCase):
    def test_export_is_downloadable_and_contains_only_own_attempts(self):
        owner = make_student("export-owner")
        stranger = make_student("export-stranger")
        node = make_node("export-node")
        assignment = make_assignment(node)
        Attempt.objects.create(
            student=owner, assignment=assignment, submitted_answer="own-answer"
        )
        Attempt.objects.create(
            student=stranger, assignment=assignment, submitted_answer="foreign-answer"
        )
        record_current_consents(owner.user, ip=None, user_agent="")
        self.client.force_login(owner.user)

        response = self.client.get(reverse("account_data_export"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        payload = json.loads(b"".join(response.streaming_content).decode("utf-8"))
        answers = [attempt["submitted_answer"] for attempt in payload["attempts"]]
        self.assertEqual(answers, ["own-answer"])
        self.assertNotIn("foreign-answer", json.dumps(payload, ensure_ascii=False))


class DataDeletionTests(TestCase):
    def setUp(self):
        self.private_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.private_root, True)
        self.settings_override = override_settings(PRIVATE_MEDIA_ROOT=self.private_root)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.student = make_student("delete-target")
        self.parent_user = User.objects.create_user(
            "delete-parent", password=PASSWORD, role=User.Role.PARENT
        )
        self.parent = ParentProfile.objects.create(user=self.parent_user)
        self.parent.children.add(self.student)
        node = make_node("delete-node")
        self.assignment = make_assignment(node)
        self.attempt = Attempt.objects.create(
            student=self.student, assignment=self.assignment, submitted_answer="42"
        )
        session = AiHintSession.objects.create(
            student=self.student, assignment=self.assignment, node=node
        )
        self.message = AiHintMessage.objects.create(
            session=session, role=AiHintMessage.Role.STUDENT, text="Личный вопрос"
        )
        self.review = ExpertReviewRequest.objects.create(
            student=self.student,
            assignment=self.assignment,
            solution_file=SimpleUploadedFile("solution.pdf", b"%PDF-1.4 test"),
        )

    def test_password_confirmation_creates_request_and_status_is_visible(self):
        self.client.force_login(self.student.user)
        response = self.client.post(
            reverse("account_delete_request"), {"password": PASSWORD}
        )
        self.assertRedirects(response, reverse("account_settings"))
        deletion = DataDeletionRequest.objects.get(user=self.student.user)
        self.assertEqual(deletion.status, DataDeletionRequest.Status.PENDING)
        self.assertContains(
            self.client.get(reverse("account_settings")), "Ожидает обработки"
        )

    def test_methodist_anonymizes_and_keeps_learning_history(self):
        deletion = DataDeletionRequest.objects.create(user=self.student.user)
        original_user_id = self.student.user_id
        original_file = self.private_root / self.review.solution_file.name
        self.assertTrue(original_file.exists())
        methodist = User.objects.create_user("delete-methodist", role=User.Role.METHODIST)
        self.client.force_login(methodist)

        response = self.client.post(
            f"/api/admin/deletion-requests/{deletion.pk}/execute/",
            {"confirm": True}, "application/json",
        )

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(pk=original_user_id)
        self.assertEqual(user.username, f"deleted-{original_user_id}")
        self.assertFalse(user.is_active)
        self.assertEqual(user.email, "")
        self.assertFalse(user.has_usable_password())
        self.assertFalse(self.parent.children.filter(pk=self.student.pk).exists())
        self.message.refresh_from_db()
        self.assertEqual(self.message.text, "")
        self.review.refresh_from_db()
        self.assertEqual(self.review.solution_file.name, "")
        self.assertFalse(original_file.exists())
        self.assertTrue(Attempt.objects.filter(pk=self.attempt.pk).exists())
        deletion.refresh_from_db()
        self.assertEqual(deletion.status, DataDeletionRequest.Status.DONE)
        self.assertEqual(deletion.processed_by, methodist)
        self.assertTrue(
            Event.objects.filter(
                event_type=Event.Type.ADMIN_ACTION,
                payload__action="data_deletion.complete",
            ).exists()
        )

    def test_only_methodist_or_superuser_can_execute(self):
        deletion = DataDeletionRequest.objects.create(user=self.student.user)
        outsider = User.objects.create_user("delete-outsider", role=User.Role.PARENT)
        ParentProfile.objects.create(user=outsider)
        url = f"/api/admin/deletion-requests/{deletion.pk}/execute/"
        self.client.force_login(outsider)
        self.assertEqual(
            self.client.post(url, {"confirm": True}, "application/json").status_code,
            403,
        )
        superuser = User.objects.create_superuser("delete-root", password=PASSWORD)
        self.client.force_login(superuser)
        self.assertEqual(
            self.client.post(url, {"confirm": True}, "application/json").status_code,
            200,
        )


class FeedbackTests(TestCase):
    def setUp(self):
        cache.clear()
        self.student = make_student("feedback-user")

    def tearDown(self):
        cache.clear()

    def test_authenticated_user_creates_feedback_and_anonymous_is_denied(self):
        url = reverse("feedback_create")
        self.assertIn(self.client.post(url, {"message": "Ошибка"}).status_code, (401, 403))
        self.client.force_login(self.student.user)
        response = self.client.post(
            url,
            {"page_url": "/track/", "message": "Не открывается урок"},
            "application/json",
        )
        self.assertEqual(response.status_code, 201)
        feedback = Feedback.objects.get()
        self.assertEqual(feedback.user, self.student.user)
        self.assertEqual(feedback.page_url, "/track/")
        self.assertTrue(
            Event.objects.filter(event_type=Event.Type.FEEDBACK_CREATED).exists()
        )

    def test_feedback_is_throttled(self):
        self.client.force_login(self.student.user)
        responses = [
            self.client.post(
                reverse("feedback_create"),
                {"message": f"Сообщение {index}"},
                "application/json",
            )
            for index in range(11)
        ]
        self.assertTrue(all(response.status_code == 201 for response in responses[:10]))
        self.assertEqual(responses[10].status_code, 429)

    def test_methodist_changes_feedback_status(self):
        feedback = Feedback.objects.create(user=self.student.user, message="Проблема")
        methodist = User.objects.create_user("feedback-methodist", role=User.Role.METHODIST)
        self.client.force_login(methodist)
        response = self.client.patch(
            f"/api/admin/feedback/{feedback.pk}/",
            {"status": Feedback.Status.IN_PROGRESS, "staff_comment": "Проверяем"},
            "application/json",
        )
        self.assertEqual(response.status_code, 200)
        feedback.refresh_from_db()
        self.assertEqual(feedback.status, Feedback.Status.IN_PROGRESS)
        self.assertEqual(feedback.staff_comment, "Проверяем")
