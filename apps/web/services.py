"""Read-side composition for the server-rendered student cabinet."""

from datetime import timedelta

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.ai_mentor.models import AiHintMessage, AiHintSession
from apps.ai_mentor.services import mentor_available
from apps.content.models import Lesson, TheoryBlock
from apps.gamification.services import gamification_snapshot
from apps.knowledge.models import KnowledgeNode, TopicCluster
from apps.knowledge.services import apply_decay, node_states
from apps.mocks.models import MockExam, MockExamResult
from apps.planning.models import StudyPlanItem, TrajectoryTransition
from apps.planning.services import get_active_plan, items_for_period
from apps.practice.models import Attempt, MistakeBacklogItem
from apps.practice.services import due_reviews, practice_queue
from apps.progress.models import ProgressSnapshot
from apps.progress.services import ceiling_forecast

from .labels import ERROR_TYPE_LABELS


NODE_STATE_LABELS = {
    "locked": "закрыто",
    "available": "можно начинать",
    "in_progress": "в процессе",
    "mastered": "освоено",
    "decayed": "подзабылось",
}
POINT_TYPE_LABELS = {
    "lesson": "Урок",
    "practice": "Практика",
    "review": "Отработка",
    "mock": "Пробник",
}
BACKLOG_STATUS_LABELS = {
    "open": "открыта",
    "in_review": "на интервальных повторах",
    "resolved": "закрыта",
}


def dashboard_context(student):
    apply_decay(student)
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    plan = get_active_plan(student)
    trajectory = plan.trajectory if plan and plan.trajectory_id else None
    return {
        "today_items": items_for_period(student, today, today),
        "week_items": items_for_period(student, week_start, week_start + timedelta(days=6)),
        "due_reviews": due_reviews(student),
        "snapshot": ProgressSnapshot.objects.filter(student=student).first(),
        "has_plan": plan is not None,
        "trajectory": trajectory,
        "major_changes": (
            plan.change_logs.filter(is_major=True, acknowledged=False) if plan else []
        ),
        "trajectory_transitions": TrajectoryTransition.objects.filter(
            student=student, acknowledged=False
        ).select_related("from_trajectory", "to_trajectory"),
        "forecast": ceiling_forecast(student) if plan else None,
        "gamification": gamification_snapshot(student),
    }


def knowledge_map_context(student, overlay=False):
    apply_decay(student)
    states = node_states(student)
    unreachable = set()
    if overlay:
        unreachable = set(ceiling_forecast(student)["unreachable_node_ids"])
    clusters = []
    for cluster in TopicCluster.objects.prefetch_related("nodes"):
        nodes = []
        for node in cluster.nodes.all():
            state = states[node.id]
            nodes.append(
                {
                    "id": node.id,
                    "title": node.title,
                    "ege_task_numbers": node.ege_task_numbers,
                    "mastery": state["mastery"],
                    "state": state["state"],
                    "state_label": NODE_STATE_LABELS[state["state"]],
                    "decay_percent": state["decay_percent"],
                    "last_practiced_at": state["last_practiced_at"],
                    "reachable_by_exam": node.id not in unreachable,
                    "unmet_conditions": state["unmet_conditions"],
                }
            )
        clusters.append({"title": cluster.title, "color": cluster.color, "nodes": nodes})
    return {"clusters": clusters, "ceiling_overlay": overlay}


def knowledge_node_context(student, node_id):
    node = get_object_or_404(
        KnowledgeNode.objects.select_related("cluster").prefetch_related(
            "lessons__theory_blocks"
        ),
        pk=node_id,
    )
    state = node_states(student)[node.id]
    mistakes = []
    for item in MistakeBacklogItem.objects.filter(student=student, node=node).select_related(
        "assignment"
    ):
        mistakes.append(
            {
                "assignment": item.assignment.title,
                "status": BACKLOG_STATUS_LABELS[item.status],
                "error_type": ERROR_TYPE_LABELS[item.error_type],
                "error_count": item.error_count,
                "created_at": item.created_at,
            }
        )
    theory = [
        block
        for lesson in node.lessons.all()
        for block in lesson.theory_blocks.all()
    ]
    return {
        "node": node,
        "node_state": {**state, "label": NODE_STATE_LABELS[state["state"]]},
        "theory_blocks": theory,
        "mistakes": mistakes,
    }


def track_context(student):
    states = node_states(student)
    open_mistake_nodes = set(
        MistakeBacklogItem.objects.filter(student=student)
        .exclude(status=MistakeBacklogItem.Status.RESOLVED)
        .values_list("node_id", flat=True)
    )
    clusters = []
    current_assigned = False
    for cluster in TopicCluster.objects.prefetch_related("nodes__lessons"):
        points = []
        cluster_has_mistakes = False
        for node in cluster.nodes.all():
            state = states[node.id]["state"]
            for lesson in node.lessons.all():
                point = _track_point("lesson", lesson.title, state, node.id)
                if not current_assigned and state in {"available", "in_progress", "decayed"}:
                    point["is_current"] = True
                    current_assigned = True
                points.append(point)
            points.append(_track_point("practice", f"Практика: {node.title}", state, node.id))
            cluster_has_mistakes = cluster_has_mistakes or node.id in open_mistake_nodes
        if cluster_has_mistakes:
            points.append(_track_point("review", f"Отработка: {cluster.title}", "available"))
        clusters.append({"title": cluster.title, "color": cluster.color, "points": points})
    mocks = [
        _track_point("mock", mock.title, "available")
        for mock in MockExam.objects.filter(is_active=True)
    ]
    return {"track_clusters": clusters, "mock_points": mocks}


def _track_point(point_type, title, state, node_id=None):
    return {
        "type": point_type,
        "type_label": POINT_TYPE_LABELS[point_type],
        "title": title,
        "state": state,
        "state_label": NODE_STATE_LABELS.get(state, state),
        "node_id": node_id,
        "is_done": state == "mastered",
        "is_current": False,
    }


def lesson_context(student, node_id, attempt_context=Attempt.Context.LESSON):
    node = get_object_or_404(KnowledgeNode, pk=node_id)
    video_lessons = list(Lesson.objects.filter(node=node).exclude(video_url=""))
    for lesson in video_lessons:
        lesson.video_is_embeddable = lesson.video_url.startswith("https://")
    queue = practice_queue(student, node)
    tasks = [
        {"assignment": assignment, "phase": "warmup", "phase_label": "Старое слабое место"}
        for assignment in queue["warmup"]
    ] + [
        {"assignment": assignment, "phase": "new", "phase_label": "Новая тема"}
        for assignment in queue["new"]
    ]
    sessions = {
        session.assignment_id: session
        for session in AiHintSession.objects.filter(
            student=student,
            assignment_id__in=[task["assignment"].id for task in tasks],
        ).prefetch_related(
            Prefetch(
                "messages",
                queryset=AiHintMessage.objects.filter(is_blocked=False),
            )
        )
    }
    for task in tasks:
        task["hint_session"] = sessions.get(task["assignment"].id)
    return {
        "node": node,
        "video_lessons": video_lessons,
        "theory_blocks": TheoryBlock.objects.filter(lesson__node=node).select_related("lesson"),
        "tasks": tasks,
        "attempt_context": attempt_context,
        "mentor_enabled": mentor_available(attempt_context),
    }


def practice_backlog_context(student):
    items = MistakeBacklogItem.objects.filter(student=student).select_related(
        "assignment", "node"
    )
    prepared = [
        {
            "assignment": item.assignment.title,
            "node": item.node.title,
            "status": BACKLOG_STATUS_LABELS[item.status],
            "error_type": ERROR_TYPE_LABELS[item.error_type],
            "error_count": item.error_count,
            "resolved_at": item.resolved_at,
            "is_resolved": item.status == MistakeBacklogItem.Status.RESOLVED,
        }
        for item in items
    ]
    return {
        "backlog_items": [item for item in prepared if not item["is_resolved"]],
        "resolved_items": [item for item in prepared if item["is_resolved"]],
        "due_reviews": due_reviews(student),
    }


def forecast_context(student):
    return {"forecast": ceiling_forecast(student)}


MOCK_STATUS_LABELS = {
    MockExamResult.Status.IN_PROGRESS: "в процессе",
    MockExamResult.Status.PART1_CHECKED: "на проверке ч.2",
    MockExamResult.Status.COMPLETED: "завершён",
}


def mocks_context(student):
    exams = list(MockExam.objects.filter(is_active=True).prefetch_related("assignments"))
    latest = {}
    for result in (
        MockExamResult.objects.filter(student=student)
        .select_related("exam")
        .order_by("exam_id", "-started_at")
    ):
        latest.setdefault(result.exam_id, result)
    active = []
    for exam in exams:
        result = latest.get(exam.id)
        active.append({"exam": exam, "latest_result": result})
    history = [
        {"result": result, "status_label": MOCK_STATUS_LABELS[result.status]}
        for result in MockExamResult.objects.filter(student=student)
        .select_related("exam")
        .order_by("-started_at")
    ]
    return {"active_mocks": active, "mock_history": history}


def mock_run_context(student, result_id):
    result = get_object_or_404(
        MockExamResult.objects.select_related("exam").prefetch_related("exam__assignments"),
        pk=result_id,
        student=student,
    )
    return {
        "result": result,
        "part1_assignments": result.exam.assignments.filter(exam_part=1),
        "part2_assignments": result.exam.assignments.filter(exam_part=2),
    }


def mock_result_context(student, result_id):
    result = get_object_or_404(
        MockExamResult.objects.select_related("exam").prefetch_related(
            "expert_reviews__assignment"
        ),
        pk=result_id,
        student=student,
    )
    reviews = list(result.expert_reviews.all())
    for review in reviews:
        review.sla_deadline = review.created_at + timedelta(hours=review.sla_hours)
    return {
        "result": result,
        "status_label": MOCK_STATUS_LABELS[result.status],
        "reviews": reviews,
    }


def parent_context(parent):
    from apps.progress.services import build_parent_report

    child = parent.children.select_related("user").first()
    if child is None:
        return {"child": None}
    report = build_parent_report(child)
    payload = report.payload
    distribution = [
        {"label": ERROR_TYPE_LABELS.get(error_type, error_type), "count": count}
        for error_type, count in payload.get("error_type_distribution", {}).items()
    ]
    return {
        "child": child,
        "report": report,
        "report_data": payload,
        "error_distribution": distribution,
    }
