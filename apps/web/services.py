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
from apps.diagnostics.models import DiagnosticResult, DiagnosticTest
from apps.expert_review.models import ExpertReviewRequest
from apps.gamification.services import gamification_snapshot
from apps.knowledge.models import KnowledgeDependency, KnowledgeNode, TopicCluster
from apps.knowledge.services import apply_decay, node_states
from apps.mocks.models import MockExam, MockExamResult
from apps.planning.labels import STUDY_PLAN_ITEM_TYPE_LABELS
from apps.planning.models import StudyPlanItem, TrajectoryTransition
from apps.planning.services import (
    get_active_plan,
    items_for_period,
    today_items_with_overdue,
)
from apps.practice.models import Attempt, MistakeBacklogItem
from apps.practice.services import due_reviews, practice_queue
from apps.progress.models import ProgressSnapshot
from apps.progress.services import (
    ceiling_forecast,
    forecast_recommendations,
    platform_forecast,
)

from .labels import ERROR_TYPE_LABELS, TRAJECTORY_REASON_LABELS


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
POINT_TYPE_LABELS = STUDY_PLAN_ITEM_TYPE_LABELS
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
    today = timezone.localdate()
    for item in prepared:
        item.ui_type_label = POINT_TYPE_LABELS[item.item_type]
        item.ui_is_overdue = (
            item.status == StudyPlanItem.Status.PENDING
            and item.due_date is not None
            and item.due_date < today
        )
        item.ui_status_label = (
            "Просрочено" if item.ui_is_overdue else PLAN_STATUS_LABELS[item.status]
        )
    return prepared


def dashboard_context(student):
    apply_decay(student)
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    plan = get_active_plan(student)
    trajectory = plan.trajectory if plan and plan.trajectory_id else None
    snapshot = ProgressSnapshot.objects.filter(student=student).first()
    forecast = platform_forecast(student)
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
        student.start_score,
        forecast["current_level"],
        student.target_score,
    )
    transitions = list(
        TrajectoryTransition.objects.filter(
            student=student, acknowledged=False
        ).select_related("from_trajectory", "to_trajectory")
    )
    for transition in transitions:
        transition.ui_reasons = [
            TRAJECTORY_REASON_LABELS.get(reason, reason)
            for reason in transition.reasons
        ]
    return {
        "today_items": _prepare_plan_items(today_items_with_overdue(student, today)),
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
        "trajectory_transitions": transitions,
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
                            "remaining_mastery_percent": max(
                                0,
                                round(
                                    float(condition["required_mastery"])
                                    - float(condition["current_mastery"])
                                ),
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
    units = []
    current_assigned = False
    current_point = None
    offset_pattern = (0, 44, 70, 44, 0, -44, -70, -44)
    deco_emojis = ("🧮", "📐", "📏", "🧊", "🎲", "📈")
    for unit_index, cluster in enumerate(
        TopicCluster.objects.prefetch_related("nodes__lessons")
    ):
        points = []
        cluster_has_mistakes = False
        for node in cluster.nodes.all():
            state_data = states[node.id]
            for lesson in node.lessons.all():
                point = _track_point(
                    "lesson", lesson.title, state_data, node.id
                )
                if not current_assigned and state_data["state"] in {
                    "available", "in_progress", "decayed"
                }:
                    _make_current(point)
                    current_assigned = True
                    current_point = point
                points.append(point)
            point = _track_point(
                "practice", f"Практика: {node.title}", state_data, node.id
            )
            if not current_assigned and state_data["state"] in {
                "available", "in_progress", "decayed"
            }:
                _make_current(point)
                current_assigned = True
                current_point = point
            points.append(point)
            cluster_has_mistakes = cluster_has_mistakes or node.id in open_mistake_nodes
        if cluster_has_mistakes:
            points.append(
                _track_point(
                    "review",
                    f"Отработка: {cluster.title}",
                    {"state": "available", "mastery": 0, "unmet_conditions": []},
                )
            )
        mirrored = unit_index % 2 == 1
        for point_index, point in enumerate(points):
            offset = offset_pattern[point_index % len(offset_pattern)]
            point["offset_px"] = -offset if mirrored else offset
        cluster_nodes = list(cluster.nodes.all())
        units.append(
            {
                "index": unit_index + 1,
                "title": cluster.title,
                "color": cluster.color,
                "mirrored": mirrored,
                "mastered_count": sum(
                    states[node.id]["state"] == "mastered" for node in cluster_nodes
                ),
                "total_nodes": len(cluster_nodes),
                "first_node_url": (
                    reverse("knowledge_node", args=[cluster_nodes[0].id])
                    if cluster_nodes
                    else None
                ),
                "deco_emoji": deco_emojis[unit_index % len(deco_emojis)],
                "is_mock_unit": False,
                "points": points,
            }
        )

    mock_points = []
    for mock in MockExam.objects.filter(is_active=True):
        mock_points.append(
            _track_point(
                "mock",
                mock.title,
                {"state": "available", "mastery": 0, "unmet_conditions": []},
            )
        )
    if mock_points:
        unit_index = len(units)
        mirrored = unit_index % 2 == 1
        for point_index, point in enumerate(mock_points):
            offset = offset_pattern[point_index % len(offset_pattern)]
            point["offset_px"] = -offset if mirrored else offset
        units.append(
            {
                "index": unit_index + 1,
                "title": "Пробники",
                "color": "#FFC800",
                "mirrored": mirrored,
                "mastered_count": 0,
                "total_nodes": len(mock_points),
                "first_node_url": None,
                "deco_emoji": "🏆",
                "is_mock_unit": True,
                "points": mock_points,
            }
        )

    if current_point is None:
        current_point = next(
            (
                point
                for unit in units
                for point in unit["points"]
                if point["visual_state"] in {"review", "mock"}
            ),
            None,
        )
        if current_point is not None:
            _make_current(current_point)

    return {
        "track_units": units,
        "current_point": current_point,
        "gamification": gamification_snapshot(student),
        "platform_forecast": platform_forecast(student),
    }


def _track_point(point_type, title, state_data, node_id=None):
    state = state_data["state"]
    mastery_percent = max(0, min(100, round(float(state_data.get("mastery", 0)))))
    popover_conditions = [
        {
            "title": condition["title"],
            "current": round(float(condition["current_mastery"])),
            "required": round(float(condition["required_mastery"])),
            "percent": max(
                0,
                min(
                    100,
                    round(
                        float(condition["current_mastery"])
                        * 100
                        / max(float(condition["required_mastery"]), 1)
                    ),
                ),
            ),
        }
        for condition in state_data.get("unmet_conditions", [])
    ]
    if point_type == "review":
        visual_state, icon, url = "review", "review", reverse("practice_backlog")
        cta_label = "К ОТРАБОТКЕ"
    elif point_type == "mock":
        visual_state, icon, url = "mock", "mock", reverse("mocks")
        cta_label = "К ПРОБНИКУ"
    else:
        visual_state = state
        icon = (
            "check"
            if state == "mastered"
            else "review"
            if state == "decayed"
            else point_type
        )
        url = reverse("lesson", args=[node_id]) if state != "locked" else None
        if state == "locked":
            cta_label = "ЗАКРЫТО"
        elif state in {"mastered", "decayed"}:
            cta_label = "ПОВТОРИТЬ"
        elif mastery_percent > 0:
            cta_label = "ПРОДОЛЖИТЬ"
        else:
            cta_label = "НАЧАТЬ"
    if state == "mastered":
        subtitle = f"Освоено · {mastery_percent}%"
    else:
        subtitle = (
            f"{POINT_TYPE_LABELS[point_type]} · "
            f"{NODE_STATE_LABELS.get(state, state)} · освоено {mastery_percent}%"
        )
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
        "icon": icon,
        "cta_label": cta_label,
        "subtitle": subtitle,
        "mastery_percent": mastery_percent,
        "offset_px": 0,
        "popover_conditions": popover_conditions,
        "url": url,
    }


def _make_current(point):
    point["is_current"] = True


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
        "forecast": platform_forecast(student),
        "recommendations": forecast_recommendations(student),
        "target_score": student.target_score,
        "trajectory": plan.trajectory if plan and plan.trajectory_id else None,
    }


def diagnostics_context(student):
    tests = list(
        DiagnosticTest.objects.filter(is_active=True).prefetch_related("assignments")
    )
    in_progress = {}
    for result in (
        DiagnosticResult.objects.filter(
            student=student,
            test__in=tests,
            status=DiagnosticResult.Status.IN_PROGRESS,
        )
        .select_related("test")
        .order_by("test_id", "-started_at")
    ):
        in_progress.setdefault(result.test_id, result)
    return {
        "diagnostics": [
            {
                "test": test,
                "task_count": len(test.assignments.all()),
                "in_progress_result": in_progress.get(test.id),
            }
            for test in tests
        ],
        "latest_completed_result": (
            DiagnosticResult.objects.filter(
                student=student,
                status=DiagnosticResult.Status.COMPLETED,
            )
            .select_related("test")
            .order_by("-completed_at", "-started_at")
            .first()
        ),
    }


def diagnostic_run_context(student, result_id):
    result = get_object_or_404(
        DiagnosticResult.objects.select_related("test").prefetch_related(
            "test__assignments"
        ),
        pk=result_id,
        student=student,
    )
    return {
        "result": result,
        "part1_assignments": result.test.assignments.filter(
            exam_part=Assignment.Part.PART1
        ),
        "part2_assignments": result.test.assignments.filter(
            exam_part=Assignment.Part.PART2
        ),
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
    score = payload.get("platform_forecast", {}).get("forecast_score") or 0
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
