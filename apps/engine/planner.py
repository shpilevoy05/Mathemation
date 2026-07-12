"""Deterministic graph ordering and greedy study selection."""
from collections import deque
from collections.abc import Sequence

from .dto import EdgeDTO, EngineParams, NodeState, TaskWeight
from .forecast import expected_primary


def topological_order(
    node_states: Sequence[NodeState], edges: Sequence[EdgeDTO]
) -> list[NodeState]:
    """Put prerequisites first and prefer higher score weight among ties."""
    by_id = {node.node_id: node for node in node_states}
    ids = set(by_id)
    incoming = {node_id: set() for node_id in ids}
    outgoing = {node_id: set() for node_id in ids}
    for edge in edges:
        if edge.from_node_id in ids and edge.to_node_id in ids:
            if by_id[edge.from_node_id].mastery >= edge.min_mastery:
                continue
            incoming[edge.to_node_id].add(edge.from_node_id)
            outgoing[edge.from_node_id].add(edge.to_node_id)

    score_weight = lambda node_id: -(
        by_id[node_id].weight * by_id[node_id].cluster_weight
    )
    ready = sorted(
        (node_id for node_id, prerequisites in incoming.items() if not prerequisites),
        key=score_weight,
    )
    queue = deque(ready)
    result: list[NodeState] = []
    emitted: set[int] = set()
    while queue:
        node_id = queue.popleft()
        if node_id in emitted:
            continue
        result.append(by_id[node_id])
        emitted.add(node_id)
        for dependant_id in sorted(outgoing[node_id], key=score_weight):
            incoming[dependant_id].discard(node_id)
            if not incoming[dependant_id]:
                queue.append(dependant_id)

    # Knowledge graphs should be acyclic; retain source order defensively.
    result.extend(node for node in node_states if node.node_id not in emitted)
    return result


def greedy_pending_nodes(
    node_states: Sequence[NodeState],
    edges: Sequence[EdgeDTO],
    params: EngineParams,
) -> list[NodeState]:
    """Backward-compatible planner entry point using node score weights."""
    tasks = [
        TaskWeight(
            assignment_id=node.node_id,
            node_ids=(node.node_id,),
            max_score=max(node.weight * node.cluster_weight, 0.0),
            difficulty=3.0,
        )
        for node in node_states
    ]
    return greedy_plan(node_states, edges, tasks, params)


def greedy_plan(
    node_states: Sequence[NodeState],
    edges: Sequence[EdgeDTO],
    task_weights: Sequence[TaskWeight],
    params: EngineParams,
) -> list[NodeState]:
    """Greedily maximize expected primary-score gain per study hour."""
    by_id = {node.node_id: node for node in node_states}
    required_prerequisites = {
        edge.from_node_id
        for edge in edges
        if edge.from_node_id in by_id
        and by_id[edge.from_node_id].mastery < edge.min_mastery
    }
    pending_ids = {
        node.node_id
        for node in node_states
        if node.mastery < params.mastery_threshold
        or node.node_id in required_prerequisites
    }
    source_order = {node.node_id: index for index, node in enumerate(node_states)}
    projected = {node.node_id: node.mastery for node in node_states}
    prerequisites = {node_id: [] for node_id in pending_ids}
    for edge in edges:
        if edge.to_node_id in prerequisites:
            prerequisites[edge.to_node_id].append(edge)

    result: list[NodeState] = []
    remaining = set(pending_ids)
    while remaining:
        available = [
            node_id
            for node_id in remaining
            if all(
                projected.get(edge.from_node_id, 0.0) >= edge.min_mastery
                for edge in prerequisites[node_id]
            )
        ]
        if not available:
            break
        current_states = [
            NodeState(
                node_id=node.node_id,
                mastery=projected[node.node_id],
                last_practiced_at=node.last_practiced_at,
                weight=node.weight,
                cluster_weight=node.cluster_weight,
            )
            for node in node_states
        ]
        baseline = expected_primary(current_states, task_weights, params)

        def priority(node_id: int) -> tuple[float, float, int]:
            candidate_states = [
                NodeState(
                    node_id=state.node_id,
                    mastery=(
                        max(state.mastery, params.attainable_mastery)
                        if state.node_id == node_id
                        else state.mastery
                    ),
                    last_practiced_at=state.last_practiced_at,
                    weight=state.weight,
                    cluster_weight=state.cluster_weight,
                )
                for state in current_states
            ]
            gain = expected_primary(candidate_states, task_weights, params) - baseline
            hours = params.hours_per_node if params.hours_per_node > 0 else 1.0
            node = by_id[node_id]
            return (
                -(gain / hours),
                -(node.weight * node.cluster_weight),
                source_order[node_id],
            )

        selected_id = min(available, key=priority)
        result.append(by_id[selected_id])
        remaining.remove(selected_id)
        projected[selected_id] = max(projected[selected_id], params.attainable_mastery)

    # Cycles, missing prerequisites and unattainable thresholds remain defensive.
    result.extend(
        node
        for node in node_states
        if node.node_id in remaining
    )
    return result
