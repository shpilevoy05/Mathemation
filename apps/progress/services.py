"""Forecast (текущий балл + потолок с рычагами), snapshots, weekly reports."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from apps.engine.ceiling import simulate_ceiling
from apps.engine.dto import EdgeDTO, EngineParams, NodeState, TaskWeight
from apps.engine.forecast import expected_primary as engine_expected_primary
from apps.engine.forecast import probability_correct, scaled_score
from apps.content.models import Assignment
from apps.exams.models import ExamProfile
from apps.knowledge.models import KnowledgeNode, SkillMastery
from apps.knowledge.models import KnowledgeDependency
from apps.planning.models import StudyPlanItem
from apps.planning.services import get_active_plan
from apps.practice.models import Attempt, MistakeBacklogItem

from .models import ForecastObservation, ParentReport, ProgressSnapshot

WEAK_TOPIC_LIMIT = 5


def active_exam_profile() -> ExamProfile | None:
    return ExamProfile.active()


def max_primary_score(profile: ExamProfile | None = None) -> float:
    """Максимум первичных баллов: из профиля, иначе из настроек."""
    profile = profile if profile is not None else active_exam_profile()
    if profile is not None:
        return float(profile.max_primary_score)
    return float(settings.MAX_PRIMARY_SCORE)


def _engine_params(profile: ExamProfile | None = None) -> EngineParams:
    return EngineParams(
        mastery_threshold=settings.MASTERY_THRESHOLD,
        decay_grace_days=settings.DECAY_GRACE_DAYS,
        decay_rate_per_day=settings.DECAY_RATE_PER_DAY,
        max_primary_score=max_primary_score(profile),
        hours_per_node=settings.HOURS_PER_NODE,
        attainable_mastery=settings.ATTAINABLE_MASTERY,
        bkt_alpha=settings.BKT_ALPHA,
        forecast_calibration_alpha=settings.FORECAST_CALIBRATION_ALPHA,
        theta_scale=settings.IRT_THETA_SCALE,
        b_step=settings.IRT_DIFFICULTY_STEP,
        default_discrimination=settings.IRT_DEFAULT_DISCRIMINATION,
        guess=settings.IRT_GUESS,
        review_intervals_days=tuple(settings.REVIEW_INTERVALS_DAYS),
        review_ease=settings.REVIEW_EASE,
        min_review_interval_days=settings.MIN_REVIEW_INTERVAL_DAYS,
        max_review_interval_days=settings.MAX_REVIEW_INTERVAL_DAYS,
        # Профиль экзамена уже описывает весь экзамен: его баллы в сумме дают
        # максимум, нормировать не на что.
        normalize_by_task_weights=profile is None,
    )


def _profile_task_weights(profile: ExamProfile) -> list[TaskWeight]:
    """Задания экзамена как веса для движка.

    Задание без связанных узлов пропускается: методист ещё не разметил его,
    и приписывать ему вероятность по нулевому mastery — значит выдумывать
    баллы. В разборе такое задание видно с нулевым вкладом.
    """
    weights = []
    for task in profile.tasks.prefetch_related("skills").all():
        skills = list(task.skills.all())
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


def _forecast_dtos(
    student, mastery_override: dict[int, float] | None = None
) -> tuple[list[NodeState], list[TaskWeight]]:
    nodes = list(KnowledgeNode.objects.select_related("cluster").all())
    masteries = mastery_override if mastery_override is not None else dict(
        SkillMastery.objects.filter(student=student).values_list("node_id", "mastery")
    )
    practiced_at = dict(
        SkillMastery.objects.filter(student=student).values_list(
            "node_id", "last_practiced_at"
        )
    )
    states = [
        NodeState(
            node_id=node.id,
            mastery=float(masteries.get(node.id, 0.0)),
            last_practiced_at=practiced_at.get(node.id),
            weight=float(node.weight),
            cluster_weight=float(node.cluster.exam_weight),
            hours=float(node.effective_hours),
        )
        for node in nodes
    ]

    # Профиль экзамена — приоритетный источник: прогноз описывает экзамен, а
    # не содержимое банка задач.
    profile = active_exam_profile()
    if profile is not None:
        profile_weights = _profile_task_weights(profile)
        if profile_weights:
            return states, profile_weights

    assignments = list(
        Assignment.objects.filter(skill_tags__node_id__in=[node.id for node in nodes])
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
    # Empty content databases still get a deterministic node-based bootstrap.
    if not weights:
        weights = [
            TaskWeight(
                assignment_id=node.id,
                node_ids=(node.id,),
                max_score=float(node.weight * node.cluster.exam_weight),
                difficulty=3.0,
            )
            for node in nodes
        ]
    return states, weights


def primary_to_scaled(primary: float) -> int:
    """Перевод первичных баллов в тестовые по таблице активного профиля.

    Пока профиля нет, используется таблица из настроек — так работает свежая
    установка.
    """
    profile = active_exam_profile()
    if profile is not None:
        return profile.scaled_for(primary)
    return scaled_score(primary, settings.PRIMARY_TO_SCALED)


def primary_for_scaled(scaled: int) -> float:
    """Сколько первичных нужно, чтобы получить такой тестовый балл.

    Обратная сторона таблицы перевода: цель ученик ставит в тестовых баллах, а
    вся шкала в интерфейсе живёт в первичных.
    """
    maximum = max_primary_score()
    step = 0.5
    primary = 0.0
    while primary <= maximum:
        if primary_to_scaled(primary) >= scaled:
            return round(primary, 1)
        primary += step
    return round(maximum, 1)


def expected_primary(student, mastery_override: dict[int, float] | None = None) -> float:
    """Ожидаемый первичный балл: Σ P(верно | mastery, IRT) · балл задания.

    Задания берутся из профиля экзамена, если он заполнен, иначе — из банка
    задач с нормировкой (прежнее поведение).
    """
    states, weights = _forecast_dtos(student, mastery_override)
    return engine_expected_primary(states, weights, _engine_params(active_exam_profile()))


def profile_coverage(profile: ExamProfile | None = None) -> dict:
    """Насколько профиль размечен узлами графа.

    Незамапленные задания дают ноль и занижают прогноз — методист должен
    видеть это как задачу, а не гадать, почему прогноз низкий.
    """
    profile = profile if profile is not None else active_exam_profile()
    if profile is None:
        return {"profile": None, "tasks": 0, "mapped": 0, "unmapped_numbers": []}
    tasks = list(profile.tasks.prefetch_related("skills").all())
    unmapped = [task.number for task in tasks if not task.skills.all()]
    return {
        "profile": str(profile),
        "tasks": len(tasks),
        "mapped": len(tasks) - len(unmapped),
        "unmapped_numbers": unmapped,
        "unmapped_score": sum(
            task.max_score for task in tasks if not task.skills.all()
        ),
    }


def forecast_breakdown(student, mastery_override: dict[int, float] | None = None) -> list[dict]:
    """Разбор прогноза по заданиям экзамена: «задача 13 даёт +0.8 балла».

    Пусто, пока методисты не описали профиль экзамена. Задание без узлов
    показывается с нулевым вкладом — так видно, что профиль недоразмечен.
    """
    profile = active_exam_profile()
    if profile is None:
        return []
    states, _ = _forecast_dtos(student, mastery_override)
    params = _engine_params(profile)
    mastery_by_id = {state.node_id: state.mastery for state in states}

    breakdown = []
    for task in profile.tasks.prefetch_related("skills").all():
        skills = list(task.skills.all())
        weights = [max(float(skill.weight), 0.0) for skill in skills]
        total_weight = sum(weights)
        mastery = (
            sum(
                mastery_by_id.get(skill.node_id, 0.0) * weight
                for skill, weight in zip(skills, weights)
            )
            / total_weight
            if total_weight
            else 0.0
        )
        probability = (
            probability_correct(mastery, float(task.difficulty), params)
            if skills
            else 0.0
        )
        breakdown.append({
            "number": task.number,
            "exam_part": task.exam_part,
            "max_score": task.max_score,
            "difficulty": task.difficulty,
            "probability": round(probability, 3),
            "expected_points": round(probability * task.max_score, 2),
            "node_ids": [skill.node_id for skill in skills],
        })
    return breakdown


def calibrated_primary(student, mastery_override: dict[int, float] | None = None) -> float:
    """Ожидаемый первичный балл с поправкой по прошлым пробникам."""
    primary = expected_primary(student, mastery_override) + student.primary_calibration
    return min(max(primary, 0.0), max_primary_score())


def predict_score(student, mastery_override: dict[int, float] | None = None) -> tuple[int, float]:
    """(прогнозный тестовый балл с калибровкой, доля ожидаемых первичных).

    Поправка применяется до таблицы перевода: таблица нелинейна, и один и тот
    же сдвиг в тестовых баллах означал бы разную ошибку на разных участках
    шкалы.
    """
    primary = calibrated_primary(student, mastery_override)
    avg = primary / (max_primary_score() or 1) * 100
    return int(min(max(primary_to_scaled(primary), 0), 100)), round(avg, 2)


def forecast_sigma(student) -> float:
    """Стандартное отклонение ошибки прогноза в первичных баллах."""
    if student.calibration_samples == 0:
        return float(settings.FORECAST_PRIOR_SIGMA_PRIMARY)
    return max(student.primary_error_variance, 0.0) ** 0.5


def forecast_interval(student, mastery_override: dict[int, float] | None = None) -> dict:
    """Прогноз интервалом: одно число выглядит точнее, чем прогноз есть."""
    primary = calibrated_primary(student, mastery_override)
    half_width = settings.FORECAST_INTERVAL_Z * forecast_sigma(student)
    low = max(primary - half_width, 0.0)
    high = min(primary + half_width, max_primary_score())
    return {
        "primary": round(primary, 2),
        "scaled": int(min(max(primary_to_scaled(primary), 0), 100)),
        "low_scaled": int(min(max(primary_to_scaled(low), 0), 100)),
        "high_scaled": int(min(max(primary_to_scaled(high), 0), 100)),
        "sigma_primary": round(forecast_sigma(student), 2),
        "samples": student.calibration_samples,
        "calibration_primary": round(student.primary_calibration, 2),
    }


def calibrate_forecast(student, actual_primary: float, mock_result=None) -> ForecastObservation:
    """Сверить прогноз с фактом пробника и подтянуть модель.

    Всё считается в первичных баллах: и поправка, и разброс. Разброс копится
    как EMA квадрата остаточной ошибки — по нему строится интервал.
    """
    alpha = settings.FORECAST_CALIBRATION_ALPHA
    raw_predicted = expected_primary(student)
    error = float(actual_primary) - raw_predicted

    student.primary_calibration = round(
        (1 - alpha) * student.primary_calibration + alpha * error, 3
    )
    residual = error - student.primary_calibration
    variance = (
        residual ** 2
        if student.calibration_samples == 0
        else (1 - alpha) * student.primary_error_variance + alpha * residual ** 2
    )
    student.primary_error_variance = round(variance, 3)
    student.calibration_samples += 1
    student.save(
        update_fields=[
            "primary_calibration", "primary_error_variance", "calibration_samples"
        ]
    )
    return ForecastObservation.objects.create(
        student=student, mock_result=mock_result,
        predicted_primary=round(raw_predicted, 2), actual_primary=float(actual_primary),
        error=round(error, 2), calibration_after=student.primary_calibration,
    )


def calibration_report(student, limit: int = 20) -> dict:
    """Пары «прогноз — факт» и средняя ошибка: по ним видно, калиброван ли прогноз."""
    observations = list(student.forecast_observations.all()[:limit])
    errors = [observation.error for observation in observations]
    return {
        "samples": len(observations),
        "mean_error": round(sum(errors) / len(errors), 2) if errors else 0.0,
        "mean_absolute_error": (
            round(sum(abs(error) for error in errors) / len(errors), 2) if errors else 0.0
        ),
        "sigma_primary": round(forecast_sigma(student), 2),
        "observations": [
            {
                "predicted_primary": observation.predicted_primary,
                "actual_primary": observation.actual_primary,
                "error": observation.error,
                "created_at": observation.created_at,
            }
            for observation in observations
        ],
    }


def ceiling_forecast(student, weekly_hours: int | None = None, exam_date=None) -> dict:
    """Потолок: чего реально достичь к экзамену при заданном темпе.

    Рычаги «поиграть ползунком» = вызов с другими weekly_hours / exam_date.
    Возвращает потолочный балл и списки достижимых/недостижимых узлов —
    последние подсвечиваются на карте оверлеем «что реально успеешь».
    """
    weekly_hours = weekly_hours or student.weekly_hours
    exam_date = exam_date or student.exam_date
    current_score, _ = predict_score(student)

    states, _ = _forecast_dtos(student)
    edges = [
        EdgeDTO(
            from_node_id=dependency.prerequisite_id,
            to_node_id=dependency.node_id,
            min_mastery=float(dependency.min_mastery),
        )
        for dependency in KnowledgeDependency.objects.all()
    ]
    days_left = (
        None
        if exam_date is None
        else max((exam_date - timezone.localdate()).days, 0)
    )
    result = simulate_ceiling(states, edges, days_left, weekly_hours, _engine_params())
    ceiling_score, _ = predict_score(student, mastery_override=result.mastery_profile)

    return {
        "current_score": current_score,
        "ceiling_score": max(ceiling_score, current_score),
        "weekly_hours": weekly_hours,
        "exam_date": exam_date,
        "reachable_node_ids": list(result.reachable_node_ids),
        "unreachable_node_ids": list(result.unreachable_node_ids),
    }


def weak_topics(student, limit=WEAK_TOPIC_LIMIT) -> list[dict]:
    masteries = dict(
        SkillMastery.objects.filter(student=student).values_list("node_id", "mastery")
    )
    nodes = KnowledgeNode.objects.select_related("cluster").all()
    ranked = sorted(nodes, key=lambda n: masteries.get(n.id, 0))[:limit]
    return [
        {
            "node_id": n.id,
            "code": n.code,
            "title": n.title,
            "cluster": n.cluster.title,
            "mastery": masteries.get(n.id, 0),
        }
        for n in ranked
    ]


def create_snapshot(student) -> ProgressSnapshot:
    """Recalculated after each mock exam / diagnostic."""
    predicted, avg = predict_score(student)
    return ProgressSnapshot.objects.create(
        student=student,
        start_score=student.start_score,
        predicted_score=predicted,
        target_score=student.target_score,
        average_mastery=avg,
        weak_topics=weak_topics(student),
    )


def build_parent_report(student, week_start=None) -> ParentReport:
    """Weekly pulse: факт недели, динамика, риски, слабые темы, следующий шаг."""
    today = timezone.localdate()
    week_start = week_start or today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)

    attempts = Attempt.objects.filter(
        student=student, created_at__date__gte=week_start, created_at__date__lt=week_end
    )
    solved = attempts.filter(is_correct=True).count()
    total = attempts.count()

    from apps.ai_mentor.models import AiHintMessage

    hints_used = AiHintMessage.objects.filter(
        session__student=student,
        role=AiHintMessage.Role.MENTOR,
        is_blocked=False,
        created_at__date__gte=week_start, created_at__date__lt=week_end,
    ).count()

    from apps.mocks.models import MockExamResult

    mocks_completed = MockExamResult.objects.filter(
        student=student,
        completed_at__date__gte=week_start,
        completed_at__date__lt=week_end,
    ).count()

    snapshots = list(
        ProgressSnapshot.objects.filter(student=student).order_by("-created_at")[:8]
    )
    scores = [snapshot.predicted_score for snapshot in reversed(snapshots)]
    current = scores[-1] if scores else None
    previous = scores[-2] if len(scores) > 1 else None
    delta = (scores[-1] - scores[0]) if len(scores) > 1 else None
    if len(scores) == 1:
        sparkline_points = "50,20"
        sparkline_last_x, sparkline_last_y = 50, 20
    elif scores:
        low, high = min(scores), max(scores)
        score_range = high - low
        points = [
            (
                round(index * 100 / (len(scores) - 1), 1),
                round(20 if not score_range else 40 - (score - low) * 40 / score_range, 1),
            )
            for index, score in enumerate(scores)
        ]
        sparkline_points = " ".join(f"{x},{y}" for x, y in points)
        sparkline_last_x, sparkline_last_y = points[-1]
    else:
        sparkline_points = ""
        sparkline_last_x, sparkline_last_y = None, None

    open_mistakes = (
        MistakeBacklogItem.objects.filter(student=student)
        .exclude(status=MistakeBacklogItem.Status.RESOLVED)
        .count()
    )
    error_type_distribution = {
        row["error_type"]: row["total"]
        for row in (
            MistakeBacklogItem.objects.filter(student=student)
            .exclude(status=MistakeBacklogItem.Status.RESOLVED)
            .values("error_type")
            .annotate(total=Sum("error_count"))
        )
    }
    plan = get_active_plan(student)
    overdue = (
        plan.items.filter(
            status=StudyPlanItem.Status.PENDING, due_date__lt=today
        ).count()
        if plan
        else 0
    )

    risks = []
    if total == 0:
        risks.append("На этой неделе не было активности.")
    if overdue:
        risks.append(f"Просрочено пунктов плана: {overdue}.")
    if open_mistakes >= 5:
        risks.append(f"Накопилось ошибок на отработку: {open_mistakes}.")

    next_item = (
        plan.items.filter(status=StudyPlanItem.Status.PENDING)
        .select_related("node")
        .first()
        if plan
        else None
    )
    next_step = (
        f"{next_item.get_item_type_display()}: {next_item.node.title}"
        if next_item and next_item.node
        else "Пройти входную диагностику."
    )

    payload = {
        "week_fact": {
            "attempts": total,
            "solved": solved,
            "hints_used": hints_used,
            "mocks_completed": mocks_completed,
            "plan_items_done": (
                plan.items.filter(
                    status=StudyPlanItem.Status.DONE,
                    due_date__gte=week_start, due_date__lt=week_end,
                ).count()
                if plan
                else 0
            ),
        },
        "dynamics": {
            "current_predicted_score": current,
            "previous_predicted_score": previous,
            "delta": delta,
            "sparkline_points": sparkline_points,
            "sparkline_last_x": sparkline_last_x,
            "sparkline_last_y": sparkline_last_y,
            "start_score": student.start_score,
            "target_score": student.target_score,
        },
        "risks": risks,
        "weak_topics": weak_topics(student),
        "error_type_distribution": error_type_distribution,
        "next_step": next_step,
    }
    report, _ = ParentReport.objects.update_or_create(
        student=student, week_start=week_start, defaults={"payload": payload}
    )
    return report
