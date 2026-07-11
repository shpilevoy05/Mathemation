"""Database-free tests for the pure learning engine."""
from datetime import datetime, timezone

from django.test import SimpleTestCase

from apps.engine.ceiling import simulate_ceiling
from apps.engine.decay import decayed_mastery
from apps.engine.dto import EdgeDTO, EngineParams, NodeState, TaskWeight
from apps.engine.forecast import expected_primary, scaled_score
from apps.engine.mastery import bkt_update
from apps.engine.planner import topological_order


PARAMS = EngineParams(
    mastery_threshold=70,
    decay_grace_days=14,
    decay_rate_per_day=0.02,
    max_primary_score=32,
    hours_per_node=2,
    attainable_mastery=85,
    bkt_alpha=0.3,
    forecast_calibration_alpha=0.3,
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


class ForecastEngineTests(SimpleTestCase):
    def test_simple_half_mastered_profile(self):
        states = [node(1, 100), node(2, 0)]
        tasks = [
            TaskWeight(1, (1,), 1, 1),
            TaskWeight(2, (2,), 1, 1),
        ]
        primary = expected_primary(states, tasks, PARAMS)
        self.assertEqual(primary, 16)
        self.assertEqual(scaled_score(primary, list(range(33))), 16)


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


class PlannerEngineTests(SimpleTestCase):
    def test_prerequisites_precede_dependants(self):
        ordered = topological_order(
            [node(2, weight=10), node(1)],
            [EdgeDTO(from_node_id=1, to_node_id=2)],
        )
        self.assertEqual([state.node_id for state in ordered], [1, 2])

