"""Deterministic attainable-mastery simulation."""
from collections.abc import Sequence

from .dto import CeilingResult, EdgeDTO, EngineParams, NodeState
from .planner import greedy_pending_nodes


def simulate_ceiling(
    node_states: Sequence[NodeState],
    edges: Sequence[EdgeDTO],
    days_left: int | None,
    weekly_hours: float,
    params: EngineParams,
) -> CeilingResult:
    """Simulate which pending nodes fit and return the resulting profile.

    The current production model allocates a fixed number of hours per node and
    raises every reachable node to its configured attainable mastery. Returning
    the profile keeps score-table conversion outside this module.
    """
    pending = greedy_pending_nodes(node_states, edges, params)
    if days_left is None:
        can_take = len(pending)
    else:
        budget_hours = max(days_left, 0) / 7.0 * max(weekly_hours, 0.0)
        can_take = int(budget_hours // params.hours_per_node)

    reachable = pending[:can_take]
    unreachable = pending[can_take:]
    profile = {node.node_id: node.mastery for node in node_states}
    for node in reachable:
        profile[node.node_id] = max(node.mastery, params.attainable_mastery)
    return CeilingResult(
        mastery_profile=profile,
        reachable_node_ids=tuple(node.node_id for node in reachable),
        unreachable_node_ids=tuple(node.node_id for node in unreachable),
    )

