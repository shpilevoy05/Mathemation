from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.knowledge.models import KnowledgeNode, SkillMastery
from apps.knowledge.services import set_mastery
from apps.knowledge.tests import make_node, make_student
from apps.practice.models import Attempt
from apps.practice.services import submit_attempt
from apps.practice.tests import make_assignment

from .models import StudyPlanItem
from .services import build_study_plan


class ScheduledReviewPlannerTests(TestCase):
    def setUp(self):
        self.student = make_student("scheduled-review")
        self.student.weekly_hours = 4
        self.student.exam_date = timezone.localdate() + timedelta(days=90)
        self.student.save(update_fields=["weekly_hours", "exam_date"])

    def test_review_is_due_at_retention_boundary(self):
        node = make_node("review-due")
        mastery = set_mastery(self.student, node, 90)
        expected = timezone.localdate(mastery.peak_at) + timedelta(
            days=mastery.retention_days
        )

        plan = build_study_plan(self.student)

        item = plan.items.filter(
            node=node, item_type=StudyPlanItem.ItemType.REVIEW
        ).order_by("due_date").first()
        self.assertEqual(item.due_date, expected)
        self.assertEqual(item.origin, StudyPlanItem.Origin.PLAN)

    def test_review_is_not_scheduled_on_or_after_exam(self):
        node = make_node("review-after-exam")
        mastery = set_mastery(self.student, node, 90)
        mastery.retention_days = settings.PLAN_REVIEW_MAX_RETENTION_DAYS
        mastery.save(update_fields=["retention_days"])
        self.student.exam_date = timezone.localdate() + timedelta(days=30)
        self.student.save(update_fields=["exam_date"])

        plan = build_study_plan(self.student)

        self.assertFalse(
            plan.items.filter(
                node=node,
                item_type=StudyPlanItem.ItemType.REVIEW,
                due_date__gte=self.student.exam_date,
            ).exists()
        )

    def test_review_share_cap_moves_overflow_to_next_week(self):
        nodes = [
            make_node(
                f"review-cap-{index}",
                exam_part=KnowledgeNode.Part.PART1,
            )
            for index in range(5)
        ]
        for node in nodes:
            set_mastery(self.student, node, 90)

        plan = build_study_plan(self.student)
        final_start = self.student.exam_date - timedelta(weeks=3)
        reviews = plan.items.filter(
            item_type=StudyPlanItem.ItemType.REVIEW, due_date__lt=final_start
        )
        per_week = Counter(reviews.values_list("week_index", flat=True))

        cap_hours = self.student.weekly_hours * settings.PLAN_REVIEW_WEEK_SHARE
        self.assertTrue(
            all(
                count * settings.PLAN_REVIEW_PART1_HOURS <= cap_hours
                for count in per_week.values()
            )
        )
        self.assertGreater(max(per_week), min(per_week))

    def test_first_review_in_week_cannot_be_starved_by_share_cap(self):
        self.student.weekly_hours = 1
        self.student.save(update_fields=["weekly_hours"])
        node = make_node("review-oversized", exam_part=KnowledgeNode.Part.PART2)
        set_mastery(self.student, node, 90)

        plan = build_study_plan(self.student)

        self.assertTrue(
            plan.items.filter(
                node=node, item_type=StudyPlanItem.ItemType.REVIEW
            ).exists()
        )

    def test_correct_attempt_closes_pending_plan_review(self):
        node = make_node("review-close")
        assignment = make_assignment(node)
        set_mastery(self.student, node, 90)
        plan = build_study_plan(self.student)
        review = plan.items.filter(
            node=node, item_type=StudyPlanItem.ItemType.REVIEW
        ).order_by("due_date").first()

        submit_attempt(self.student, assignment, "42", Attempt.Context.REVIEW)

        review.refresh_from_db()
        self.assertEqual(review.status, StudyPlanItem.Status.DONE)

    def test_wrong_attempt_keeps_review_open_and_reschedules_earlier(self):
        node = make_node("review-wrong")
        assignment = make_assignment(node)
        mastery = set_mastery(self.student, node, 90)
        mastery.retention_days = 28
        mastery.save(update_fields=["retention_days"])
        first_plan = build_study_plan(self.student)
        review = first_plan.items.filter(
            node=node, item_type=StudyPlanItem.ItemType.REVIEW
        ).order_by("due_date").first()

        submit_attempt(self.student, assignment, "wrong", Attempt.Context.REVIEW)

        review.refresh_from_db()
        self.assertEqual(review.status, StudyPlanItem.Status.PENDING)
        second_plan = build_study_plan(self.student)
        moved = second_plan.items.filter(
            node=node, item_type=StudyPlanItem.ItemType.REVIEW
        ).order_by("due_date").first()
        self.assertEqual(moved.due_date, timezone.localdate() + timedelta(days=14))

    def test_mastered_topic_gets_no_learning_items(self):
        node = make_node("review-not-learning")
        set_mastery(self.student, node, 90)

        plan = build_study_plan(self.student)

        self.assertFalse(
            plan.items.filter(
                node=node,
                item_type__in=(
                    StudyPlanItem.ItemType.LESSON,
                    StudyPlanItem.ItemType.PRACTICE,
                ),
            ).exists()
        )

    def test_review_share_increases_in_final_phases(self):
        self.student.weekly_hours = 2
        self.student.exam_date = timezone.localdate() + timedelta(weeks=38)
        self.student.save(update_fields=["weekly_hours", "exam_date"])
        nodes = [make_node(f"SK-phase-{index}") for index in range(6)]
        for node in nodes:
            set_mastery(self.student, node, 90)

        plan = build_study_plan(self.student)
        reviews = list(plan.items.filter(item_type=StudyPlanItem.ItemType.REVIEW))
        final_start = self.student.exam_date - timedelta(
            weeks=settings.PLAN_CONSOLIDATION_WEEKS
        )
        learning_counts = Counter(
            item.week_index for item in reviews if item.due_date < final_start
        )
        final_counts = Counter(
            item.week_index for item in reviews if item.due_date >= final_start
        )

        self.assertEqual(max(learning_counts.values()), 4)
        self.assertEqual(max(final_counts.values()), 5)

    def test_every_mastered_topic_is_reviewed_in_consolidation_window(self):
        self.student.exam_date = timezone.localdate() + timedelta(weeks=38)
        self.student.save(update_fields=["exam_date"])
        nodes = [make_node(f"consolidate-{index}") for index in range(4)]
        for node in nodes:
            mastery = set_mastery(self.student, node, 90)
            mastery.retention_days = settings.PLAN_REVIEW_MAX_RETENTION_DAYS
            mastery.save(update_fields=["retention_days"])

        plan = build_study_plan(self.student)
        final_start = self.student.exam_date - timedelta(
            weeks=settings.PLAN_CONSOLIDATION_WEEKS
        )

        for node in nodes:
            self.assertTrue(
                plan.items.filter(
                    node=node,
                    item_type=StudyPlanItem.ItemType.REVIEW,
                    due_date__gte=final_start,
                    due_date__lt=self.student.exam_date,
                ).exists()
            )

    def test_exam_phase_drops_brand_new_topics_and_counts_them(self):
        self.student.weekly_hours = 1
        self.student.exam_date = timezone.localdate() + timedelta(weeks=10)
        self.student.save(update_fields=["weekly_hours", "exam_date"])
        cluster = None
        for index in range(8):
            node = make_node(
                f"in-progress-{index}",
                cluster=cluster,
                weight=10 - index,
                hours_estimate=1,
            )
            cluster = node.cluster
            set_mastery(self.student, node, 10)
        brand_new = make_node(
            "brand-new-exam", cluster=cluster, weight=0.01, hours_estimate=1
        )

        plan = build_study_plan(self.student)

        self.assertFalse(plan.items.filter(node=brand_new).exists())
        self.assertGreaterEqual(plan.unplanned_nodes, 1)
        self.assertFalse(plan.items.filter(due_date__gt=self.student.exam_date).exists())
