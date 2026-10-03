"""Database-free tests for the pure learning engine."""
from datetime import datetime, timezone

from django.test import SimpleTestCase

from apps.engine.ceiling import simulate_ceiling
from apps.engine.decay import decayed_mastery, next_intervals
from apps.engine.dto import EdgeDTO, EngineParams, NodeState, TaskWeight
from apps.engine.forecast import expected_primary, probability_correct, scaled_score
from apps.engine.mastery import bkt_update
from apps.engine.planner import greedy_plan, topological_order


PARAMS = EngineParams(
    mastery_threshold=70,
    decay_grace_days=14,
    decay_rate_per_day=0.02,
    max_primary_score=32,
    hours_per_node=2,
    attainable_mastery=85,
    bkt_alpha=0.3,
    forecast_calibration_alpha=0.3,
    theta_scale=6,
    b_step=1.2,
    default_discrimination=1,
    guess=0,
    review_intervals_days=(1, 3, 7, 30),
    review_ease=1.6,
    min_review_interval_days=1,
    max_review_interval_days=60,
)


def node(node_id: int, mastery: float = 0, weight: float = 1) -> NodeState:
    return NodeState(
        node_id=node_id,
        mastery=mastery,
        last_practiced_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        weight=weight,
        cluster_weight=1,
    )


class MasteryEngineTests(SimpleTestCase):
    def test_correct_answer_increases_and_wrong_answer_decreases_mastery(self):
        self.assertGreater(bkt_update(50, True, 1, PARAMS), 50)
        self.assertLess(bkt_update(50, False, 1, PARAMS), 50)


class DecayEngineTests(SimpleTestCase):
    def test_mastery_decreases_over_time_after_grace_period(self):
        early = decayed_mastery(90, 15, PARAMS)
        late = decayed_mastery(90, 45, PARAMS)
        self.assertLess(late, early)

    def test_adaptive_intervals_shrink_stretch_and_stay_bounded(self):
        failed = next_intervals(1, 0, PARAMS)
        successful = next_intervals(0, 1, PARAMS)
        self.assertTrue(all(a <= b for a, b in zip(failed, PARAMS.review_intervals_days)))
        self.assertTrue(all(a >= b for a, b in zip(successful, PARAMS.review_intervals_days)))
        minimum = next_intervals(20, 0, PARAMS)
        maximum = next_intervals(0, 20, PARAMS)
        self.assertTrue(all(interval == 1 for interval in minimum))
        self.assertTrue(all(interval <= 60 for interval in maximum))
        self.assertIn(60, maximum)


class ForecastEngineTests(SimpleTestCase):
    def test_simple_half_mastered_profile(self):
        states = [node(1, 100), node(2, 0)]
        tasks = [
            TaskWeight(1, (1,), 1, 3),
            TaskWeight(2, (2,), 1, 3),
        ]
        primary = expected_primary(states, tasks, PARAMS)
        self.assertAlmostEqual(primary, 16)
        self.assertEqual(scaled_score(primary, list(range(33))), 16)

    def test_irt_probability_is_monotonic_and_bounded(self):
        low = probability_correct(20, 3, PARAMS)
        high = probability_correct(80, 3, PARAMS)
        easy = probability_correct(50, 1, PARAMS)
        hard = probability_correct(50, 5, PARAMS)
        self.assertLess(low, high)
        self.assertGreater(easy, hard)
        self.assertTrue(all(0 <= value <= 1 for value in (low, high, easy, hard)))

    def test_expected_score_never_decreases_with_mastery(self):
        task = [TaskWeight(1, (1,), 2, 4)]
        self.assertLessEqual(
            expected_primary([node(1, 30)], task, PARAMS),
            expected_primary([node(1, 70)], task, PARAMS),
        )


class CeilingEngineTests(SimpleTestCase):
    def test_more_hours_never_lower_the_ceiling_profile(self):
        states = [node(1), node(2), node(3)]
        slow = simulate_ceiling(states, [], 14, 1, PARAMS)
        fast = simulate_ceiling(states, [], 14, 8, PARAMS)
        self.assertTrue(
            all(
                fast.mastery_profile[node_id] >= mastery
                for node_id, mastery in slow.mastery_profile.items()
            )
        )
        self.assertLessEqual(
            len(fast.unreachable_node_ids), len(slow.unreachable_node_ids)
        )

    def test_child_stays_unreachable_when_edge_threshold_cannot_be_reached(self):
        result = simulate_ceiling(
            [node(2, weight=10), node(1, mastery=55)],
            [EdgeDTO(from_node_id=1, to_node_id=2, min_mastery=90)],
            days_left=14,
            weekly_hours=20,
            params=PARAMS,
        )
        self.assertEqual(result.reachable_node_ids, (1,))
        self.assertEqual(result.unreachable_node_ids, (2,))

    def test_prerequisite_above_global_but_below_edge_threshold_is_studied_first(self):
        result = simulate_ceiling(
            [node(2, weight=10), node(1, mastery=75)],
            [EdgeDTO(from_node_id=1, to_node_id=2, min_mastery=80)],
            days_left=14,
            weekly_hours=20,
            params=PARAMS,
        )
        self.assertEqual(result.reachable_node_ids, (1, 2))


class PlannerEngineTests(SimpleTestCase):
    def test_higher_score_gain_is_planned_first_and_order_is_stable(self):
        states = [node(1), node(2), node(3)]
        tasks = [
            TaskWeight(1, (1,), 1, 3),
            TaskWeight(2, (2,), 4, 3),
            TaskWeight(3, (3,), 1, 3),
        ]
        first = greedy_plan(states, [], tasks, PARAMS)
        second = greedy_plan(states, [], tasks, PARAMS)
        self.assertEqual([state.node_id for state in first], [2, 1, 3])
        self.assertEqual(first, second)

    def test_greedy_plan_keeps_prerequisite_first(self):
        ordered = greedy_plan(
            [node(2, weight=10), node(1)],
            [EdgeDTO(1, 2)],
            [TaskWeight(2, (2,), 10, 3), TaskWeight(1, (1,), 1, 3)],
            PARAMS,
        )
        self.assertEqual([state.node_id for state in ordered], [1, 2])

    def test_prerequisites_precede_dependants(self):
        ordered = topological_order(
            [node(2, weight=10), node(1)],
            [EdgeDTO(from_node_id=1, to_node_id=2)],
        )
        self.assertEqual([state.node_id for state in ordered], [1, 2])

    def test_unsatisfied_edge_threshold_always_keeps_prerequisite_first(self):
        for threshold in (50, 80, 100):
            with self.subTest(threshold=threshold):
                ordered = topological_order(
                    [node(2, weight=10), node(1, mastery=threshold - 1)],
                    [EdgeDTO(1, 2, min_mastery=threshold)],
                )
                self.assertEqual([state.node_id for state in ordered], [1, 2])
