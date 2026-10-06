"""Exam-profile adapters shared by forecast and planning."""
from dataclasses import dataclass
from typing import Iterable

from django.conf import settings

from apps.content.models import Assignment
from apps.engine.dto import TaskWeight

from .models import ExamProfile


@dataclass(frozen=True, slots=True)
class TaskWeightSet:
    weights: list[TaskWeight]
    profile: ExamProfile | None


def active_exam_profile() -> ExamProfile | None:
    return ExamProfile.active()


def max_primary_score(profile: ExamProfile | None = None) -> float:
    profile = profile if profile is not None else active_exam_profile()
    if profile is not None:
        return float(profile.max_primary_score)
    return float(settings.MAX_PRIMARY_SCORE)


def profile_task_weights(
    profile: ExamProfile, node_ids: set[int] | None = None
) -> list[TaskWeight]:
    weights = []
    for task in profile.tasks.prefetch_related("skills").all():
        skills = [
            skill for skill in task.skills.all()
            if node_ids is None or skill.node_id in node_ids
        ]
        if not skills:
            continue
        weights.append(
            TaskWeight(
                assignment_id=task.id,
                node_ids=tuple(skill.node_id for skill in skills),
                node_weights=tuple(float(skill.weight) for skill in skills),
                max_score=float(task.max_score),
                difficulty=float(task.difficulty),
                discrimination=settings.IRT_DEFAULT_DISCRIMINATION,
            )
        )
    return weights


def task_weights_for_nodes(nodes: Iterable) -> TaskWeightSet:
    nodes = list(nodes)
    node_ids = {node.id for node in nodes}
    profile = active_exam_profile()
    if profile is not None:
        profile_weights = profile_task_weights(profile, node_ids)
        if profile_weights:
            return TaskWeightSet(profile_weights, profile)

    assignments = list(
        Assignment.objects.filter(skill_tags__node_id__in=node_ids)
        .prefetch_related("skill_tags")
        .distinct()
    )
    weights = []
    for assignment in assignments:
        tags = list(assignment.skill_tags.all())
        weights.append(
            TaskWeight(
                assignment_id=assignment.id,
                node_ids=tuple(tag.node_id for tag in tags),
                node_weights=tuple(float(tag.weight) for tag in tags),
                max_score=float(assignment.max_score),
                difficulty=float(assignment.difficulty),
                discrimination=settings.IRT_DEFAULT_DISCRIMINATION,
            )
        )
    if weights:
        return TaskWeightSet(weights, None)

    return TaskWeightSet(
        [
            TaskWeight(
                assignment_id=node.id,
                node_ids=(node.id,),
                max_score=float(node.weight * node.cluster.exam_weight),
                difficulty=3.0,
            )
            for node in nodes
        ],
        None,
    )
