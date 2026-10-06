from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.knowledge.models import KnowledgeDependency, TopicCluster
from apps.knowledge.services import set_mastery
from apps.knowledge.tests import make_node, make_student
from apps.events.models import Event
from apps.planning.models import (
    PlanChangeLog,
    StudyPlanItem,
    Trajectory,
    TrajectoryTransition,
)
from apps.planning.services import (
    assign_trajectory,
    build_study_plan,
    get_active_plan,
    log_plan_change,
    reinsert_node,
)


class StudyPlanTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.cluster = TopicCluster.objects.create(title="Алгебра")
        self.basic = make_node("basic", cluster=self.cluster)
        self.advanced = make_node("advanced", cluster=self.cluster)
        KnowledgeDependency.objects.create(node=self.advanced, prerequisite=self.basic)

    def _node_order(self, plan):
        seen = []
        for item in plan.items.all():
            if item.node_id not in seen:
                seen.append(item.node_id)
        return seen

    def test_prerequisites_come_first(self):
        plan = build_study_plan(self.student)
        order = self._node_order(plan)
        self.assertLess(order.index(self.basic.id), order.index(self.advanced.id))

    def test_mastered_nodes_skipped(self):
        set_mastery(self.student, self.basic, 90)
        plan = build_study_plan(self.student)
        self.assertFalse(
            plan.items.filter(
                node=self.basic,
                item_type__in=(
                    StudyPlanItem.ItemType.LESSON,
                    StudyPlanItem.ItemType.PRACTICE,
                ),
            ).exists()
        )
        self.assertTrue(
            plan.items.filter(
                node=self.basic, item_type=StudyPlanItem.ItemType.REVIEW
            ).exists()
        )
        self.assertIn(self.advanced.id, self._node_order(plan))

    def test_each_node_gets_lesson_and_practice(self):
        plan = build_study_plan(self.student)
        types = set(
            plan.items.filter(node=self.basic).values_list("item_type", flat=True)
        )
        self.assertEqual(
            types, {StudyPlanItem.ItemType.LESSON, StudyPlanItem.ItemType.PRACTICE}
        )

    def test_rebuild_archives_previous_plan(self):
        first = build_study_plan(self.student)
        second = build_study_plan(self.student)
        first.refresh_from_db()
        self.assertEqual(first.status, "archived")
        self.assertEqual(get_active_plan(self.student).id, second.id)

    def test_higher_weight_scheduled_earlier(self):
        heavy = make_node("heavy", cluster=self.cluster, weight=5.0)
        plan = build_study_plan(self.student)
        order = self._node_order(plan)
        self.assertEqual(order[0], heavy.id)

    def test_rebuild_after_inactivity_logs_major_change(self):
        from apps.planning.models import PlanChangeLog
        from apps.planning.services import rebuild_after_inactivity

        old_plan = build_study_plan(self.student)
        plan = rebuild_after_inactivity(self.student, idle_days=14)
        self.assertIsNotNone(plan)
        self.assertNotEqual(plan.id, old_plan.id)
        self.assertFalse(TrajectoryTransition.objects.exists())
        change = PlanChangeLog.objects.get(reason=PlanChangeLog.Reason.INACTIVITY)
        self.assertTrue(change.is_major)
        self.assertFalse(change.acknowledged)
        # Снижение показываем фактом, без упрёка: в тексте есть прогноз.
        self.assertIn("прогноз", change.description.lower())

    def test_rebuild_after_inactivity_skips_students_without_plan(self):
        from apps.planning.services import rebuild_after_inactivity

        self.assertIsNone(rebuild_after_inactivity(self.student, idle_days=14))


class TrajectoryTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.node = make_node("trajectory-node")

    def test_assignment_by_target_score(self):
        trajectory = assign_trajectory(self.student, 84)
        self.assertEqual(trajectory.slug, "score84")
        transition = TrajectoryTransition.objects.get(student=self.student)
        self.assertIsNone(transition.from_trajectory)
        self.assertEqual(transition.to_trajectory, trajectory)
        self.assertTrue(
            Event.objects.filter(event_type=Event.Type.TRAJECTORY_ASSIGNED).exists()
        )

    def test_score_above_90_uses_top_trajectory(self):
        self.assertEqual(assign_trajectory(self.student, 97).slug, "score90")

    def test_acknowledge_transition_api(self):
        assign_trajectory(self.student, 84)
        build_study_plan(self.student)
        transition = TrajectoryTransition.objects.create(
            student=self.student,
            to_trajectory=Trajectory.objects.get(slug="score84"),
            reasons=[PlanChangeLog.Reason.INACTIVITY],
        )
        self.client.force_login(self.student.user)
        response = self.client.post(
            f"/api/trajectory/transitions/{transition.id}/ack/"
        )
        self.assertEqual(response.status_code, 200)
        transition.refresh_from_db()
        self.assertTrue(transition.acknowledged)

    def test_previous_evidence_version_uses_breakdown_without_trigger_sentence(self):
        from apps.progress.services import transition_explanation

        trajectory = assign_trajectory(self.student, 84)
        transition = TrajectoryTransition.objects.create(
            student=self.student,
            to_trajectory=trajectory,
            reasons=[PlanChangeLog.Reason.FREQUENT_MISTAKES],
            evidence={
                "mistake_count": 5,
                "period_days": 7,
                "threshold": 3,
                "topics": [{"title": self.node.title, "count": 5}],
                "error_types": [{"label": "тип уточняется", "count": 5}],
            },
        )

        explanation = transition_explanation(transition)

        self.assertEqual(
            explanation,
            [f"За последние 7 дней больше всего ошибок в темах: {self.node.title} — 5."],
        )

    def test_old_transition_explanation_uses_human_label(self):
        from apps.progress.services import transition_explanation

        trajectory = assign_trajectory(self.student, 84)
        transition = TrajectoryTransition.objects.create(
            student=self.student,
            to_trajectory=trajectory,
            reasons=[PlanChangeLog.Reason.FREQUENT_MISTAKES],
        )

        self.assertEqual(transition_explanation(transition), ["частые ошибки"])

    def test_trajectory_api_uses_conditional_wording(self):
        assign_trajectory(self.student, 84)
        build_study_plan(self.student)
        self.client.force_login(self.student.user)
        response = self.client.get("/api/trajectory/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slug"], "score84")
        self.assertIn("при текущем темпе", response.json()["message"].lower())

    def test_target_score_api_switches_trajectory_and_rebuilds_plan(self):
        self.student.target_score = 84
        self.student.save(update_fields=["target_score"])
        assign_trajectory(self.student, 84)
        old_plan = build_study_plan(self.student)
        self.client.force_login(self.student.user)

        response = self.client.post(
            "/api/me/target/", {"target_score": 90}, content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.target_score, 90)
        self.assertEqual(response.json()["trajectory"]["slug"], "score90")
        new_plan = get_active_plan(self.student)
        self.assertNotEqual(new_plan.id, old_plan.id)
        self.assertEqual(new_plan.target_score, 90)
        self.assertEqual(new_plan.trajectory.slug, "score90")
        change = PlanChangeLog.objects.get(
            plan=new_plan, reason=PlanChangeLog.Reason.MANUAL
        )
        self.assertTrue(change.is_major)
        self.assertIn("Целевой балл изменён на 90", change.description)
        event = Event.objects.get(event_type=Event.Type.TARGET_SCORE_CHANGED)
        self.assertEqual(event.payload["old"], 84)
        self.assertEqual(event.payload["new"], 90)
        self.assertEqual(event.payload["trajectory_id"], new_plan.trajectory_id)

    def test_target_score_api_keeps_plan_within_same_trajectory(self):
        self.student.target_score = 84
        self.student.save(update_fields=["target_score"])
        assign_trajectory(self.student, 84)
        plan = build_study_plan(self.student)
        rebuild_events = Event.objects.filter(event_type=Event.Type.PLAN_REBUILT).count()
        self.client.force_login(self.student.user)

        response = self.client.post(
            "/api/me/target/", {"target_score": 86}, content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["trajectory_changed"])
        self.assertEqual(response.json()["trajectory"]["slug"], "score84")
        self.assertEqual(get_active_plan(self.student).id, plan.id)
        self.assertEqual(
            Event.objects.filter(event_type=Event.Type.PLAN_REBUILT).count(),
            rebuild_events,
        )
        self.assertFalse(
            PlanChangeLog.objects.filter(reason=PlanChangeLog.Reason.MANUAL).exists()
        )

    def test_target_score_api_rejects_values_outside_range(self):
        self.client.force_login(self.student.user)
        for target_score in (39, 101):
            with self.subTest(target_score=target_score):
                response = self.client.post(
                    "/api/me/target/",
                    {"target_score": target_score},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("target_score", response.json())


class PlanChangeLogDeduplicationTests(TestCase):
    """Карточка изменений плана не зашумляется повторами."""

    def setUp(self):
        from apps.knowledge.models import TopicCluster
        from apps.knowledge.tests import make_node, make_student

        self.student = make_student("dedup-student")
        self.cluster = TopicCluster.objects.create(title="Алгебра")
        self.first_node = make_node("dedup-first", cluster=self.cluster)
        self.second_node = make_node("dedup-second", cluster=self.cluster)
        self.plan = build_study_plan(self.student)

    def _reinsert(self, node, is_major=False):
        return reinsert_node(
            self.student, node,
            reason=PlanChangeLog.Reason.FREQUENT_MISTAKES,
            description=f"Ошибка по узлу {node.title}.",
            is_major=is_major,
        )

    def _logs(self, node=None):
        query = PlanChangeLog.objects.filter(
            plan=self.plan, reason=PlanChangeLog.Reason.FREQUENT_MISTAKES
        )
        return query.filter(node=node) if node is not None else query

    def test_same_node_within_a_day_does_not_duplicate(self):
        self._reinsert(self.first_node)
        self._reinsert(self.first_node)
        self.assertEqual(self._logs(self.first_node).count(), 1)

    def test_other_node_gets_its_own_entry(self):
        self._reinsert(self.first_node)
        self._reinsert(self.second_node)
        self.assertEqual(self._logs().count(), 2)

    def test_entry_older_than_a_day_does_not_block_a_new_one(self):
        self._reinsert(self.first_node)
        PlanChangeLog.objects.update(
            created_at=timezone.now() - timedelta(days=1, seconds=1)
        )
        self._reinsert(self.first_node)
        self.assertEqual(self._logs(self.first_node).count(), 2)

    def test_major_change_always_creates_an_entry(self):
        log_plan_change(
            self.student, reason=PlanChangeLog.Reason.INACTIVITY,
            description="Перестроил план.", is_major=True,
        )
        log_plan_change(
            self.student, reason=PlanChangeLog.Reason.INACTIVITY,
            description="Перестроил план.", is_major=True,
        )
        self.assertEqual(
            PlanChangeLog.objects.filter(
                reason=PlanChangeLog.Reason.INACTIVITY, is_major=True
            ).count(),
            2,
        )

    def test_repeated_mistakes_do_not_flood_the_card(self):
        from apps.practice.models import Attempt
        from apps.practice.services import submit_attempt
        from apps.practice.tests import make_assignment

        assignment = make_assignment(self.first_node, answer="42")
        for _ in range(5):
            submit_attempt(self.student, assignment, "неверно", Attempt.Context.LESSON)
        self.assertLessEqual(self._logs(self.first_node).count(), 1)


class PlanAutocompleteTests(TestCase):
    """План закрывается сам по факту работы ученика."""

    def setUp(self):
        from apps.knowledge.services import set_mastery
        from apps.practice.tests import make_assignment

        self.student = make_student("autocomplete-student")
        self.cluster = TopicCluster.objects.create(title="Алгебра")
        self.node = make_node("auto-node", cluster=self.cluster)
        self.assignment = make_assignment(self.node, answer="42")
        self.plan = build_study_plan(self.student)
        self.set_mastery = set_mastery

    def _items(self, item_type):
        return self.plan.items.filter(node=self.node, item_type=item_type)

    def test_correct_answer_closes_the_lesson_item(self):
        from apps.practice.models import Attempt
        from apps.practice.services import submit_attempt

        lesson_item = self._items(StudyPlanItem.ItemType.LESSON).first()
        self.assertEqual(lesson_item.status, StudyPlanItem.Status.PENDING)

        submit_attempt(self.student, self.assignment, "42", Attempt.Context.LESSON)

        lesson_item.refresh_from_db()
        self.assertEqual(lesson_item.status, StudyPlanItem.Status.DONE)

    def test_practice_item_waits_for_mastery_threshold(self):
        from apps.practice.models import Attempt
        from apps.practice.services import submit_attempt

        submit_attempt(self.student, self.assignment, "42", Attempt.Context.LESSON)
        practice_item = self._items(StudyPlanItem.ItemType.PRACTICE).first()
        practice_item.refresh_from_db()
        self.assertEqual(practice_item.status, StudyPlanItem.Status.PENDING)

        self.set_mastery(self.student, self.node, 90)
        submit_attempt(self.student, self.assignment, "42", Attempt.Context.LESSON)

        practice_item.refresh_from_db()
        self.assertEqual(practice_item.status, StudyPlanItem.Status.DONE)

    def test_wrong_answer_does_not_close_anything(self):
        from apps.practice.models import Attempt
        from apps.practice.services import submit_attempt

        submit_attempt(self.student, self.assignment, "неверно", Attempt.Context.LESSON)
        statuses = set(
            self.plan.items.filter(node=self.node).values_list("status", flat=True)
        )
        self.assertEqual(statuses, {StudyPlanItem.Status.PENDING})

    def test_autocompletion_advances_the_weekly_quest(self):
        from apps.gamification.models import WeeklyQuest
        from apps.practice.models import Attempt
        from apps.practice.services import submit_attempt

        submit_attempt(self.student, self.assignment, "42", Attempt.Context.LESSON)
        quest = WeeklyQuest.objects.filter(
            student=self.student, quest_type=WeeklyQuest.QuestType.FINISH_PLAN_ITEMS
        ).first()
        self.assertIsNotNone(quest)
        self.assertGreaterEqual(quest.progress_count, 1)

    def test_successful_review_closes_the_review_item(self):
        from apps.practice.models import Attempt, ReviewSchedule
        from apps.practice.services import complete_review, submit_attempt

        submit_attempt(self.student, self.assignment, "неверно", Attempt.Context.LESSON)
        review_item = StudyPlanItem.objects.create(
            plan=self.plan, node=self.node,
            item_type=StudyPlanItem.ItemType.REVIEW, order=999,
        )
        for review in ReviewSchedule.objects.filter(backlog_item__node=self.node):
            complete_review(review, success=True)

        review_item.refresh_from_db()
        self.assertEqual(review_item.status, StudyPlanItem.Status.DONE)

    def test_completion_is_idempotent(self):
        from apps.planning.services import autocomplete_items_for_node
        from apps.practice.models import Attempt
        from apps.practice.services import submit_attempt

        submit_attempt(self.student, self.assignment, "42", Attempt.Context.LESSON)
        first = self._items(StudyPlanItem.ItemType.LESSON).first()
        first.refresh_from_db()
        completed_at_first = first.status

        self.assertEqual(autocomplete_items_for_node(self.student, self.node), [])
        first.refresh_from_db()
        self.assertEqual(first.status, completed_at_first)


class WeeklyCapacityTests(TestCase):
    """Неделя вмещает столько занятий, сколько человек успевает."""

    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.knowledge.tests import make_node, make_student, set_mastery

        self.student = make_student(target_score=80)
        self.student.weekly_hours = 4
        self.student.exam_date = timezone.localdate() + timedelta(days=14)
        self.student.save(update_fields=["weekly_hours", "exam_date"])
        cluster = None
        for index in range(6):
            node = make_node(f"cap-{index}", cluster=cluster, hours_estimate=4)
            cluster = node.cluster
            set_mastery(self.student, node, 10)

    def test_week_holds_only_what_fits(self):
        from apps.planning.services import build_study_plan

        plan = build_study_plan(self.student)

        # Четыре часа в неделю и темы по четыре часа: одна тема в неделю.
        by_week = {}
        for item in plan.items.all():
            by_week.setdefault(item.week_index, set()).add(item.node_id)
        self.assertTrue(all(len(nodes) == 1 for nodes in by_week.values()))

    def test_plan_stops_at_the_exam(self):
        from apps.planning.services import build_study_plan

        plan = build_study_plan(self.student)

        # Две недели до экзамена — дальше план не заходит.
        self.assertLessEqual(max(item.week_index for item in plan.items.all()), 1)
        self.assertTrue(all(item.due_date <= self.student.exam_date for item in plan.items.all()))

    def test_what_does_not_fit_is_counted(self):
        from apps.planning.services import build_study_plan

        plan = build_study_plan(self.student)

        # Шесть тем, помещается две: остальное честно не запланировано.
        self.assertEqual(plan.unplanned_nodes, 4)

    def test_more_hours_fit_more_topics(self):
        from apps.planning.services import build_study_plan

        self.student.weekly_hours = 12
        self.student.save(update_fields=["weekly_hours"])

        plan = build_study_plan(self.student)

        self.assertLess(plan.unplanned_nodes, 4)

    def test_without_an_exam_date_everything_is_planned(self):
        from apps.planning.services import build_study_plan

        self.student.exam_date = None
        self.student.save(update_fields=["exam_date"])

        plan = build_study_plan(self.student)

        # Горизонта нет — откладывать нечего.
        self.assertEqual(plan.unplanned_nodes, 0)
