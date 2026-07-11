"""Deterministic graph ordering and greedy study selection."""
from collections import deque
from collections.abc import Sequence

from .dto import EdgeDTO, EngineParams, NodeState


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
    """Choose pending nodes by score gain per hour while respecting edges."""
    pending = [
        node for node in node_states if node.mastery < params.mastery_threshold
    ]
    # With a constant HOURS_PER_NODE, score/hour ordering is score-weight ordering.
    return topological_order(pending, edges)
