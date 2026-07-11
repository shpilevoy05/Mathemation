from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.content.models import Assignment, AssignmentSkillTag
from apps.knowledge.services import mastery_map
from apps.knowledge.tests import make_node, make_student
from apps.planning.models import PlanChangeLog, StudyPlanItem
from apps.planning.services import build_study_plan
from apps.practice.models import Attempt, MistakeBacklogItem, ReviewSchedule
from apps.practice.services import complete_review, submit_attempt


def make_assignment(node, answer="42", part=Assignment.Part.PART1):
    a = Assignment.objects.create(
        title=f"Задача {node.code}", statement="...", correct_answer=answer, exam_part=part
    )
    AssignmentSkillTag.objects.create(assignment=a, node=node)
    return a


class AttemptTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.node = make_node()
        self.assignment = make_assignment(self.node)

    def test_correct_attempt_updates_mastery_no_backlog(self):
        attempt = submit_attempt(self.student, self.assignment, "42", Attempt.Context.LESSON)
        self.assertTrue(attempt.is_correct)
        self.assertEqual(mastery_map(self.student)[self.node.id], 30.0)
        self.assertFalse(MistakeBacklogItem.objects.exists())

    def test_answer_normalization(self):
        attempt = submit_attempt(self.student, self.assignment, " 42 ", Attempt.Context.LESSON)
        self.assertTrue(attempt.is_correct)

    def test_part2_attempt_not_autochecked(self):
        a2 = make_assignment(self.node, answer="", part=Assignment.Part.PART2)
        attempt = submit_attempt(self.student, a2, "решение", Attempt.Context.LESSON)
        self.assertIsNone(attempt.is_correct)


class MistakeBacklogTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.node = make_node()
        self.assignment = make_assignment(self.node)

    def test_mistake_creates_backlog_and_intervals(self):
        submit_attempt(self.student, self.assignment, "wrong", Attempt.Context.LESSON)
        item = MistakeBacklogItem.objects.get()
        self.assertEqual(item.status, MistakeBacklogItem.Status.IN_REVIEW)
        intervals = list(item.reviews.values_list("interval_days", flat=True))
        self.assertEqual(sorted(intervals), [1, 3, 7, 30])
        today = timezone.localdate()
        self.assertEqual(
            item.reviews.order_by("due_date").first().due_date, today + timedelta(days=1)
        )

    def test_repeat_mistake_bumps_error_count(self):
        for _ in range(2):
            submit_attempt(self.student, self.assignment, "wrong", Attempt.Context.LESSON)
        item = MistakeBacklogItem.objects.get()
        self.assertEqual(item.error_count, 2)
        self.assertEqual(item.reviews.count(), 4)  # intervals not duplicated

    def test_frequent_mistakes_reinsert_topic_into_plan(self):
        build_study_plan(self.student)
        # Mark existing items done so reinsertion is observable.
        StudyPlanItem.objects.update(status=StudyPlanItem.Status.DONE)
        for _ in range(3):
            submit_attempt(self.student, self.assignment, "wrong", Attempt.Context.LESSON)
        self.assertTrue(
            StudyPlanItem.objects.filter(
                node=self.node, status=StudyPlanItem.Status.PENDING
            ).exists()
        )
        self.assertTrue(
            PlanChangeLog.objects.filter(
                reason=PlanChangeLog.Reason.FREQUENT_MISTAKES
            ).exists()
        )

    def test_review_flow_resolves_backlog(self):
        submit_attempt(self.student, self.assignment, "wrong", Attempt.Context.LESSON)
        item = MistakeBacklogItem.objects.get()
        for review in list(item.reviews.all()):
            complete_review(review, success=True)
        item.refresh_from_db()
        self.assertEqual(item.status, MistakeBacklogItem.Status.RESOLVED)

    def test_failed_review_reschedules(self):
        submit_attempt(self.student, self.assignment, "wrong", Attempt.Context.LESSON)
        item = MistakeBacklogItem.objects.get()
        first = item.reviews.first()
        complete_review(first, success=False)
        item.refresh_from_db()
        pending = item.reviews.filter(status=ReviewSchedule.Status.PENDING)
        self.assertEqual(pending.count(), 4)  # full ladder rescheduled
        self.assertEqual(item.status, MistakeBacklogItem.Status.IN_REVIEW)


class PracticeQueueTests(TestCase):
    """Перед новой темой подмешиваются 1-2 задачи на старые слабые места."""

    def setUp(self):
        self.student = make_student()
        self.old_node = make_node("old")
        self.new_node = make_node("new", cluster=self.old_node.cluster)
        self.old_assignment = make_assignment(self.old_node)
        self.new_assignment = make_assignment(self.new_node)

    def test_mixes_due_reviews_from_other_nodes(self):
        from apps.practice.services import practice_queue

        submit_attempt(self.student, self.old_assignment, "wrong", Attempt.Context.LESSON)
        # Сделаем первый повтор просроченным «на сегодня».
        review = ReviewSchedule.objects.filter(
            backlog_item__student=self.student
        ).first()
        review.due_date = timezone.localdate()
        review.save()

        queue = practice_queue(self.student, self.new_node)
        self.assertIn(self.old_assignment, queue["warmup"])
        self.assertLessEqual(len(queue["warmup"]), 2)
        self.assertIn(self.new_assignment, queue["new"])

    def test_own_node_mistakes_not_in_warmup(self):
        from apps.practice.services import practice_queue

        submit_attempt(self.student, self.new_assignment, "wrong", Attempt.Context.LESSON)
        review = ReviewSchedule.objects.first()
        review.due_date = timezone.localdate()
        review.save()
        queue = practice_queue(self.student, self.new_node)
        self.assertEqual(queue["warmup"], [])
