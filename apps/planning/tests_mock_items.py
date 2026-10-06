from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.content.models import Assignment
from apps.knowledge.models import KnowledgeNode
from apps.knowledge.services import set_mastery
from apps.knowledge.tests import make_node, make_student
from apps.mocks.models import MockExam, MockExamResult
from apps.mocks.services import save_mock_exam, start_mock, submit_mock
from apps.practice.tests import make_assignment

from .models import StudyPlan, StudyPlanItem
from .phases import EXAM, phase_for_date
from .schedule import _plan_entries
from .services import build_study_plan, move_item, preparation_start
from .tasks import refresh_plans


class MockPlanItemTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.student = make_student("mock-plan")
        self.student.weekly_hours = 6
        self.student.exam_date = self.today + timedelta(days=100)
        self.student.save(update_fields=["weekly_hours", "exam_date"])

    def test_first_mock_is_fourteen_days_after_preparation_start(self):
        plan = build_study_plan(self.student)

        first = plan.items.filter(item_type=StudyPlanItem.ItemType.MOCK).first()

        self.assertEqual(first.due_date, preparation_start(self.student) + timedelta(days=14))
        self.assertEqual(first.origin, StudyPlanItem.Origin.PLAN)

    def test_mock_cadence_uses_last_completed_full_mock(self):
        exam = MockExam.objects.create(title="Completed full")
        completed_at = timezone.now() - timedelta(days=5)
        MockExamResult.objects.create(
            student=self.student,
            exam=exam,
            status=MockExamResult.Status.COMPLETED,
            completed_at=completed_at,
        )

        plan = build_study_plan(self.student)
        first = plan.items.filter(item_type=StudyPlanItem.ItemType.MOCK).first()

        self.assertEqual(
            first.due_date,
            timezone.localdate(completed_at) + timedelta(days=settings.PLAN_MOCK_INTERVAL_DAYS),
        )

    def test_mock_is_not_scheduled_after_exam(self):
        self.student.exam_date = self.today + timedelta(days=10)
        self.student.save(update_fields=["exam_date"])

        plan = build_study_plan(self.student)

        self.assertFalse(plan.items.filter(item_type=StudyPlanItem.ItemType.MOCK).exists())

    def test_variant_is_only_in_exam_week_without_mock(self):
        initial = build_study_plan(self.student)
        StudyPlan.objects.filter(pk=initial.pk).update(
            created_at=timezone.now() - timedelta(weeks=35)
        )
        self.student.exam_date = self.today + timedelta(weeks=3)
        self.student.save(update_fields=["exam_date"])
        MockExam.objects.create(
            title="Part 1 variant A", kind=MockExam.Kind.PART1_VARIANT
        )
        MockExam.objects.create(
            title="Part 1 variant B", kind=MockExam.Kind.PART1_VARIANT
        )

        plan = build_study_plan(self.student)
        mocks = set(
            plan.items.filter(item_type=StudyPlanItem.ItemType.MOCK).values_list(
                "week_index", flat=True
            )
        )
        variants = plan.items.filter(item_type=StudyPlanItem.ItemType.VARIANT)

        self.assertEqual(variants.count(), 2)
        for item in variants:
            self.assertNotIn(item.week_index, mocks)
            self.assertEqual(
                phase_for_date(
                    preparation_start(self.student),
                    self.student.exam_date,
                    item.due_date,
                    consolidation_weeks=settings.PLAN_CONSOLIDATION_WEEKS,
                    exam_phase_weeks=settings.PLAN_EXAM_PHASE_WEEKS,
                ).code,
                EXAM,
            )
            self.assertLessEqual(item.due_date, self.student.exam_date)

    def test_no_variant_item_without_active_uncompleted_variant(self):
        initial = build_study_plan(self.student)
        StudyPlan.objects.filter(pk=initial.pk).update(
            created_at=timezone.now() - timedelta(weeks=35)
        )
        self.student.exam_date = self.today + timedelta(weeks=3)
        self.student.save(update_fields=["exam_date"])

        plan = build_study_plan(self.student)

        self.assertFalse(plan.items.filter(item_type=StudyPlanItem.ItemType.VARIANT).exists())

    def test_mock_precedes_reviews_and_blocks_learning_in_low_hours_week(self):
        self.student.weekly_hours = 1
        self.student.save(update_fields=["weekly_hours"])
        mastered = make_node("mock-budget-review", exam_part=KnowledgeNode.Part.PART1)
        set_mastery(self.student, mastered, 90)
        make_node("mock-budget-learning", exam_part=KnowledgeNode.Part.PART1)

        plan = build_study_plan(self.student)
        mock = plan.items.filter(item_type=StudyPlanItem.ItemType.MOCK).first()
        review = plan.items.filter(
            item_type=StudyPlanItem.ItemType.REVIEW, week_index=mock.week_index
        ).first()

        self.assertIsNotNone(review)
        self.assertLess(mock.order, review.order)
        self.assertFalse(
            plan.items.filter(
                week_index=mock.week_index,
                item_type__in=(
                    StudyPlanItem.ItemType.LESSON,
                    StudyPlanItem.ItemType.PRACTICE,
                ),
            ).exists()
        )

    def test_completing_full_mock_closes_item_and_shifts_cadence(self):
        exam = MockExam.objects.create(title="Full mock")
        plan = build_study_plan(self.student)
        pending = plan.items.filter(item_type=StudyPlanItem.ItemType.MOCK).first()

        result = start_mock(self.student, exam)
        submit_mock(result, {})
        refresh_plans()

        pending.refresh_from_db()
        self.assertEqual(pending.status, StudyPlanItem.Status.DONE)
        active = StudyPlan.objects.get(student=self.student, status=StudyPlan.Status.ACTIVE)
        next_mock = active.items.filter(
            item_type=StudyPlanItem.ItemType.MOCK,
            status=StudyPlanItem.Status.PENDING,
        ).first()
        result.refresh_from_db()
        self.assertEqual(
            next_mock.due_date,
            timezone.localdate(result.completed_at)
            + timedelta(days=settings.PLAN_MOCK_INTERVAL_DAYS),
        )

    def test_completing_variant_closes_variant_item_only(self):
        initial = build_study_plan(self.student)
        StudyPlan.objects.filter(pk=initial.pk).update(
            created_at=timezone.now() - timedelta(weeks=35)
        )
        self.student.exam_date = self.today + timedelta(weeks=3)
        self.student.save(update_fields=["exam_date"])
        variant = MockExam.objects.create(
            title="Completable variant", kind=MockExam.Kind.PART1_VARIANT
        )
        plan = build_study_plan(self.student)
        pending_variant = plan.items.filter(
            item_type=StudyPlanItem.ItemType.VARIANT
        ).first()

        submit_mock(start_mock(self.student, variant), {})

        pending_variant.refresh_from_db()
        self.assertEqual(pending_variant.status, StudyPlanItem.Status.DONE)
        self.assertTrue(
            plan.items.filter(
                item_type=StudyPlanItem.ItemType.MOCK,
                status=StudyPlanItem.Status.PENDING,
            ).exists()
        )

    def test_manual_mock_move_survives_regeneration(self):
        plan = build_study_plan(self.student)
        mock = plan.items.filter(item_type=StudyPlanItem.ItemType.MOCK).first()
        moved_to = mock.due_date + timedelta(days=3)
        move_item(mock, moved_to)

        rebuilt = build_study_plan(self.student)

        carried = rebuilt.items.get(
            item_type=StudyPlanItem.ItemType.MOCK,
            origin=StudyPlanItem.Origin.MANUAL,
        )
        self.assertEqual(carried.due_date, moved_to)

    def test_checkpoint_calendar_links_are_actionable(self):
        variant = MockExam.objects.create(
            title="Linked variant", kind=MockExam.Kind.PART1_VARIANT
        )
        plan = build_study_plan(self.student)
        mock = plan.items.filter(item_type=StudyPlanItem.ItemType.MOCK).first()
        variant_item = StudyPlanItem.objects.create(
            plan=plan,
            item_type=StudyPlanItem.ItemType.VARIANT,
            due_date=self.today,
            order=999,
        )

        entries = _plan_entries(self.student, self.today, self.student.exam_date)
        mock_entry = next(entry for entry in entries[mock.due_date] if entry.kind == "mock")
        variant_entry = next(
            entry for entry in entries[variant_item.due_date] if entry.kind == "variant"
        )

        self.assertEqual(mock_entry.url, reverse("mocks"))
        self.assertEqual(variant_entry.url, f'{reverse("mocks")}#mock-{variant.pk}')


class MockKindValidationTests(TestCase):
    def test_mock_kind_defaults_to_full(self):
        self.assertEqual(MockExam.objects.create(title="Default").kind, MockExam.Kind.FULL)

    def test_part1_variant_rejects_part2_assignments(self):
        node = make_node("variant-part2")
        part2 = make_assignment(node, part=Assignment.Part.PART2)

        with self.assertRaises(ValidationError):
            save_mock_exam(
                MockExam(),
                title="Invalid variant",
                kind=MockExam.Kind.PART1_VARIANT,
                duration_minutes=60,
                is_active=True,
                add_assignments=[part2],
            )

        self.assertFalse(MockExam.objects.filter(title="Invalid variant").exists())
