from django.test import TestCase

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
    maybe_transition,
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
        self.assertNotIn(self.basic.id, self._node_order(plan))
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

        build_study_plan(self.student)
        plan = rebuild_after_inactivity(self.student, idle_days=14)
        self.assertIsNotNone(plan)
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

    def test_poor_mock_moves_down_and_rebuilds_plan(self):
        assign_trajectory(self.student, 84)
        build_study_plan(self.student)
        transition = maybe_transition(
            self.student,
            PlanChangeLog.Reason.POOR_MOCK,
            {"scaled_score": 70, "node_ids": [self.node.id]},
        )

        self.assertIsNotNone(transition)
        self.assertEqual(transition.from_trajectory.slug, "score84")
        self.assertEqual(transition.to_trajectory.slug, "score78")
        self.assertTrue(transition.recovery_actions)
        self.assertIn(
            f'Вернуть в план: "{self.node.title}".',
            transition.recovery_actions,
        )
        self.assertNotIn(str(self.node.id), transition.recovery_actions[0])
        self.assertEqual(get_active_plan(self.student).trajectory.slug, "score78")
        self.assertTrue(
            PlanChangeLog.objects.filter(
                reason=PlanChangeLog.Reason.POOR_MOCK, is_major=True
            ).exists()
        )
        self.assertTrue(
            Event.objects.filter(event_type=Event.Type.TRAJECTORY_TRANSITION).exists()
        )

    def test_recovery_actions_from_details_deduplicate_and_skip_missing_nodes(self):
        second_node = make_node("second-trajectory-node", cluster=self.node.cluster)
        assign_trajectory(self.student, 84)
        build_study_plan(self.student)

        transition = maybe_transition(
            self.student,
            PlanChangeLog.Reason.INACTIVITY,
            {"idle_days": 14, "node_ids": [self.node.id, self.node.id, 999999]},
        )

        recovery = transition.recovery_actions[0]
        self.assertEqual(recovery.count(f'"{self.node.title}"'), 1)
        self.assertNotIn("999999", recovery)
        self.assertNotIn(f'"{second_node.title}"', recovery)

    def test_recovery_actions_from_plan_deduplicate_nodes_and_use_titles(self):
        second_node = make_node("second-trajectory-node", cluster=self.node.cluster)
        assign_trajectory(self.student, 84)
        build_study_plan(self.student)

        transition = maybe_transition(
            self.student,
            PlanChangeLog.Reason.INACTIVITY,
            {"idle_days": 14},
        )

        recovery = transition.recovery_actions[0]
        self.assertEqual(recovery.count(f'"{self.node.title}"'), 1)
        self.assertEqual(recovery.count(f'"{second_node.title}"'), 1)
        self.assertNotIn(str(self.node.id), recovery)
        self.assertNotIn(str(second_node.id), recovery)

    def test_acknowledge_transition_api(self):
        assign_trajectory(self.student, 84)
        build_study_plan(self.student)
        transition = maybe_transition(
            self.student,
            PlanChangeLog.Reason.INACTIVITY,
            {"idle_days": 14},
        )
        self.client.force_login(self.student.user)
        response = self.client.post(
            f"/api/trajectory/transitions/{transition.id}/ack/"
        )
        self.assertEqual(response.status_code, 200)
        transition.refresh_from_db()
        self.assertTrue(transition.acknowledged)

    def test_three_errors_on_node_move_trajectory_down(self):
        from apps.practice.models import Attempt
        from apps.practice.services import submit_attempt
        from apps.practice.tests import make_assignment

        assignment = make_assignment(self.node, answer="42")
        assign_trajectory(self.student, 84)
        build_study_plan(self.student)
        StudyPlanItem.objects.update(status=StudyPlanItem.Status.DONE)
        for _ in range(3):
            submit_attempt(self.student, assignment, "wrong", Attempt.Context.LESSON)
        transition = TrajectoryTransition.objects.get(
            student=self.student,
            from_trajectory__slug="score84",
            to_trajectory__slug="score78",
        )
        self.assertIn(PlanChangeLog.Reason.FREQUENT_MISTAKES, transition.reasons)

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
