from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import User
from apps.billing.models import PaymentMethod, Tariff
from apps.content.models import Homework
from apps.diagnostics.models import DiagnosticTest
from apps.economy.models import ShopItem
from apps.exams.models import ExamProfile
from apps.expert_review.models import ExpertReviewRequest
from apps.knowledge.models import KnowledgeNode
from apps.mocks.models import MockExam
from apps.planning.models import Trajectory
from apps.practice.models import Attempt


class BootstrapReferenceCommandTests(TestCase):
    def test_dry_run_prints_plan_and_changes_nothing(self):
        output = StringIO()
        before = (
            KnowledgeNode.objects.count(),
            Trajectory.objects.count(),
            ExamProfile.objects.count(),
            Tariff.objects.count(),
            PaymentMethod.objects.count(),
            ShopItem.objects.count(),
        )

        call_command("bootstrap_reference", "--dry-run", stdout=output)

        self.assertIn("Будут созданы", output.getvalue())
        self.assertIn("Сухой прогон: изменения не сохранены", output.getvalue())
        self.assertEqual(
            before,
            (
                KnowledgeNode.objects.count(),
                Trajectory.objects.count(),
                ExamProfile.objects.count(),
                Tariff.objects.count(),
                PaymentMethod.objects.count(),
                ShopItem.objects.count(),
            ),
        )
        self.assertFalse(User.objects.exists())

    def test_creates_only_reference_data_and_is_idempotent(self):
        call_command("bootstrap_reference", stdout=StringIO())
        counts = (
            KnowledgeNode.objects.count(),
            Trajectory.objects.count(),
            ExamProfile.objects.count(),
            Tariff.objects.count(),
            PaymentMethod.objects.count(),
            ShopItem.objects.count(),
        )

        call_command("bootstrap_reference", stdout=StringIO())

        self.assertEqual(
            counts,
            (
                KnowledgeNode.objects.count(),
                Trajectory.objects.count(),
                ExamProfile.objects.count(),
                Tariff.objects.count(),
                PaymentMethod.objects.count(),
                ShopItem.objects.count(),
            ),
        )
        self.assertTrue(all(count > 0 for count in counts))
        self.assertFalse(User.objects.exists())
        self.assertFalse(Attempt.objects.exists())
        self.assertFalse(ExpertReviewRequest.objects.exists())
        self.assertFalse(Homework.objects.exists())
        # Текущие диагностика и пробник seed_demo собраны из демо-задач,
        # поэтому production bootstrap не выдаёт их за справочники.
        self.assertFalse(DiagnosticTest.objects.exists())
        self.assertFalse(MockExam.objects.exists())
