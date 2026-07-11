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
            SimpleUploadedFile("solution.jpg", b"scan"),
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
            SimpleUploadedFile("admin-solution.jpg", b"scan"),
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
