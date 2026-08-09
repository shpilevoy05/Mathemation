"""Read-side composition for the server-rendered student cabinet."""

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

from apps.ai_mentor.models import AiHintMessage, AiHintSession
from apps.ai_mentor.services import mentor_available
from apps.content.services import published_lessons
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


def _published_lessons_prefetch(lookup: str = "nodes__lessons", *related: str) -> Prefetch:
    """Prefetch уроков, отфильтрованный по публикации.

    Черновик методиста не должен появляться у ученика на дорожке или в карте
    навыков как пустая точка.
    """
    queryset = published_lessons()
    if related:
        queryset = queryset.prefetch_related(*related)
    return Prefetch(lookup, queryset=queryset)


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
        "gauge": primary_gauge(student, forecast),
        "wallet_balance": _wallet_balance(student),
        "days_to_exam": (
            max((student.exam_date - today).days, 0) if student.exam_date else None
        ),
        "week_streak": _week_streak(student, today),
        "daily": _daily_banner(student),
    }


def _week_streak(student, today) -> list[bool]:
    """Были ли занятия в каждый день этой недели — семь ячеек для полосы серии."""
    week_start = today - timedelta(days=today.weekday())
    active_days = set(
        Attempt.objects.filter(
            student=student, created_at__date__gte=week_start, created_at__date__lte=today
        )
        .values_list("created_at__date", flat=True)
        .distinct()
    )
    return [(week_start + timedelta(days=offset)) in active_days for offset in range(7)]


def _daily_banner(student) -> dict | None:
    """Полоса задания дня для кабинета: награда и сколько осталось до полуночи."""
    from apps.content.services import challenge_state

    state = challenge_state(student)
    challenge = state.get("challenge")
    if challenge is None:
        return None
    now = timezone.localtime()
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    left = midnight - now
    hours, remainder = divmod(int(left.total_seconds()), 3600)
    return {
        "title": challenge.title or challenge.assignment.title,
        "solved": state.get("solved", False),
        "reward_xp": state.get("reward_xp", 0),
        "reward_coins": getattr(challenge, "reward_coins", 0),
        "time_left": f"{hours:02d}:{remainder // 60:02d}",
    }


def _wallet_balance(student) -> int:
    from apps.economy.services import get_wallet

    return get_wallet(student).balance


def primary_gauge(student, forecast=None) -> dict:
    """Шкала первичных баллов: текущая оценка, интервал, цель и потолок.

    Ось одна и всегда первичная: перевод в тестовые нелинейный, поэтому
    смешивать единицы на одной линейке нельзя.
    """
    from apps.progress.services import (
        forecast_interval,
        max_primary_score,
        primary_for_scaled,
        primary_to_scaled,
    )

    interval = forecast_interval(student)
    maximum = max_primary_score() or 1
    low_primary = max(interval["primary"] - interval["sigma_primary"] * 1.28, 0)
    high_primary = min(interval["primary"] + interval["sigma_primary"] * 1.28, maximum)
    target_primary = primary_for_scaled(student.target_score)
    percent = lambda value: round(min(max(value / maximum, 0), 1) * 100, 2)  # noqa: E731

    gauge = {
        "max_primary": round(maximum, 1),
        "primary": interval["primary"],
        "scaled": interval["scaled"],
        "low_scaled": interval["low_scaled"],
        "high_scaled": interval["high_scaled"],
        "now_percent": percent(interval["primary"]),
        "band_left_percent": percent(low_primary),
        "band_width_percent": percent(high_primary) - percent(low_primary),
        "target_primary": target_primary,
        "target_scaled": student.target_score,
        "target_percent": percent(target_primary),
        "to_target_primary": round(max(target_primary - interval["primary"], 0), 1),
        # Сколько занятий это примерно значит: один пункт плана ≈ 0,5 первичного
        # балла по демо-данным — числу верить нельзя как прогнозу, но масштаб
        # ученику нужен.
        "to_target_lessons": max(
            1, round(max(target_primary - interval["primary"], 0) / 0.5)
        ) if target_primary > interval["primary"] else 0,
        "ticks": [round(maximum * step / 8, 1) for step in range(9)],
        "ceiling_primary": None,
        "ceiling_percent": None,
    }
    if forecast is not None and forecast.get("ceiling_score") is not None:
        ceiling_primary = primary_for_scaled(forecast["ceiling_score"])
        gauge["ceiling_primary"] = ceiling_primary
        gauge["ceiling_percent"] = percent(ceiling_primary)
        gauge["ceiling_scaled"] = forecast["ceiling_score"]
    gauge["scaled_check"] = primary_to_scaled(interval["primary"])
    return gauge


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
    return {
        "clusters": clusters,
        "ceiling_overlay": overlay,
        "graph": knowledge_graph_layout(clusters),
    }


# Раскладка графа. Считается на сервере, чтобы координаты были одинаковыми в
# браузере, в тестах и в будущем экспорте картинки.
GRAPH_CLUSTER_WIDTH = 320
GRAPH_CLUSTER_GAP = 26
GRAPH_COLUMNS = 3
GRAPH_ROW_HEIGHT = 116
GRAPH_HEAD = 74


def knowledge_graph_layout(clusters: list[dict]) -> dict:
    """Координаты узлов и рёбер для SVG-графа карты навыков.

    Узлы раскладываются по своим кластерам в две колонки: так подписи не
    налезают на рёбра, а кластер остаётся визуально цельным.
    """
    positions: dict[int, dict] = {}
    boxes: list[dict] = []
    row_top = 20
    row_height = 0
    for index, cluster in enumerate(clusters):
        column = index % GRAPH_COLUMNS
        if column == 0 and index:
            row_top += row_height + GRAPH_CLUSTER_GAP
            row_height = 0
        left = 20 + column * (GRAPH_CLUSTER_WIDTH + GRAPH_CLUSTER_GAP)
        rows = max(1, -(-len(cluster["nodes"]) // 2))
        height = GRAPH_HEAD + rows * GRAPH_ROW_HEIGHT - 30
        row_height = max(row_height, height)
        boxes.append({
            "title": cluster["title"], "color": cluster["color"],
            "x": left, "y": row_top, "w": GRAPH_CLUSTER_WIDTH, "h": height,
        })
        for order, node in enumerate(cluster["nodes"]):
            node_row, node_column = divmod(order, 2)
            positions[node["id"]] = {
                "id": node["id"],
                "title": node["title"],
                "state": node["state"],
                "state_label": node["state_label"],
                "mastery": round(float(node["mastery"])),
                "x": left + 86 + node_column * 152 + (node_row % 2) * 16,
                "y": row_top + 62 + node_row * GRAPH_ROW_HEIGHT,
                "url": reverse("knowledge_node", args=[node["id"]]),
            }

    edges = []
    dependencies = KnowledgeDependency.objects.filter(
        node_id__in=positions, prerequisite_id__in=positions
    ).values("node_id", "prerequisite_id", "min_mastery")
    for dependency in dependencies:
        prerequisite = positions[dependency["prerequisite_id"]]
        edges.append({
            "from": dependency["prerequisite_id"],
            "to": dependency["node_id"],
            "met": prerequisite["mastery"] >= dependency["min_mastery"],
        })
    return {
        "clusters": boxes,
        "nodes": list(positions.values()),
        "edges": edges,
        "width": 20 + GRAPH_COLUMNS * (GRAPH_CLUSTER_WIDTH + GRAPH_CLUSTER_GAP),
        "height": row_top + row_height + 24,
    }


def knowledge_node_context(student, node_id):
    node = get_object_or_404(
        KnowledgeNode.objects.select_related("cluster").prefetch_related(
            _published_lessons_prefetch("lessons", "theory_blocks")
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
    task_progress = node_task_progress(student)
    for cluster in TopicCluster.objects.prefetch_related(_published_lessons_prefetch()):
        points = []
        cluster_has_mistakes = False
        for node in cluster.nodes.all():
            state_data = states[node.id]
            for lesson in node.lessons.all():
                point = _track_point(
                    "lesson", lesson.title, state_data, position, node.id,
                    task_progress,
                )
                # Текущей не может быть уже пройденная точка: иначе «продолжить»
                # ведёт туда, где всё решено.
                if not current_assigned and not point["is_done"] and state_data["state"] in {
                    "available", "in_progress", "decayed"
                }:
                    _make_current(point)
                    current_assigned = True
                points.append(point)
                position += 1
            point = _track_point(
                "practice", f"Практика: {node.title}", state_data, position, node.id,
                task_progress,
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
        done_points = sum(1 for point in points if point["is_done"])
        clusters.append({
            "title": cluster.title,
            "color": cluster.color,
            "points": points,
            "percent": round(done_points * 100 / len(points)) if points else 0,
        })
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
    all_points = [point for cluster in clusters for point in cluster["points"]]
    done = sum(1 for point in all_points if point["is_done"])
    # «До пробника» — сколько тем осталось закрыть в текущем разделе: у ученика
    # это единственный ориентир, зачем ему следующие точки.
    current_cluster = next(
        (cluster for cluster in clusters if any(p["is_current"] for p in cluster["points"])),
        None,
    )
    to_mock = (
        sum(1 for point in current_cluster["points"] if not point["is_done"])
        if current_cluster else 0
    )
    return {
        "track_clusters": clusters,
        "mock_points": mocks,
        "track_done": done,
        "track_total": len(all_points),
        "track_to_mock": f"{to_mock} тем" if to_mock else "готово",
    }


def homework_context(student) -> dict:
    """Выданные домашки с прогрессом и ссылкой на занятие по теме."""
    from apps.content.models import HomeworkSubmission
    from apps.content.services import homework_progress, is_overdue

    submissions = (
        HomeworkSubmission.objects.filter(student=student)
        .select_related("homework", "homework__lesson__node")
        .prefetch_related("homework__tasks__assignment__skill_tags__node")
    )
    rows = []
    for submission in submissions:
        tasks = []
        for task in submission.homework.tasks.all():
            tag = task.assignment.skill_tags.first()
            tasks.append({
                "assignment": task.assignment,
                "node": tag.node if tag else None,
                "url": reverse("lesson", args=[tag.node_id]) if tag else None,
            })
        progress = homework_progress(submission)
        rows.append({
            "submission": submission,
            "homework": submission.homework,
            "progress": progress,
            "percent": (
                round(progress["solved"] * 100 / progress["total"])
                if progress["total"] else 0
            ),
            "overdue": is_overdue(submission),
            "tasks": tasks,
        })
    return {
        "homework_rows": rows,
        "open_count": sum(
            1 for row in rows
            if row["submission"].status != HomeworkSubmission.Status.CHECKED
        ),
    }


WEEKDAY_LABELS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
WEEKDAY_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def daily_challenge_context(student) -> dict:
    """Задание дня: сама задача, награда, серия и неделя занятий."""
    from apps.content.services import challenge_state
    from apps.gamification.models import GamificationProfile

    state = challenge_state(student)
    challenge = state.get("challenge")
    node = None
    if challenge is not None:
        tag = challenge.assignment.skill_tags.select_related("node").first()
        node = tag.node if tag else None

    today = timezone.localdate()
    week = _week_streak(student, today)
    profile, _ = GamificationProfile.objects.get_or_create(student=student)
    banner = _daily_banner(student)
    return {
        "challenge": challenge,
        "solved": state.get("solved", False),
        "reward_xp": state.get("reward_xp", 0),
        "node": node,
        "attempt_context": Attempt.Context.LESSON,
        "today": today,
        "time_left": banner["time_left"] if banner else "—",
        "streak_current": profile.streak_current,
        "next_streak": profile.streak_current + 1,
        # Неделя серии: закрашенные дни — те, в которые ученик отвечал.
        "week_days": [
            {
                "done": done,
                "is_today": index == today.weekday(),
                "label": WEEKDAY_LABELS[index],
                "short": WEEKDAY_SHORT[index],
            }
            for index, done in enumerate(week)
        ],
        "week_done": sum(week),
    }


def shop_context(student) -> dict:
    """Витрина: баланс, косметика и расходники с их эффектами."""
    from apps.economy.models import InventoryItem, ShopItem
    from apps.economy.services import active_boost, get_wallet, storefront
    from apps.gamification.models import GamificationProfile

    inventory = list(
        InventoryItem.objects.filter(student=student).select_related("item")
    )
    owned = {entry.item_id for entry in inventory}
    equipped = {entry.item_id for entry in inventory if entry.is_equipped}
    wallet = get_wallet(student)
    items, boosts = [], []
    for item in storefront():
        row = {
            "item": item,
            "owned": item.id in owned,
            "equipped": item.id in equipped,
            "affordable": wallet.balance >= item.price_coins,
            "is_consumable": item.effect != ShopItem.Effect.NONE,
            "effect_note": _effect_note(item),
        }
        (boosts if row["is_consumable"] else items).append(row)

    profile, _ = GamificationProfile.objects.get_or_create(student=student)
    boost = active_boost(student)
    return {
        "balance": wallet.balance,
        "shop_items": items,
        "boost_items": boosts,
        "shop_cards": [_shop_card(row, wallet.balance) for row in boosts + items],
        "owned_count": len(owned),
        "recent_entries": list(wallet.entries.all()[:10]),
        "streak_freezes": profile.streak_freezes,
        "active_boost": boost,
        "has_equipped": bool(equipped),
    }


# Витрина макета показывает предмет карточкой: иконка в тонированном квадрате,
# ярлык, описание и цена. Иконку и тон выбираем по слоту и эффекту — товар
# должен читаться до того, как ученик прочитал название.
SHOP_ICONS = {
    "avatar": ("i-star", "indigo"),
    "frame": ("i-medal", "gold"),
    "theme": ("i-moon", "violet"),
    "badge": ("i-medal", "gold"),
    "boost": ("i-bolt", "indigo"),
}
SHOP_EFFECT_ICONS = {
    "streak_freeze": ("i-snow", "ice"),
    "xp_boost": ("i-bolt", "indigo"),
}


def _shop_card(row: dict, balance: int) -> dict:
    """Карточка витрины: что нарисовать и что написать на ярлыке."""
    from apps.economy.models import ShopItem

    item = row["item"]
    icon, tone = SHOP_EFFECT_ICONS.get(
        item.effect, SHOP_ICONS.get(item.slot, ("i-sigma", "indigo"))
    )
    if row["equipped"]:
        tag, tag_class = "надето", "success-soft"
    elif row["owned"]:
        tag, tag_class = "куплено", "chip-mute"
    elif item.effect == ShopItem.Effect.STREAK_FREEZE:
        tag, tag_class = "защита серии", "chip-brand"
    elif item.effect == ShopItem.Effect.XP_BOOST:
        tag, tag_class = "ускоритель", "warning-soft"
    else:
        tag, tag_class = item.get_slot_display().lower(), "chip-mute"
    return {
        **row,
        "icon": icon,
        "tone": tone,
        "tag": tag,
        "tag_class": tag_class,
        "frosted": item.effect == ShopItem.Effect.STREAK_FREEZE,
        "group": "boost" if row["is_consumable"] else item.slot,
        "description": item.description or row.get("effect_note") or "Оформление кабинета.",
        "available": row["owned"] or row["affordable"],
        "missing": max(item.price_coins - balance, 0),
    }


def _effect_note(item) -> str:
    """Человеческая подпись к расходнику: что именно он делает."""
    from apps.economy.models import ShopItem

    if item.effect == ShopItem.Effect.STREAK_FREEZE:
        days = max(item.effect_value, 1)
        return f"Спасает серию при пропуске: {days} дн."
    if item.effect == ShopItem.Effect.XP_BOOST:
        return f"+{item.effect_value} % опыта на {item.duration_hours} ч"
    return ""


def node_task_progress(student) -> dict[int, dict]:
    """Сколько задач темы решено верно — по всем узлам сразу.

    Ученик видит на дорожке не только состояние узла, но и движение внутри
    темы: без этого верный ответ не отражается нигде, пока не сменится статус.
    """
    totals = dict(
        KnowledgeNode.objects.annotate(
            total=Count("assignments", distinct=True)
        ).values_list("id", "total")
    )
    solved = dict(
        KnowledgeNode.objects.filter(
            assignments__attempts__student=student,
            assignments__attempts__is_correct=True,
        )
        .annotate(solved=Count("assignments", distinct=True))
        .values_list("id", "solved")
    )
    return {
        node_id: {
            "solved": solved.get(node_id, 0),
            "total": total,
            "percent": round(solved.get(node_id, 0) * 100 / total) if total else 0,
        }
        for node_id, total in totals.items()
    }


def _track_point(point_type, title, state_data, position, node_id=None,
                 task_progress=None):
    state = state_data["state"]
    mastery_percent = max(0, min(100, round(float(state_data.get("mastery", 0)))))
    progress = (task_progress or {}).get(node_id, {"solved": 0, "total": 0, "percent": 0})
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
    # Урок считается пройденным, когда решены все его задачи: ученик уже сделал
    # работу, и точка на дорожке не должна ждать порога освоения темы. Практика
    # закрывается порогом — это другой критерий и другая точка.
    tasks_done = progress["total"] > 0 and progress["solved"] >= progress["total"]
    is_done = state == "mastered" or (point_type == "lesson" and tasks_done)
    # Иконка точки берётся из спрайта: символы в тексте выглядели служебными.
    if point_type == "review":
        visual_state, marker, url = "review", "↻", reverse("practice_backlog")
        icon = "i-repeat"
    elif point_type == "mock":
        visual_state, marker, url = "mock", "🏆", reverse("mocks")
        icon = "i-cup"
    else:
        visual_state = "mastered" if is_done else state
        marker = "✓" if is_done else ("🔒" if state == "locked" else "●")
        url = reverse("lesson", args=[node_id]) if state != "locked" else None
        icon = "i-check" if is_done else ("i-lock" if state == "locked" else "i-bolt")
    return {
        "type": point_type,
        "type_label": POINT_TYPE_LABELS[point_type],
        "title": title,
        "state": state,
        "state_label": NODE_STATE_LABELS.get(state, state),
        "node_id": node_id,
        "is_done": is_done,
        "is_current": False,
        "visual_state": visual_state,
        "marker": marker,
        "icon": icon,
        "mastery_percent": mastery_percent,
        "progress_style": f"--track-progress: {mastery_percent}%",
        # Прогресс по задачам темы: «решено 3 из 5» видно сразу после ответа.
        "tasks_solved": progress["solved"],
        "tasks_total": progress["total"],
        "tasks_percent": progress["percent"],
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
    # Черновики методиста ученику не показываем; ссылка на плеер собирается
    # моделью, потому что для Kinescope достаточно идентификатора ролика.
    video_lessons = list(
        published_lessons(node).exclude(video_url="")
    )
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

    from apps.content.lessons import lesson_stages, review_stats, task_stats
    from apps.gamification.services import gamification_snapshot
    from apps.economy.services import get_wallet

    stages = lesson_stages(student, node)
    review = review_stats(student, node)
    snapshot = gamification_snapshot(student)
    mastery = node_states(student)[node.id]
    return {
        "node": node,
        "video_lessons": video_lessons,
        "theory_blocks": TheoryBlock.objects.filter(lesson__node=node).select_related("lesson"),
        "tasks": tasks,
        "attempt_context": attempt_context,
        "mentor_enabled": mentor_available(attempt_context),
        "stages": stages,
        "current_stage": next(stage["key"] for stage in stages if stage["is_current"]),
        "lesson_is_complete": all(stage["is_done"] for stage in stages),
        "task_stats": task_stats(student, node),
        "due_node_reviews": review["due"],
        "open_mistakes": review["open_count"],
        "mastery_percent": round(float(mastery["mastery"]), 1),
        "mastery_threshold": settings.MASTERY_THRESHOLD,
        "start_xp": snapshot["xp"],
        "start_level": snapshot["level"],
        "start_coins": get_wallet(student).balance,
    }


def diagnostics_context(student) -> dict:
    """Входная диагностика: что пройти и что она уже показала."""
    from apps.diagnostics.models import DiagnosticResult, DiagnosticTest

    results = list(
        DiagnosticResult.objects.filter(student=student)
        .select_related("test")
        .order_by("-started_at")[:5]
    )
    last_completed = next(
        (result for result in results if result.status == DiagnosticResult.Status.COMPLETED),
        None,
    )
    in_progress = next(
        (result for result in results if result.status == DiagnosticResult.Status.IN_PROGRESS),
        None,
    )
    return {
        "tests": [
            {"test": test, "count": test.assignments.count()}
            for test in DiagnosticTest.objects.filter(is_active=True)
        ],
        "results": results,
        "last_completed": last_completed,
        "in_progress": in_progress,
        "has_plan": get_active_plan(student) is not None,
    }


def diagnostic_run_context(student, result_id) -> dict:
    """Прохождение диагностики: задачи одной страницей, без таймера."""
    from apps.diagnostics.models import DiagnosticResult

    result = get_object_or_404(
        DiagnosticResult.objects.select_related("test"), pk=result_id, student=student
    )
    return {
        "result": result,
        "assignments": list(result.test.assignments.all()),
        "is_open": result.status == DiagnosticResult.Status.IN_PROGRESS,
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
        "expert_reviews": expert_verdicts(student),
    }


EXPERT_STATUS_LABELS = {
    ExpertReviewRequest.Status.SUBMITTED: "на проверке",
    ExpertReviewRequest.Status.REVIEWED: "проверено",
    ExpertReviewRequest.Status.NEEDS_RESUBMISSION: "вернули на доработку",
}


def expert_verdicts(student, limit: int = 8) -> list[dict]:
    """Что сказал эксперт по работам второй части.

    Без этого списка вердикт виден только в полке ошибок, а работа, которую
    вернули на доработку, не видна ученику нигде — и он не знает, что от него
    ждут повторной загрузки.
    """
    requests = (
        ExpertReviewRequest.objects.filter(student=student)
        .select_related("assignment")
        .order_by("-created_at")[:limit]
    )
    return [
        {
            "id": review.id,
            "assignment": review.assignment,
            "assignment_id": review.assignment_id,
            "status": review.status,
            "status_label": EXPERT_STATUS_LABELS.get(review.status, review.status),
            "needs_resubmission": (
                review.status == ExpertReviewRequest.Status.NEEDS_RESUBMISSION
            ),
            "is_pending": review.status == ExpertReviewRequest.Status.SUBMITTED,
            "score": review.total_score,
            "max_score": review.assignment.max_score,
            "lost_points": review.lost_points,
            "comment": review.comment,
            "reviewed_at": review.reviewed_at,
            "created_at": review.created_at,
        }
        for review in requests
    ]


def forecast_context(student):
    from apps.exams.models import ExamTask
    from apps.progress.services import (
        active_exam_profile,
        forecast_interval,
        profile_coverage,
    )

    plan = get_active_plan(student)
    forecast = ceiling_forecast(student)
    coverage = profile_coverage()
    profile = active_exam_profile()
    unmapped = set(coverage.get("unmapped_numbers", []))
    numbers = []
    if profile is not None:
        numbers = [
            {"number": number, "mapped": number not in unmapped}
            for number in ExamTask.objects.filter(profile=profile)
            .order_by("number")
            .values_list("number", flat=True)
        ]
    return {
        "forecast": forecast,
        "target_score": student.target_score,
        "trajectory": plan.trajectory if plan and plan.trajectory_id else None,
        "gauge": primary_gauge(student, forecast),
        "interval": forecast_interval(student),
        "coverage": {**coverage, "numbers": numbers},
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
