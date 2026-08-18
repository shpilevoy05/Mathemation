"""Переоценка плана: очередь идёт за прогрессом, а не за датой сборки."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.knowledge.models import KnowledgeDependency
from apps.knowledge.services import set_mastery
from apps.knowledge.tests import make_node, make_student
from apps.practice.tests import make_assignment

from .models import StudyPlanItem
from .services import (
    build_study_plan,
    carry_over_overdue,
    get_active_plan,
    reinsert_node,
    reprioritize_plan,
)
from .tasks import refresh_plans


class ReprioritizeTests(TestCase):
    def setUp(self):
        self.student = make_student("replan-student")
        self.cheap = make_node("cheap", weight=1.0)
        self.rich = make_node("rich", cluster=self.cheap.cluster, weight=3.0)
        for node in (self.cheap, self.rich):
            make_assignment(node, answer="1")
        build_study_plan(self.student)

    def pending_nodes(self) -> list[int]:
        return list(
            get_active_plan(self.student).items
            .exclude(status=StudyPlanItem.Status.DONE)
            .order_by("order")
            .values_list("node_id", flat=True)
        )

    def test_finished_items_survive_the_reprioritization(self):
        plan = get_active_plan(self.student)
        first = plan.items.order_by("order").first()
        first.status = StudyPlanItem.Status.DONE
        first.completed_at = timezone.now()
        first.save(update_fields=["status", "completed_at"])

        reprioritize_plan(self.student)

        plan.refresh_from_db()
        self.assertEqual(plan.items.filter(status=StudyPlanItem.Status.DONE).count(), 1)
        self.assertTrue(plan.items.filter(pk=first.pk).exists())

    def test_mastered_topic_leaves_the_queue(self):
        set_mastery(self.student, self.cheap, 95)

        reprioritize_plan(self.student)

        self.assertNotIn(self.cheap.id, self.pending_nodes())
        self.assertIn(self.rich.id, self.pending_nodes())

    def test_queue_follows_the_freshly_opened_prerequisite(self):
        locked = make_node("locked", cluster=self.cheap.cluster, weight=5.0)
        make_assignment(locked, answer="2")
        KnowledgeDependency.objects.create(
            node=locked, prerequisite=self.rich, min_mastery=70
        )
        reprioritize_plan(self.student)
        before = self.pending_nodes()

        set_mastery(self.student, self.rich, 80)
        reprioritize_plan(self.student)

        after = self.pending_nodes()
        # Пока пререквизит закрыт, дорогая тема стоит после него; как только он
        # освоен, она поднимается наверх — ради неё план и перестраивается.
        self.assertLess(before.index(self.rich.id), before.index(locked.id))
        self.assertEqual(after[0], locked.id)

    def test_plan_without_students_plan_is_skipped(self):
        other = make_student("no-plan-student")

        self.assertIsNone(reprioritize_plan(other))


class ScheduleTests(TestCase):
    def setUp(self):
        self.student = make_student("schedule-student")
        self.student.weekly_hours = 4
        self.node_short = make_node("short", exam_part=1)
        self.node_long = make_node("long", cluster=self.node_short.cluster, exam_part=2)
        for node in (self.node_short, self.node_long):
            make_assignment(node, answer="1")

    def test_heavy_topic_takes_more_of_the_week_budget(self):
        self.student.exam_date = None
        self.student.save(update_fields=["exam_date"])

        build_study_plan(self.student)

        weeks = {
            item.node_id: item.week_index
            for item in get_active_plan(self.student).items.all()
        }
        # Часть 2 стоит вдвое дороже по часам, поэтому две темы не помещаются
        # в одну неделю при бюджете 4 часа.
        self.assertNotEqual(weeks[self.node_short.id], weeks[self.node_long.id])

    def test_plan_never_runs_past_the_exam_date(self):
        self.student.exam_date = timezone.localdate() + timedelta(days=10)
        self.student.save(update_fields=["exam_date"])

        build_study_plan(self.student)

        due_dates = [
            item.due_date for item in get_active_plan(self.student).items.all()
        ]
        self.assertTrue(due_dates)
        self.assertTrue(all(date <= self.student.exam_date for date in due_dates))


class UrgentReworkTests(TestCase):
    def setUp(self):
        self.student = make_student("urgent-student")
        self.node = make_node("urgent-node")
        self.other = make_node("other-node", cluster=self.node.cluster)
        for node in (self.node, self.other):
            make_assignment(node, answer="1")
        build_study_plan(self.student)

    def test_returned_topic_goes_to_the_front_of_the_queue(self):
        returned = make_node("returned", cluster=self.node.cluster)

        item = reinsert_node(self.student, returned, reason="decay", description="")

        first = (
            get_active_plan(self.student).items
            .filter(status=StudyPlanItem.Status.PENDING)
            .order_by("order")
            .first()
        )
        self.assertEqual(first.pk, item.pk)
        self.assertEqual(item.due_date, timezone.localdate() + timedelta(days=1))


class CarryOverTests(TestCase):
    def setUp(self):
        self.student = make_student("overdue-student")
        node = make_node("overdue-node")
        make_assignment(node, answer="1")
        build_study_plan(self.student)

    def test_overdue_items_move_to_today(self):
        plan = get_active_plan(self.student)
        plan.items.update(due_date=timezone.localdate() - timedelta(days=5))

        moved = carry_over_overdue(self.student)

        self.assertEqual(moved, plan.items.count())
        self.assertFalse(
            plan.items.filter(due_date__lt=timezone.localdate()).exists()
        )

    def test_done_items_keep_their_date(self):
        plan = get_active_plan(self.student)
        stale = timezone.localdate() - timedelta(days=5)
        plan.items.update(due_date=stale, status=StudyPlanItem.Status.DONE)

        carry_over_overdue(self.student)

        self.assertTrue(plan.items.filter(due_date=stale).exists())

    def test_nightly_job_processes_active_plans(self):
        plan = get_active_plan(self.student)
        plan.items.update(due_date=timezone.localdate() - timedelta(days=2))

        processed = refresh_plans()

        self.assertEqual(processed, 1)
        self.assertFalse(plan.items.filter(due_date__lt=timezone.localdate()).exists())
