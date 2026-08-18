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

    Каждый узел тратит свои часы (`NodeState.hours`, иначе `hours_per_node`):
    тема второй части дороже короткой задачи первой, и потолок обязан это
    учитывать, иначе он обещает больше, чем ученик успеет. Возврат профиля
    оставляет перевод в баллы за пределами модуля.
    """
    pending = greedy_pending_nodes(node_states, edges, params)
    unlimited = days_left is None
    budget_hours = (
        0.0 if unlimited else max(days_left, 0) / 7.0 * max(weekly_hours, 0.0)
    )

    profile = {node.node_id: node.mastery for node in node_states}
    prerequisites = {node.node_id: [] for node in pending}
    for edge in edges:
        if edge.to_node_id in prerequisites:
            prerequisites[edge.to_node_id].append(edge)

    reachable = []
    unreachable = []
    spent_hours = 0.0
    for node in pending:
        requirements_met = all(
            profile.get(edge.from_node_id, 0.0) >= edge.min_mastery
            for edge in prerequisites[node.node_id]
        )
        cost = node.study_hours(params.hours_per_node)
        fits = unlimited or spent_hours + cost <= budget_hours
        if not fits or not requirements_met:
            unreachable.append(node)
            continue
        reachable.append(node)
        spent_hours += cost
        profile[node.node_id] = max(node.mastery, params.attainable_mastery)
    return CeilingResult(
        mastery_profile=profile,
        reachable_node_ids=tuple(node.node_id for node in reachable),
        unreachable_node_ids=tuple(node.node_id for node in unreachable),
    )
