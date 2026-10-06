"""Переоценка плана: очередь идёт за прогрессом, а не за датой сборки."""
from datetime import timedelta
from unittest.mock import Mock, patch

from django.db import connection
from django.core.cache import cache
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.knowledge.models import KnowledgeDependency
from apps.knowledge.services import set_mastery
from apps.knowledge.tests import make_node, make_student
from apps.practice.tests import make_assignment

from .models import StudyPlanItem
from .services import (
    autocomplete_items_for_node,
    build_study_plan,
    carry_over_overdue,
    get_active_plan,
    move_item,
    order_pending_nodes,
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
        plan = get_active_plan(self.student)
        next_week = timezone.localdate() + timedelta(days=8)
        plan.items.update(due_date=next_week, week_index=1)
        set_mastery(self.student, self.cheap, 95)

        reprioritize_plan(self.student)

        plan = get_active_plan(self.student)
        self.assertFalse(
            plan.items.exclude(status=StudyPlanItem.Status.DONE).filter(
                node=self.cheap,
                item_type__in=(
                    StudyPlanItem.ItemType.LESSON,
                    StudyPlanItem.ItemType.PRACTICE,
                ),
            ).exists()
        )
        self.assertTrue(
            plan.items.exclude(status=StudyPlanItem.Status.DONE).filter(
                node=self.cheap, item_type=StudyPlanItem.ItemType.REVIEW
            ).exists()
        )
        self.assertIn(self.rich.id, self.pending_nodes())

    def test_queue_follows_the_freshly_opened_prerequisite(self):
        locked = make_node("locked", cluster=self.cheap.cluster, weight=5.0)
        make_assignment(locked, answer="2")
        KnowledgeDependency.objects.create(
            node=locked, prerequisite=self.rich, min_mastery=70
        )
        get_active_plan(self.student).items.update(
            due_date=timezone.localdate() + timedelta(days=8), week_index=1
        )
        reprioritize_plan(self.student)
        before = list(
            get_active_plan(self.student).items.filter(
                item_type=StudyPlanItem.ItemType.LESSON
            ).order_by("order").values_list("node_id", flat=True)
        )

        set_mastery(self.student, self.rich, 80)
        reprioritize_plan(self.student)

        after = list(
            get_active_plan(self.student).items.filter(
                item_type=StudyPlanItem.ItemType.LESSON
            ).order_by("order").values_list("node_id", flat=True)
        )
        # Пока пререквизит закрыт, дорогая тема стоит после него; как только он
        # освоен, она поднимается наверх — ради неё план и перестраивается.
        self.assertLess(before.index(self.rich.id), before.index(locked.id))
        self.assertEqual(after[0], locked.id)

    def test_plan_without_students_plan_is_skipped(self):
        other = make_student("no-plan-student")

        self.assertIsNone(reprioritize_plan(other))

    def test_manual_move_survives_nightly_refresh_and_autocomplete_rebuild(self):
        plan = get_active_plan(self.student)
        manual = plan.items.filter(node=self.rich).order_by("order").first()
        target = timezone.localdate() + timedelta(days=5)
        move_item(manual, target)

        refresh_plans()

        manual.refresh_from_db()
        self.assertEqual(manual.origin, StudyPlanItem.Origin.MANUAL)
        self.assertEqual(manual.due_date, target)

        set_mastery(self.student, self.cheap, 95)
        autocomplete_items_for_node(self.student, self.cheap)

        manual.refresh_from_db()
        self.assertEqual(manual.origin, StudyPlanItem.Origin.MANUAL)
        self.assertEqual(manual.due_date, target)

    def test_in_progress_item_survives_reprioritize(self):
        plan = get_active_plan(self.student)
        item = plan.items.order_by("order").first()
        item.status = StudyPlanItem.Status.IN_PROGRESS
        item.save(update_fields=["status"])

        reprioritize_plan(self.student)

        item.refresh_from_db()
        self.assertEqual(item.status, StudyPlanItem.Status.IN_PROGRESS)

    def test_kept_items_block_duplicate_node_type_pairs(self):
        plan = get_active_plan(self.student)
        manual = plan.items.order_by("order").first()
        move_item(manual, timezone.localdate() + timedelta(days=3))
        in_progress = (
            plan.items.exclude(pk=manual.pk)
            .filter(node=manual.node, item_type=StudyPlanItem.ItemType.PRACTICE)
            .first()
        )
        in_progress.status = StudyPlanItem.Status.IN_PROGRESS
        in_progress.save(update_fields=["status"])

        reprioritize_plan(self.student)

        pairs = list(
            get_active_plan(self.student).items
            .exclude(status=StudyPlanItem.Status.DONE)
            .values_list("node_id", "item_type")
        )
        self.assertEqual(len(pairs), len(set(pairs)))


class StablePlanTests(TestCase):
    def setUp(self):
        self.student = make_student("stable-plan-student")
        self.student.weekly_hours = 2
        self.student.exam_date = None
        self.student.save(update_fields=["weekly_hours", "exam_date"])
        self.nodes = []
        cluster = None
        for index in range(4):
            node = make_node(f"stable-{index}", cluster=cluster, hours_estimate=2)
            cluster = node.cluster
            make_assignment(node, answer="1")
            self.nodes.append(node)
        self.plan = build_study_plan(self.student)

    @staticmethod
    def _week_end(day):
        return day + timedelta(days=6 - day.weekday())

    def test_nightly_reprioritize_freezes_current_week_and_changes_future(self):
        today = timezone.localdate()
        week_end = self._week_end(today)
        frozen_before = list(
            self.plan.items.filter(due_date__lte=week_end)
            .order_by("order")
            .values_list("pk", "due_date", "order")
        )
        future = self.plan.items.filter(
            due_date__gt=week_end,
            item_type=StudyPlanItem.ItemType.LESSON,
        ).first()
        future_ids = set(
            self.plan.items.filter(due_date__gt=week_end).values_list("pk", flat=True)
        )
        set_mastery(self.student, future.node, 95)

        reprioritize_plan(self.student)

        self.assertEqual(
            list(
                self.plan.items.filter(pk__in=[row[0] for row in frozen_before])
                .order_by("order")
                .values_list("pk", "due_date", "order")
            ),
            frozen_before,
        )
        self.assertFalse(
            self.plan.items.filter(
                node=future.node,
                item_type__in=(
                    StudyPlanItem.ItemType.LESSON,
                    StudyPlanItem.ItemType.PRACTICE,
                ),
            ).exists()
        )
        self.assertFalse(
            self.plan.items.filter(pk__in=future_ids, due_date__gt=week_end).exists()
        )

    def test_daytime_mastery_closes_items_without_reordering_the_rest(self):
        target = self.nodes[0]
        untouched_before = list(
            self.plan.items.exclude(node=target)
            .order_by("pk")
            .values_list("pk", "due_date", "order", "status")
        )
        set_mastery(self.student, target, 95)

        autocomplete_items_for_node(self.student, target)

        self.assertEqual(
            list(
                self.plan.items.exclude(node=target)
                .order_by("pk")
                .values_list("pk", "due_date", "order", "status")
            ),
            untouched_before,
        )
        self.assertFalse(
            self.plan.items.filter(node=target).exclude(
                status=StudyPlanItem.Status.DONE
            ).exists()
        )

    def test_first_refresh_in_new_week_starts_regeneration_following_monday(self):
        today = timezone.localdate()
        next_monday = today + timedelta(days=7 - today.weekday())
        following_monday = next_monday + timedelta(days=7)
        current_node = self.nodes[0]
        self.plan.items.filter(node=current_node).update(
            due_date=next_monday, week_index=0
        )
        self.plan.items.exclude(node=current_node).update(
            due_date=following_monday, week_index=1
        )
        frozen_ids = set(
            self.plan.items.filter(node=current_node).values_list("pk", flat=True)
        )

        with patch("apps.planning.services.timezone.localdate", return_value=next_monday):
            reprioritize_plan(self.student)

        self.assertEqual(
            set(self.plan.items.filter(node=current_node).values_list("pk", flat=True)),
            frozen_ids,
        )
        regenerated = self.plan.items.filter(
            status=StudyPlanItem.Status.PENDING,
            origin=StudyPlanItem.Origin.PLAN,
        ).exclude(pk__in=frozen_ids)
        self.assertTrue(regenerated.exists())
        self.assertFalse(regenerated.filter(due_date__lt=following_monday).exists())

    def test_nightly_refresh_is_idempotent(self):
        def snapshot():
            return list(
                self.plan.items.order_by("order", "pk").values_list(
                    "node_id",
                    "item_type",
                    "due_date",
                    "week_index",
                    "order",
                    "status",
                    "origin",
                )
            )

        refresh_plans()
        first = snapshot()
        refresh_plans()

        self.assertEqual(snapshot(), first)

    def test_full_build_still_fills_current_week(self):
        today = timezone.localdate()
        week_end = self._week_end(today)

        self.assertTrue(
            self.plan.items.filter(due_date__gte=today, due_date__lte=week_end).exists()
        )


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

    def test_partly_mastered_topic_uses_less_weekly_budget(self):
        student = make_student("cost-student")
        student.weekly_hours = 6
        student.exam_date = timezone.localdate() + timedelta(days=14)
        student.save(update_fields=["weekly_hours", "exam_date"])
        zero = make_node("cost-zero", hours_estimate=4)
        partly = make_node("cost-partly", cluster=zero.cluster, hours_estimate=4)
        for node in (zero, partly):
            make_assignment(node, answer="1")
        set_mastery(student, zero, 0)
        set_mastery(student, partly, 60)

        plan = build_study_plan(student)

        weeks = {
            item.node_id: item.week_index
            for item in plan.items.filter(item_type=StudyPlanItem.ItemType.LESSON)
        }
        self.assertEqual(weeks[zero.id], weeks[partly.id])

    def test_recommended_hours_use_the_same_starting_level_costs(self):
        student = make_student("cost-advice-student")
        student.exam_date = timezone.localdate() + timedelta(days=7)
        student.save(update_fields=["exam_date"])
        set_mastery(student, self.node_short, 100)
        set_mastery(student, self.node_long, 100)
        zero = make_node("cost-advice-zero", hours_estimate=4)
        partly = make_node("cost-advice-partly", cluster=zero.cluster, hours_estimate=4)
        for node in (zero, partly):
            make_assignment(node, answer="1")
        set_mastery(student, zero, 0)
        set_mastery(student, partly, 60)

        from .services import recommended_weekly_hours

        self.assertEqual(recommended_weekly_hours(student), 6)

    def test_recommended_hours_query_count_does_not_grow_with_nodes(self):
        from .services import recommended_weekly_hours

        small = make_student("query-small")
        small.exam_date = timezone.localdate() + timedelta(days=21)
        small.save(update_fields=["exam_date"])
        small_node = make_node("query-small-node")
        make_assignment(small_node)

        large = make_student("query-large")
        large.exam_date = timezone.localdate() + timedelta(days=21)
        large.save(update_fields=["exam_date"])
        cluster = None
        for index in range(8):
            node = make_node(f"query-large-{index}", cluster=cluster)
            cluster = node.cluster
            make_assignment(node)

        with CaptureQueriesContext(connection) as small_queries:
            recommended_weekly_hours(small)
        with CaptureQueriesContext(connection) as large_queries:
            recommended_weekly_hours(large)
        self.assertEqual(len(small_queries), len(large_queries))

    def test_student_weekly_hours_override_trajectory_for_scheduling(self):
        from .models import Trajectory

        student = make_student("student-hours-student")
        student.weekly_hours = 4
        student.exam_date = timezone.localdate() + timedelta(days=14)
        student.save(update_fields=["weekly_hours", "exam_date"])
        set_mastery(student, self.node_short, 100)
        set_mastery(student, self.node_long, 100)
        trajectory = Trajectory.objects.create(
            slug="ten-hour-hint",
            title="10h",
            target_min=80,
            target_max=90,
            weekly_load_hours=10,
        )
        node_a = make_node("student-hours-a", hours_estimate=4)
        node_b = make_node("student-hours-b", cluster=node_a.cluster, hours_estimate=4)
        for node in (node_a, node_b):
            make_assignment(node, answer="1")
        from .models import TrajectoryTransition

        TrajectoryTransition.objects.create(student=student, to_trajectory=trajectory)

        plan = build_study_plan(student)

        weeks = {
            item.node_id: item.week_index
            for item in plan.items.filter(item_type=StudyPlanItem.ItemType.LESSON)
        }
        self.assertNotEqual(weeks[node_a.id], weeks[node_b.id])

    def test_planner_uses_exam_profile_weights_before_bank_volume(self):
        from apps.exams.models import ExamProfile, ExamTask, ExamTaskSkill

        student = make_student("profile-plan-student")
        set_mastery(student, self.node_short, 100)
        set_mastery(student, self.node_long, 100)
        light = make_node("profile-light")
        heavy = make_node("profile-heavy", cluster=light.cluster)
        for index in range(12):
            make_assignment(light, answer=str(index))
        make_assignment(heavy, answer="h")
        ExamProfile.objects.update(is_active=False)
        profile = ExamProfile.objects.create(
            year=2030,
            title="Planner profile",
            max_primary_score=5,
            primary_to_scaled=[0, 20, 40, 60, 80, 100],
            is_active=True,
        )
        light_task = ExamTask.objects.create(
            profile=profile, number=1, max_score=1, difficulty=3
        )
        heavy_task = ExamTask.objects.create(
            profile=profile, number=2, max_score=4, difficulty=3
        )
        ExamTaskSkill.objects.create(task=light_task, node=light)
        ExamTaskSkill.objects.create(task=heavy_task, node=heavy)

        ordered = order_pending_nodes(student)

        self.assertLess(
            [node.id for node in ordered].index(heavy.id),
            [node.id for node in ordered].index(light.id),
        )


class UrgentReworkTests(TestCase):
    def setUp(self):
        self.student = make_student("urgent-student")
        self.node = make_node("urgent-node")
        self.other = make_node("other-node", cluster=self.node.cluster)
        for node in (self.node, self.other):
            make_assignment(node, answer="1")
        self.plan = build_study_plan(self.student)

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
        self.assertEqual(item.origin, StudyPlanItem.Origin.URGENT)
        self.assertEqual(item.due_date, timezone.localdate() + timedelta(days=1))

    def test_existing_pending_topic_becomes_urgent_instead_of_duplicate(self):
        practice = self.plan.items.get(
            node=self.node, item_type=StudyPlanItem.ItemType.PRACTICE
        )
        old_due = practice.due_date

        item = reinsert_node(self.student, self.node, reason="decay", in_days=1)

        practice.refresh_from_db()
        self.assertEqual(item.pk, practice.pk)
        self.assertEqual(practice.origin, StudyPlanItem.Origin.URGENT)
        self.assertEqual(
            practice.due_date, min(old_due, timezone.localdate() + timedelta(days=1))
        )
        self.assertEqual(
            self.plan.items.filter(
                node=self.node, item_type=StudyPlanItem.ItemType.PRACTICE
            ).count(),
            1,
        )

    def test_urgent_item_survives_reprioritize_even_when_mastered(self):
        returned = make_node("mastered-returned", cluster=self.node.cluster)
        set_mastery(self.student, returned, 95)
        item = reinsert_node(
            self.student, returned, reason="decay", description="", in_days=0
        )

        reprioritize_plan(self.student)

        item.refresh_from_db()
        self.assertEqual(item.origin, StudyPlanItem.Origin.URGENT)
        first = (
            get_active_plan(self.student).items
            .exclude(status=StudyPlanItem.Status.DONE)
            .order_by("order")
            .first()
        )
        self.assertEqual(first.pk, item.pk)


class BuildCarryOverTests(TestCase):
    def setUp(self):
        self.student = make_student("build-carry-student")
        self.node = make_node("build-carry-node")
        self.other = make_node("build-carry-other", cluster=self.node.cluster)
        for node in (self.node, self.other):
            make_assignment(node, answer="1")
        self.plan = build_study_plan(self.student)

    def test_build_study_plan_carries_future_manual_and_urgent_items(self):
        manual = self.plan.items.get(
            node=self.node, item_type=StudyPlanItem.ItemType.LESSON
        )
        manual_date = timezone.localdate() + timedelta(days=4)
        move_item(manual, manual_date)
        urgent = reinsert_node(
            self.student,
            make_node("build-carry-urgent", cluster=self.node.cluster),
            reason="decay",
            in_days=0,
        )

        new_plan = build_study_plan(self.student, reason="manual")

        carried_manual = new_plan.items.get(
            node=self.node, item_type=StudyPlanItem.ItemType.LESSON
        )
        carried_urgent = new_plan.items.get(
            node=urgent.node, item_type=StudyPlanItem.ItemType.PRACTICE
        )
        self.assertEqual(carried_manual.origin, StudyPlanItem.Origin.MANUAL)
        self.assertEqual(carried_manual.due_date, manual_date)
        self.assertEqual(carried_urgent.origin, StudyPlanItem.Origin.URGENT)
        pairs = list(new_plan.items.values_list("node_id", "item_type"))
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_build_study_plan_does_not_carry_past_manual_item(self):
        manual = self.plan.items.get(
            node=self.node, item_type=StudyPlanItem.ItemType.LESSON
        )
        manual.origin = StudyPlanItem.Origin.MANUAL
        manual.due_date = timezone.localdate() - timedelta(days=1)
        manual.save(update_fields=["origin", "due_date"])

        new_plan = build_study_plan(self.student, reason="manual")

        item = new_plan.items.get(
            node=self.node, item_type=StudyPlanItem.ItemType.LESSON
        )
        self.assertEqual(item.origin, StudyPlanItem.Origin.PLAN)


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

    def test_nightly_job_warms_contract_cache(self):
        from apps.progress.services import plan_contract

        self.student.exam_date = timezone.localdate() + timedelta(days=90)
        self.student.save(update_fields=["exam_date"])
        cache.clear()
        fake_forecast = {
            "ceiling_score": 85,
            "unreachable_node_ids": [],
        }
        simulation = Mock(return_value=fake_forecast)
        with patch(
            "apps.progress.services._contract_ceiling_runner",
            return_value=simulation,
        ) as prepare:
            refresh_plans()
            calls_after_warm = simulation.call_count
            plan_contract(self.student)

        self.assertGreater(calls_after_warm, 0)
        self.assertEqual(simulation.call_count, calls_after_warm)
        self.assertEqual(prepare.call_count, 1)

    def test_contract_warm_failure_does_not_stop_other_students(self):
        other = make_student("warm-failure-other")
        other_node = make_node("warm-failure-node")
        make_assignment(other_node)
        build_study_plan(other)

        with (
            patch(
                "apps.progress.services.plan_contract",
                side_effect=RuntimeError("cache unavailable"),
            ) as warm,
            self.assertLogs("apps.planning.tasks", level="ERROR"),
        ):
            processed = refresh_plans()

        self.assertEqual(processed, 2)
        self.assertEqual(warm.call_count, 2)
