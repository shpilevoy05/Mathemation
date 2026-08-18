from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.ai_mentor.models import AiHintSession
from apps.content.models import Assignment, Lesson
from apps.expert_review.models import ExpertReviewRequest
from apps.knowledge.models import KnowledgeNode


class BackofficeRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.expert = User.objects.get(username="expert")
        cls.methodist = User.objects.get(username="methodist")
        cls.student = User.objects.get(username="student").student_profile
        cls.superuser = User.objects.create_superuser(
            username="admin-tests", password="admin-password"
        )

    def test_groups_have_exact_permission_sets(self):
        expert_permissions = {
            "expert_review.add_expertreviewrequest",
            "expert_review.change_expertreviewrequest",
            "expert_review.delete_expertreviewrequest",
            "expert_review.view_expertreviewrequest",
            "ai_mentor.view_aihintsession",
            "ai_mentor.view_aihintmessage",
            "content.view_assignment",
            "knowledge.view_knowledgenode",
            "mocks.view_mockexamresult",
        }
        full_methodist_models = {
            "content.lesson",
            "content.theoryblock",
            "content.assignment",
            "content.assignmentskilltag",
            "knowledge.topiccluster",
            "knowledge.knowledgenode",
            "knowledge.knowledgedependency",
            "mocks.mockexam",
            "diagnostics.diagnostictest",
            "planning.trajectory",
            "planning.studyplan",
            "planning.studyplanitem",
        }
        methodist_permissions = {
            f"{model.rsplit('.', 1)[0]}.{action}_{model.rsplit('.', 1)[1]}"
            for model in full_methodist_models
            for action in ("add", "change", "delete", "view")
        }
        methodist_permissions.add("accounts.view_studentprofile")

        self.assertEqual(self._permissions("Эксперты"), expert_permissions)
        self.assertEqual(self._permissions("Методисты"), methodist_permissions)

    def test_role_admin_access_is_scoped(self):
        self.client.force_login(self.expert)
        self.assertEqual(
            self.client.get(reverse("admin:expert_review_expertreviewrequest_changelist")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("admin:accounts_user_changelist")).status_code,
            403,
        )

        self.client.force_login(self.methodist)
        self.assertEqual(
            self.client.get(reverse("admin:content_lesson_changelist")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("admin:expert_review_expertreviewrequest_changelist")).status_code,
            403,
        )

    def test_expert_sees_only_escalated_hint_sessions(self):
        assignments = list(Assignment.objects.order_by("pk")[:2])
        visible = AiHintSession.objects.create(
            student=self.student,
            assignment=assignments[0],
            escalated_to_expert=True,
        )
        hidden = AiHintSession.objects.create(
            student=self.student,
            assignment=assignments[1],
            escalated_to_expert=False,
        )

        self.client.force_login(self.expert)
        response = self.client.get(reverse("admin:ai_mentor_aihintsession_changelist"))

        self.assertEqual(response.status_code, 200)
        result_ids = {item.pk for item in response.context["cl"].result_list}
        self.assertIn(visible.pk, result_ids)
        self.assertNotIn(hidden.pk, result_ids)

    def test_expert_review_list_defaults_to_submitted_queue(self):
        node = KnowledgeNode.objects.get(code="frac-powers")
        assignments = list(node.assignments.order_by("pk")[:2])
        pending = ExpertReviewRequest.objects.create(
            student=self.student,
            assignment=assignments[0],
            solution_file="solutions/pending.jpg",
        )
        reviewed = ExpertReviewRequest.objects.create(
            student=self.student,
            assignment=assignments[1],
            solution_file="solutions/reviewed.jpg",
            status=ExpertReviewRequest.Status.REVIEWED,
        )

        self.client.force_login(self.expert)
        response = self.client.get(
            reverse("admin:expert_review_expertreviewrequest_changelist")
        )

        self.assertEqual(response.status_code, 200)
        result_ids = {item.pk for item in response.context["cl"].result_list}
        self.assertIn(pending.pk, result_ids)
        self.assertNotIn(reviewed.pk, result_ids)

    def test_user_add_page_contains_profile_inlines(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:accounts_user_add"))

        self.assertEqual(response.status_code, 200)
        inline_models = {inline.opts.model for inline in response.context["inline_admin_formsets"]}
        self.assertIn(self.student.__class__, inline_models)
        self.assertIn(User._meta.get_field("parent_profile").related_model, inline_models)

    @staticmethod
    def _permissions(group_name):
        return {
            f"{app_label}.{codename}"
            for app_label, codename in Group.objects.get(name=group_name).permissions.values_list(
                "content_type__app_label", "codename"
            )
        }
