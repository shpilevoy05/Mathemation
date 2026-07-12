"""Read-side composition for the server-rendered student cabinet."""

from datetime import timedelta
from pathlib import Path

from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

from apps.ai_mentor.models import AiHintMessage, AiHintSession
from apps.ai_mentor.services import mentor_available
from apps.content.models import Assignment, Lesson, TheoryBlock
from apps.expert_review.models import ExpertReviewRequest
from apps.gamification.services import gamification_snapshot
from apps.knowledge.models import KnowledgeDependency, KnowledgeNode, TopicCluster
from apps.knowledge.services import apply_decay, node_states
from apps.mocks.models import MockExam, MockExamResult
from apps.planning.models import StudyPlanItem, TrajectoryTransition
from apps.planning.services import get_active_plan, items_for_period
from apps.practice.models import Attempt, MistakeBacklogItem
from apps.practice.services import due_reviews, practice_queue
from apps.progress.models import ProgressSnapshot
from apps.progress.services import ceiling_forecast

from .labels import ERROR_TYPE_LABELS


def expert_queue_context(user):
    """Compose the expert queue, SLA metrics and recent mentor escalations."""
    now = timezone.now()
    pending = list(
        ExpertReviewRequest.objects.filter(status=ExpertReviewRequest.Status.SUBMITTED)
        .select_related("student__user", "assignment", "mock_result")
    )
    for review in pending:
        review.sla_deadline = review.created_at + timedelta(hours=review.sla_hours)
        review.is_overdue = review.sla_deadline < now
        review.sla_hours_left = (review.sla_deadline - now).total_seconds() / 3600
        review.sla_tone = (
            "danger" if review.is_overdue else
            "warning" if review.sla_hours_left < 12 else "success"
        )
        review.age_hours = max(0, int((now - review.created_at).total_seconds() // 3600))
    pending.sort(key=lambda item: (not item.is_overdue, item.sla_deadline))

    escalations = list(
        AiHintSession.objects.filter(
            escalated_to_expert=True,
            created_at__gte=now - timedelta(days=14),
        )
        .select_related("student__user", "assignment")
        .prefetch_related("messages")
        .order_by("-created_at")
    )
    return {
        "pending_reviews": pending,
        "pending_count": len(pending),
        "overdue_count": sum(item.is_overdue for item in pending),
        "reviewed_last_7d": ExpertReviewRequest.objects.filter(
            reviewed_at__gte=now - timedelta(days=7)
        ).count(),
        "escalations": escalations,
    }


def expert_review_context(review_id):
    """Prepare one submitted review and all choices used by the verdict form."""
    review = get_object_or_404(
        ExpertReviewRequest.objects.select_related("student__user", "assignment")
        .prefetch_related("assignment__skill_tags__node__cluster"),
        pk=review_id,
        status=ExpertReviewRequest.Status.SUBMITTED,
    )
    primary_nodes = [tag.node for tag in review.assignment.skill_tags.all()]
    primary_ids = {node.id for node in primary_nodes}
    cluster_ids = {node.cluster_id for node in primary_nodes}
    other_nodes = KnowledgeNode.objects.filter(cluster_id__in=cluster_ids).exclude(
        pk__in=primary_ids
    )
    suffix = Path(review.solution_file.name).suffix.lower()
    return {
        "review": review,
        "criteria": range(1, review.assignment.max_score + 1),
        "error_types": [
            {"value": value, "label": ERROR_TYPE_LABELS[value]}
            for value in MistakeBacklogItem.ErrorType.values
            if value != MistakeBacklogItem.ErrorType.UNKNOWN
        ],
        "primary_nodes": primary_nodes,
        "other_nodes": other_nodes,
        "solution_is_image": suffix in {".jpg", ".jpeg", ".png", ".webp"},
    }


def methodist_context():
    """Compose content health counters and a cluster-oriented graph read model."""
    assignments_without_solution = list(
        Assignment.objects.filter(reference_solution="").order_by("title")
    )
    lessons_without_content = list(
        Lesson.objects.annotate(theory_count=Count("theory_blocks"))
        .filter(theory_count=0, video_url="")
        .order_by("title")
    )
    nodes_without_assignments = list(
        KnowledgeNode.objects.annotate(assignment_count=Count("assignments", distinct=True))
        .filter(assignment_count=0)
        .order_by("cluster__order", "order")
    )

    clusters = list(
        TopicCluster.objects.prefetch_related(
            Prefetch(
                "nodes",
                queryset=KnowledgeNode.objects.annotate(
                    lesson_count=Count("lessons", distinct=True),
                    assignment_count=Count("assignments", distinct=True),
                ).prefetch_related(
                    Prefetch(
                        "dependencies",
                        queryset=KnowledgeDependency.objects.select_related("prerequisite"),
                    )
                ),
            )
        )
    )
    for cluster in clusters:
        for node in cluster.nodes.all():
            node.ui_prerequisites = ", ".join(
                f"{dependency.prerequisite.code} ≥{dependency.min_mastery}%"
                for dependency in node.dependencies.all()
            ) or "—"

    lesson_totals = Lesson.objects.aggregate(
        total=Count("id"),
        with_video=Count("id", filter=~Q(video_url="")),
    )
    return {
        "node_count": KnowledgeNode.objects.count(),
        "lesson_count": lesson_totals["total"],
        "video_lesson_count": lesson_totals["with_video"],
        "assignment_count": Assignment.objects.count(),
        "content_gap_count": (
            len(assignments_without_solution)
            + len(lessons_without_content)
            + len(nodes_without_assignments)
        ),
        "assignments_without_solution": assignments_without_solution,
        "lessons_without_content": lessons_without_content,
        "nodes_without_assignments": nodes_without_assignments,
        "content_clusters": clusters,
    }


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
PLAN_STATUS_LABELS = {
    StudyPlanItem.Status.PENDING: "Запланировано",
    StudyPlanItem.Status.IN_PROGRESS: "В процессе",
    StudyPlanItem.Status.DONE: "Выполнено",
}


def xp_progress_percent(xp, level):
    level_start_xp = 100 * (level - 1) ** 2
    level_end_xp = 100 * level**2
    percent = round((xp - level_start_xp) * 100 / (level_end_xp - level_start_xp))
    return max(0, min(100, percent))


def journey_percent(start_score, predicted_score, target_score):
    if start_score is None:
        return 0
    score_range = target_score - start_score
    if not score_range:
        return 100 if predicted_score >= target_score else 0
    percent = round((predicted_score - start_score) * 100 / score_range)
    return max(0, min(100, percent))


def gauge_metrics(score):
    gauge_dash = 251.2
    clamped_score = max(0, min(100, score or 0))
    return {
        "dash": "251.2",
        "offset": f"{gauge_dash * (1 - clamped_score / 100):.2f}",
    }


def _prepare_plan_items(items):
    prepared = list(items)
    for item in prepared:
        item.ui_type_label = POINT_TYPE_LABELS[item.item_type]
        item.ui_status_label = PLAN_STATUS_LABELS[item.status]
    return prepared


def dashboard_context(student):
    apply_decay(student)
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    plan = get_active_plan(student)
    trajectory = plan.trajectory if plan and plan.trajectory_id else None
    snapshot = ProgressSnapshot.objects.filter(student=student).first()
    forecast = ceiling_forecast(student) if plan else None
    gamification = gamification_snapshot(student)
    level = gamification["level"]
    level_start_xp = 100 * (level - 1) ** 2
    level_end_xp = 100 * level**2
    gamification = {
        **gamification,
        "level_start_xp": level_start_xp,
        "level_end_xp": level_end_xp,
        "xp_progress_percent": xp_progress_percent(gamification["xp"], level),
    }
    score_journey_percent = journey_percent(
        snapshot.start_score if snapshot else None,
        snapshot.predicted_score if snapshot else 0,
        student.target_score,
    )
    return {
        "today_items": _prepare_plan_items(items_for_period(student, today, today)),
        "week_items": _prepare_plan_items(
            items_for_period(student, week_start, week_start + timedelta(days=6))
        ),
        "due_reviews": due_reviews(student),
        "snapshot": snapshot,
        "target_score": student.target_score,
        "has_plan": plan is not None,
        "trajectory": trajectory,
        "major_changes": (
            plan.change_logs.filter(is_major=True, acknowledged=False) if plan else []
        ),
        "trajectory_transitions": TrajectoryTransition.objects.filter(
            student=student, acknowledged=False
        ).select_related("from_trajectory", "to_trajectory"),
        "forecast": forecast,
        "gamification": gamification,
        "has_diagnostic": snapshot is not None and snapshot.start_score is not None,
        "journey_percent": score_journey_percent,
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
                    "unmet_conditions": [
                        {
                            **condition,
                            "current_mastery_percent": max(
                                0, min(100, round(float(condition["current_mastery"])))
                            ),
                        }
                        for condition in state["unmet_conditions"]
                    ],
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
    position = 0
    for cluster in TopicCluster.objects.prefetch_related("nodes__lessons"):
        points = []
        cluster_has_mistakes = False
        for node in cluster.nodes.all():
            state_data = states[node.id]
            for lesson in node.lessons.all():
                point = _track_point(
                    "lesson", lesson.title, state_data, position, node.id
                )
                if not current_assigned and state_data["state"] in {
                    "available", "in_progress", "decayed"
                }:
                    _make_current(point)
                    current_assigned = True
                points.append(point)
                position += 1
            point = _track_point(
                "practice", f"Практика: {node.title}", state_data, position, node.id
            )
            if not current_assigned and state_data["state"] in {
                "available", "in_progress", "decayed"
            }:
                _make_current(point)
                current_assigned = True
            points.append(point)
            position += 1
            cluster_has_mistakes = cluster_has_mistakes or node.id in open_mistake_nodes
        if cluster_has_mistakes:
            points.append(
                _track_point(
                    "review",
                    f"Отработка: {cluster.title}",
                    {"state": "available", "mastery": 0, "unmet_conditions": []},
                    position,
                )
            )
            position += 1
        clusters.append({"title": cluster.title, "color": cluster.color, "points": points})
    mocks = []
    for mock in MockExam.objects.filter(is_active=True):
        mocks.append(
            _track_point(
                "mock",
                mock.title,
                {"state": "available", "mastery": 0, "unmet_conditions": []},
                position,
            )
        )
        position += 1
    return {"track_clusters": clusters, "mock_points": mocks}


def _track_point(point_type, title, state_data, position, node_id=None):
    state = state_data["state"]
    mastery_percent = max(0, min(100, round(float(state_data.get("mastery", 0)))))
    unlock_conditions = [
        {
            **condition,
            "current_mastery": round(float(condition["current_mastery"])),
        }
        for condition in state_data.get("unmet_conditions", [])
    ]
    unlock_tooltip = "; ".join(
        f"Тема {condition['title']} — нужно {condition['required_mastery']}%, "
        f"сейчас {condition['current_mastery']}%"
        for condition in unlock_conditions
    )
    if point_type == "review":
        visual_state, marker, url = "review", "↻", reverse("practice_backlog")
    elif point_type == "mock":
        visual_state, marker, url = "mock", "🏆", reverse("mocks")
    else:
        visual_state = state
        marker = "✓" if state == "mastered" else ("🔒" if state == "locked" else "●")
        url = reverse("lesson", args=[node_id]) if state != "locked" else None
    return {
        "type": point_type,
        "type_label": POINT_TYPE_LABELS[point_type],
        "title": title,
        "state": state,
        "state_label": NODE_STATE_LABELS.get(state, state),
        "node_id": node_id,
        "is_done": state == "mastered",
        "is_current": False,
        "visual_state": visual_state,
        "marker": marker,
        "mastery_percent": mastery_percent,
        "progress_style": f"--track-progress: {mastery_percent}%",
        "position": position % 5,
        "position_class": f"track-pos-{position % 5}",
        "unlock_conditions": unlock_conditions,
        "unlock_tooltip": unlock_tooltip,
        "url": url,
        "is_clickable": url is not None,
    }


def _make_current(point):
    point.update({"is_current": True, "visual_state": "current", "marker": "★"})


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
    plan = get_active_plan(student)
    return {
        "forecast": ceiling_forecast(student),
        "target_score": student.target_score,
        "trajectory": plan.trajectory if plan and plan.trajectory_id else None,
    }


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
    raw_distribution = payload.get("error_type_distribution", {})
    max_error_count = max(raw_distribution.values(), default=0)
    distribution = [
        {
            "label": ERROR_TYPE_LABELS.get(error_type, error_type),
            "count": count,
            "percent": round(count * 100 / max_error_count) if max_error_count else 0,
        }
        for error_type, count in raw_distribution.items()
    ]
    risks = [
        {
            "text": risk,
            "severity": (
                "danger"
                if "просроч" in risk.lower() or "пробник" in risk.lower()
                else "warning"
            ),
        }
        for risk in payload.get("risks", [])
    ]
    score = payload.get("dynamics", {}).get("current_predicted_score") or 0
    delta = payload.get("dynamics", {}).get("delta")
    if delta is None:
        delta_label, delta_class = "без изменений", "muted"
    elif delta > 0:
        delta_label, delta_class = f"+{delta}", "success"
    elif delta < 0:
        delta_label, delta_class = f"−{abs(delta)}", "danger"
    else:
        delta_label, delta_class = "без изменений", "muted"
    gauge = gauge_metrics(score)
    return {
        "child": child,
        "report": report,
        "report_data": payload,
        "error_distribution": distribution,
        "risk_cards": risks,
        "gauge_dash": gauge["dash"],
        "gauge_offset": gauge["offset"],
        "week_end": report.week_start + timedelta(days=6),
        "delta_label": delta_label,
        "delta_class": delta_class,
    }
