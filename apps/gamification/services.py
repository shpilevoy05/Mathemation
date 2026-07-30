"""XP, configurable streaks and weekly quests."""
import math
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from apps.events.models import Event
from apps.events.services import log_event

from .models import GamificationProfile, WeeklyQuest


XP_CORRECT_ATTEMPT = 10
XP_INCORRECT_ATTEMPT = 2
XP_COMPLETED_REVIEW = 15
XP_FINISHED_PLAN_ITEM = 5


def level_for_xp(xp: int) -> int:
    """Derive the level from XP; persisted level is a read-side cache."""
    return math.floor(math.sqrt(max(0, xp) / 100)) + 1


def streak_mode() -> str:
    mode = getattr(settings, "STREAK_MODE", "daily")
    if mode not in {"daily", "weekly"}:
        raise ImproperlyConfigured("STREAK_MODE must be 'daily' or 'weekly'.")
    return mode


def week_start_for(value: date | None = None) -> date:
    value = value or timezone.localdate()
    return value - timedelta(days=value.weekday())


def _period_anchor(activity_date: date) -> date:
    return activity_date if streak_mode() == "daily" else week_start_for(activity_date)


def _get_locked_profile(student) -> GamificationProfile:
    GamificationProfile.objects.get_or_create(student=student)
    return GamificationProfile.objects.select_for_update().get(student=student)


@transaction.atomic
def award_xp(student, amount: int, source: str, **event_payload) -> GamificationProfile:
    if amount < 0:
        raise ValueError("XP award cannot be negative.")
    profile = _get_locked_profile(student)
    profile.xp += amount
    profile.level = level_for_xp(profile.xp)
    profile.save(update_fields=["xp", "level"])
    log_event(
        Event.Type.XP_AWARDED,
        student=student,
        amount=amount,
        source=source,
        total_xp=profile.xp,
        level=profile.level,
        **event_payload,
    )
    # Монеты магазина идут за тем же событием: XP — прогресс и стрики,
    # монеты — покупки. Один коэффициент, чтобы курсы не разъезжались.
    from apps.economy.services import reward_for_xp

    reward_for_xp(student, source=source, amount_xp=amount, total_xp=profile.xp)
    return profile


@transaction.atomic
def advance_streak(student, activity_date: date | None = None) -> GamificationProfile:
    activity_date = activity_date or timezone.localdate()
    period = _period_anchor(activity_date)
    profile = _get_locked_profile(student)
    previous = profile.streak_period_anchor

    if previous == period:
        return profile

    period_step = timedelta(days=1 if streak_mode() == "daily" else 7)
    if previous is None:
        profile.streak_current = 1
        event_type = Event.Type.STREAK_ADVANCED
    elif period == previous + period_step:
        profile.streak_current += 1
        event_type = Event.Type.STREAK_ADVANCED
    else:
        profile.streak_current = 1
        event_type = Event.Type.STREAK_RESET

    profile.streak_best = max(profile.streak_best, profile.streak_current)
    profile.streak_period_anchor = period
    profile.save(
        update_fields=["streak_current", "streak_best", "streak_period_anchor"]
    )
    log_event(
        event_type,
        student=student,
        mode=streak_mode(),
        period_anchor=period.isoformat(),
        streak_current=profile.streak_current,
        streak_best=profile.streak_best,
    )
    return profile


@transaction.atomic
def generate_weekly_quests(student, week_start: date | None = None) -> list[WeeklyQuest]:
    """Create realistic quests from the active plan; repeated calls are safe."""
    from apps.planning.models import StudyPlanItem
    from apps.planning.services import get_active_plan
    from apps.practice.models import ReviewSchedule

    week_start = week_start_for(week_start)
    plan = get_active_plan(student)
    if plan is None:
        return []
    week_end = week_start + timedelta(days=6)
    week_items = plan.items.filter(due_date__range=(week_start, week_end))
    practice_count = week_items.filter(
        item_type=StudyPlanItem.ItemType.PRACTICE
    ).count()
    plan_item_count = week_items.count()
    review_count = ReviewSchedule.objects.filter(
        backlog_item__student=student,
        due_date__range=(week_start, week_end),
        status=ReviewSchedule.Status.PENDING,
    ).count()

    definitions = [
        (
            WeeklyQuest.QuestType.SOLVE_TASKS,
            "Решить задачи недели",
            max(3, practice_count),
            30,
        ),
        (
            WeeklyQuest.QuestType.FINISH_PLAN_ITEMS,
            "Продвинуться по плану",
            max(3, plan_item_count),
            25,
        ),
    ]
    if review_count:
        definitions.append(
            (
                WeeklyQuest.QuestType.COMPLETE_REVIEWS,
                "Закрепить сложные места",
                max(3, review_count),
                25,
            )
        )

    for quest_type, title, target_count, reward_xp in definitions:
        WeeklyQuest.objects.get_or_create(
            student=student,
            week_start=week_start,
            quest_type=quest_type,
            defaults={
                "title": title,
                "target_count": target_count,
                "reward_xp": reward_xp,
            },
        )
    return list(WeeklyQuest.objects.filter(student=student, week_start=week_start))


@transaction.atomic
def _advance_quest(student, quest_type: str, activity_date: date | None = None) -> None:
    activity_date = activity_date or timezone.localdate()
    current_week = week_start_for(activity_date)
    generate_weekly_quests(student, current_week)
    quests = WeeklyQuest.objects.select_for_update().filter(
        student=student,
        week_start=current_week,
        quest_type=quest_type,
        completed=False,
    )
    for quest in quests:
        quest.progress_count = min(quest.target_count, quest.progress_count + 1)
        just_completed = quest.progress_count >= quest.target_count
        quest.completed = just_completed
        quest.save(update_fields=["progress_count", "completed"])
        if just_completed:
            award_xp(
                student,
                quest.reward_xp,
                source="weekly_quest",
                quest_id=quest.id,
                quest_type=quest.quest_type,
            )
            log_event(
                Event.Type.QUEST_COMPLETED,
                student=student,
                quest_id=quest.id,
                quest_type=quest.quest_type,
                reward_xp=quest.reward_xp,
                week_start=quest.week_start.isoformat(),
            )


@transaction.atomic
def record_attempt_activity(
    student, is_correct: bool | None, activity_date: date | None = None
) -> GamificationProfile:
    advance_streak(student, activity_date)
    if is_correct is not None:
        award_xp(
            student,
            XP_CORRECT_ATTEMPT if is_correct else XP_INCORRECT_ATTEMPT,
            source="attempt",
            is_correct=is_correct,
        )
    _advance_quest(student, WeeklyQuest.QuestType.SOLVE_TASKS, activity_date)
    return GamificationProfile.objects.get(student=student)


@transaction.atomic
def record_review_activity(student, activity_date: date | None = None) -> GamificationProfile:
    advance_streak(student, activity_date)
    award_xp(student, XP_COMPLETED_REVIEW, source="review")
    _advance_quest(student, WeeklyQuest.QuestType.COMPLETE_REVIEWS, activity_date)
    return GamificationProfile.objects.get(student=student)


@transaction.atomic
def record_plan_item_activity(student, activity_date: date | None = None) -> GamificationProfile:
    advance_streak(student, activity_date)
    award_xp(student, XP_FINISHED_PLAN_ITEM, source="plan_item")
    _advance_quest(student, WeeklyQuest.QuestType.FINISH_PLAN_ITEMS, activity_date)
    return GamificationProfile.objects.get(student=student)


def gamification_snapshot(student, on_date: date | None = None) -> dict:
    on_date = on_date or timezone.localdate()
    quests = generate_weekly_quests(student, week_start_for(on_date))
    profile, _ = GamificationProfile.objects.get_or_create(student=student)
    return {
        "xp": profile.xp,
        "level": level_for_xp(profile.xp),
        "streak_current": profile.streak_current,
        "streak_best": profile.streak_best,
        "streak_mode": streak_mode(),
        "quests": [
            {
                "id": quest.id,
                "week_start": quest.week_start,
                "title": quest.title,
                "quest_type": quest.quest_type,
                "target_count": quest.target_count,
                "progress_count": quest.progress_count,
                "completed": quest.completed,
                "reward_xp": quest.reward_xp,
                "progress_percent": min(
                    100, round(quest.progress_count * 100 / quest.target_count)
                ),
            }
            for quest in quests
        ],
    }

