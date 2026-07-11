"""Expected primary and scaled score calculations."""
from collections.abc import Sequence

from .dto import EngineParams, NodeState, TaskWeight


def expected_primary(
    node_states: Sequence[NodeState],
    task_weights: Sequence[TaskWeight],
    params: EngineParams,
) -> float:
    """Return the current weighted-mastery primary-score estimate.

    Adapters may express the current node weighting as one synthetic task per
    node. This keeps the pre-engine forecast formula exactly reproducible while
    leaving the boundary ready for real assignment/IRT probabilities later.
    """
    mastery_by_id = {state.node_id: state.mastery for state in node_states}
    if task_weights:
        total_weight = sum(max(task.max_score, 0.0) for task in task_weights)
        if not total_weight:
            return 0.0
        weighted_mastery = 0.0
        for task in task_weights:
            values = [mastery_by_id.get(node_id, 0.0) for node_id in task.node_ids]
            probability = sum(values) / len(values) if values else 0.0
            weighted_mastery += probability * max(task.max_score, 0.0)
    else:
        total_weight = sum(
            max(state.weight * state.cluster_weight, 0.0) for state in node_states
        )
        if not total_weight:
            return 0.0
        weighted_mastery = sum(
            state.mastery * max(state.weight * state.cluster_weight, 0.0)
            for state in node_states
        )
    return (weighted_mastery / total_weight) / 100.0 * params.max_primary_score


def scaled_score(primary: float, primary_to_scaled_table: Sequence[int]) -> int:
    """Map a primary score through the supplied annual conversion table."""
    if not primary_to_scaled_table:
        raise ValueError("primary_to_scaled_table must not be empty")
    index = min(max(int(round(primary)), 0), len(primary_to_scaled_table) - 1)
    return int(primary_to_scaled_table[index])

