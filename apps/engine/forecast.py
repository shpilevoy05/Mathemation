"""IRT-based expected primary and scaled score calculations."""
from collections.abc import Sequence
import math

from .dto import EngineParams, NodeState, TaskWeight


def probability_correct(
    mastery: float,
    difficulty: float,
    params: EngineParams,
    discrimination: float | None = None,
) -> float:
    """Return a numerically stable 2PL probability for one assignment."""
    theta = (min(max(float(mastery), 0.0), 100.0) / 100.0 - 0.5) * params.theta_scale
    b = (min(max(float(difficulty), 1.0), 5.0) - 3.0) * params.b_step
    a = params.default_discrimination if discrimination is None else discrimination
    exponent = float(a) * (theta - b)
    if exponent >= 0:
        logistic = 1.0 / (1.0 + math.exp(-min(exponent, 709.0)))
    else:
        exp_value = math.exp(max(exponent, -709.0))
        logistic = exp_value / (1.0 + exp_value)
    guess = min(max(float(params.guess), 0.0), 1.0)
    return min(max(guess + (1.0 - guess) * logistic, 0.0), 1.0)


def expected_primary(
    node_states: Sequence[NodeState],
    task_weights: Sequence[TaskWeight],
    params: EngineParams,
) -> float:
    """Return normalized Σ P(correct | mastery, IRT) × assignment max score."""
    mastery_by_id = {state.node_id: state.mastery for state in node_states}
    if task_weights:
        total_weight = sum(max(task.max_score, 0.0) for task in task_weights)
        if not total_weight:
            return 0.0
        expected_score = 0.0
        for task in task_weights:
            values = [mastery_by_id.get(node_id, 0.0) for node_id in task.node_ids]
            if task.node_weights and len(task.node_weights) == len(values):
                positive_weights = [max(float(weight), 0.0) for weight in task.node_weights]
                weight_sum = sum(positive_weights)
                mastery = (
                    sum(value * weight for value, weight in zip(values, positive_weights))
                    / weight_sum
                    if weight_sum
                    else 0.0
                )
            else:
                mastery = sum(values) / len(values) if values else 0.0
            probability = probability_correct(
                mastery, task.difficulty, params, task.discrimination
            )
            expected_score += probability * max(task.max_score, 0.0)
    else:
        total_weight = sum(
            max(state.weight * state.cluster_weight, 0.0) for state in node_states
        )
        if not total_weight:
            return 0.0
        expected_score = sum(
            probability_correct(state.mastery, 3.0, params)
            * max(state.weight * state.cluster_weight, 0.0)
            for state in node_states
        )
    normalized = expected_score / total_weight * params.max_primary_score
    return min(max(normalized, 0.0), params.max_primary_score)


def scaled_score(primary: float, primary_to_scaled_table: Sequence[int]) -> int:
    """Map a primary score through the supplied annual conversion table."""
    if not primary_to_scaled_table:
        raise ValueError("primary_to_scaled_table must not be empty")
    index = min(max(int(round(primary)), 0), len(primary_to_scaled_table) - 1)
    return int(primary_to_scaled_table[index])
