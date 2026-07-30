from django.contrib.auth import get_user_model
from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.content.models import Assignment
from apps.expert_review.services import finish_review, submit_solution
from apps.expert_review.admin import ExpertReviewRequestAdmin
from apps.expert_review.forms import FinishExpertReviewForm
from apps.expert_review.models import ExpertReviewRequest
from apps.events.models import Event
from apps.knowledge.models import SkillMastery
from apps.knowledge.tests import make_node, make_student
from apps.practice.models import MistakeBacklogItem
from apps.practice.tests import make_assignment


class ExpertErrorTagTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.node = make_node("expert-tag")
        self.assignment = make_assignment(
            self.node, answer="", part=Assignment.Part.PART2
        )
        self.assignment.max_score = 2
        self.assignment.save(update_fields=["max_score"])
        self.expert = get_user_model().objects.create_user(
            username="expert-tags", role="expert"
        )

    def test_expert_tags_set_backlog_error_type(self):
        review = submit_solution(
            self.student,
            self.assignment,
            SimpleUploadedFile("solution.jpg", (b"\xff\xd8\xff\xe0" + b"\x00" * 64)),
        )
        finish_review(
            review,
            self.expert,
            {"K1": 0},
            error_tags=[
                {"node_id": self.node.id, "error_type": "wrong_method"}
            ],
        )
        item = MistakeBacklogItem.objects.get()
        self.assertEqual(item.error_type, MistakeBacklogItem.ErrorType.WRONG_METHOD)

    def test_backlog_api_returns_error_type(self):
        MistakeBacklogItem.objects.create(
            student=self.student,
            assignment=self.assignment,
            node=self.node,
            error_type=MistakeBacklogItem.ErrorType.RUBRIC_MISS,
        )
        self.client.force_login(self.student.user)
        response = self.client.get("/api/backlog/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["error_type"], "rubric_miss")

    def test_admin_finish_form_runs_full_pipeline(self):
        review = submit_solution(
            self.student,
            self.assignment,
            SimpleUploadedFile("admin-solution.jpg", (b"\xff\xd8\xff\xe0" + b"\x00" * 64)),
        )
        form = FinishExpertReviewForm(
            data={
                "student": self.student.pk,
                "assignment": self.assignment.pk,
                "attempt": "",
                "mock_result": "",
                "sla_hours": review.sla_hours,
                "score_by_criteria": '{"K1": 0}',
                "comment": "Потерян балл за метод",
                "error_tags": [MistakeBacklogItem.ErrorType.WRONG_METHOD],
                "related_nodes": [self.node.pk],
                "finish_review": "on",
            },
            instance=review,
        )
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        request = type("AdminRequest", (), {"user": self.expert})()
        ExpertReviewRequestAdmin(ExpertReviewRequest, admin.site).save_model(
            request, obj, form, change=True
        )

        review.refresh_from_db()
        self.assertEqual(review.status, ExpertReviewRequest.Status.REVIEWED)
        self.assertTrue(
            MistakeBacklogItem.objects.filter(
                student=self.student,
                assignment=self.assignment,
                error_type=MistakeBacklogItem.ErrorType.WRONG_METHOD,
            ).exists()
        )
        self.assertTrue(SkillMastery.objects.filter(student=self.student, node=self.node).exists())
        self.assertTrue(
            Event.objects.filter(
                student=self.student,
                event_type=Event.Type.EXPERT_REVIEW_COMPLETED,
            ).exists()
        )


class FinishExpertReviewApiTests(TestCase):
    def setUp(self):
        self.student = make_student(username="api-review-student")
        self.node = make_node("api-review-node")
        self.assignment = make_assignment(
            self.node, answer="", part=Assignment.Part.PART2
        )
        self.assignment.max_score = 2
        self.assignment.save(update_fields=["max_score"])
        self.review = submit_solution(
            self.student,
            self.assignment,
            SimpleUploadedFile("api-solution.png", (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)),
        )
        self.expert = get_user_model().objects.create_user(
            username="api-expert", role="expert"
        )
        self.url = f"/api/expert-reviews/{self.review.id}/finish/"
        self.payload = {
            "score_by_criteria": {"К1": 1, "К2": 0},
            "error_tags": [MistakeBacklogItem.ErrorType.WRONG_METHOD],
            "related_node_ids": [self.node.id],
            "comment": "Не обоснован переход",
            "needs_resubmission": False,
        }

    def test_expert_finish_runs_full_pipeline(self):
        self.client.force_login(self.expert)
        response = self.client.post(self.url, self.payload, content_type="application/json")

        self.assertEqual(response.status_code, 200, response.content)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, ExpertReviewRequest.Status.REVIEWED)
        self.assertEqual(self.review.reviewer, self.expert)
        self.assertEqual(self.review.total_score, 1)
        self.assertEqual(self.review.lost_points, 1)
        self.assertTrue(
            SkillMastery.objects.filter(student=self.student, node=self.node).exists()
        )
        self.assertTrue(
            MistakeBacklogItem.objects.filter(
                student=self.student,
                assignment=self.assignment,
                error_type=MistakeBacklogItem.ErrorType.WRONG_METHOD,
            ).exists()
        )
        self.assertTrue(
            Event.objects.filter(
                student=self.student,
                event_type=Event.Type.EXPERT_REVIEW_COMPLETED,
            ).exists()
        )

    def test_student_is_forbidden(self):
        self.client.force_login(self.student.user)
        response = self.client.post(self.url, self.payload, content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_repeated_finish_returns_conflict(self):
        self.client.force_login(self.expert)
        self.assertEqual(
            self.client.post(self.url, self.payload, content_type="application/json").status_code,
            200,
        )
        self.assertEqual(
            self.client.post(self.url, self.payload, content_type="application/json").status_code,
            409,
        )

    def test_score_above_one_is_invalid(self):
        self.client.force_login(self.expert)
        self.payload["score_by_criteria"] = {"К1": 2}
        response = self.client.post(self.url, self.payload, content_type="application/json")
        self.assertEqual(response.status_code, 400)


# --- Приватность работ учеников (перенесено из ветки service-implementation) ---

import shutil  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

from django.core.exceptions import ValidationError  # noqa: E402
from django.test import override_settings  # noqa: E402
from django.urls import reverse  # noqa: E402

from apps.accounts.models import ParentProfile, User  # noqa: E402

from .validators import validate_solution_upload  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
EXE = b"MZ\x90\x00" + b"\x00" * 64


def _upload(name="solution.jpg", content=JPEG, content_type="image/jpeg"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class SolutionPrivacyTestCase(TestCase):
    """Приватное хранилище и временные каталоги вместо рабочего дерева."""

    def setUp(self):
        self.private_root = Path(tempfile.mkdtemp())
        self.public_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.private_root, True)
        self.addCleanup(shutil.rmtree, self.public_root, True)
        patch = override_settings(
            PRIVATE_MEDIA_ROOT=self.private_root, MEDIA_ROOT=self.public_root
        )
        patch.enable()
        self.addCleanup(patch.disable)

        self.student = make_student("privacy-student")
        self.node = make_node("privacy-node")
        self.assignment = make_assignment(self.node, answer="", part=Assignment.Part.PART2)

    def _review(self, student=None):
        return submit_solution(
            student or self.student, self.assignment,
            SimpleUploadedFile("solution.jpg", JPEG, content_type="image/jpeg"),
        )


class SolutionUploadValidationTests(SolutionPrivacyTestCase):
    def _post(self, upload):
        self.client.force_login(self.student.user)
        return self.client.post(
            "/api/expert-reviews/submit/",
            {"assignment": self.assignment.pk, "file": upload},
        )

    def test_upload_is_stored_privately_with_random_name(self):
        response = self._post(_upload())
        self.assertEqual(response.status_code, 201)
        review = ExpertReviewRequest.objects.get(pk=response.json()["id"])
        self.assertTrue(review.solution_file.name.startswith("solutions/%d/" % self.student.pk))
        self.assertNotIn("solution.jpg", review.solution_file.name)
        self.assertTrue((self.private_root / review.solution_file.name).exists())
        self.assertFalse((self.public_root / review.solution_file.name).exists())

    def test_file_has_no_public_url(self):
        with self.assertRaises(ValueError):
            self._review().solution_file.url  # noqa: B018

    def test_forged_content_type_is_rejected(self):
        self.assertEqual(self._post(_upload(content=EXE)).status_code, 400)
        self.assertEqual(ExpertReviewRequest.objects.count(), 0)

    def test_unknown_extension_is_rejected(self):
        response = self._post(_upload("payload.exe", EXE, "application/octet-stream"))
        self.assertEqual(response.status_code, 400)

    def test_oversized_upload_is_rejected(self):
        with self.settings(SOLUTION_UPLOAD_MAX_BYTES=32):
            self.assertEqual(self._post(_upload()).status_code, 400)

    def test_validator_rejects_png_bytes_in_jpg(self):
        with self.assertRaises(ValidationError):
            validate_solution_upload(_upload("s.jpg", PNG, "image/jpeg"))


class SolutionAccessTests(SolutionPrivacyTestCase):
    def setUp(self):
        super().setUp()
        self.review = self._review()
        self.url = reverse("expert-review-file", args=[self.review.pk])
        self.other_student = make_student("privacy-other")
        self.parent = ParentProfile.objects.create(
            user=get_user_model().objects.create_user("privacy-parent", role=User.Role.PARENT)
        )
        self.parent.children.add(self.student)
        self.expert = get_user_model().objects.create_user(
            "privacy-expert", role=User.Role.EXPERT
        )
        self.other_expert = get_user_model().objects.create_user(
            "privacy-expert-2", role=User.Role.EXPERT
        )
        self.methodist = get_user_model().objects.create_user(
            "privacy-methodist", role=User.Role.METHODIST
        )

    def _get(self, user=None):
        if user is not None:
            self.client.force_login(user)
        return self.client.get(self.url)

    def test_owner_can_download(self):
        response = self._get(self.student.user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), JPEG)

    def test_anonymous_denied(self):
        self.assertIn(self._get().status_code, (401, 403))

    def test_other_student_gets_404(self):
        self.assertEqual(self._get(self.other_student.user).status_code, 404)

    def test_parent_of_owner_can_download(self):
        self.assertEqual(self._get(self.parent.user).status_code, 200)

    def test_methodist_can_download(self):
        self.assertEqual(self._get(self.methodist).status_code, 200)

    def test_unassigned_review_visible_to_any_expert(self):
        self.assertEqual(self._get(self.expert).status_code, 200)

    def test_assigned_review_hidden_from_other_expert(self):
        self.review.reviewer = self.expert
        self.review.save(update_fields=["reviewer"])
        self.assertEqual(self._get(self.other_expert).status_code, 404)

    def test_headers_forbid_caching_and_sniffing(self):
        response = self._get(self.student.user)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_nginx_accel_redirect_when_configured(self):
        with self.settings(PRIVATE_MEDIA_NGINX_LOCATION="/private-media"):
            response = self._get(self.student.user)
        self.assertEqual(
            response["X-Accel-Redirect"], "/private-media/%s" % self.review.solution_file.name
        )
