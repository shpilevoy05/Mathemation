"""AI mentor rules: available only inside regular lesson tasks, max 2 leading
hints, never a final answer, everything is logged for the parent."""
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.practice.models import Attempt

from .guardrails import check_hint, contains_final_answer
from .models import AiHintMessage, AiHintSession
from .providers import (
    HintProvider,
    LLMHintProvider,
    MockHintProvider,
    UNCERTAINTY_NOTE,
    get_provider,
)

DISALLOWED_CONTEXTS = {Attempt.Context.MOCK, Attempt.Context.DIAGNOSTIC, Attempt.Context.REVIEW}

ESCALATION_TEXT = (
    "Подсказки исчерпаны. Если решение всё ещё не складывается — отправь свою "
    "попытку на проверку эксперту, он разберёт её по шагам."
)
GUARDRAIL_BLOCK_TEXT = (
    "Не могу поручиться за этот шаг. Давай спросим живого преподавателя."
)


class HintNotAllowed(Exception):
    pass


class DailyHintLimitExceeded(Exception):
    pass


def redact_student_hint_messages(student) -> int:
    """Удалить тексты диалога, сохранив обезличенную статистику сессий."""
    return AiHintMessage.objects.filter(session__student=student).update(text="")


def mentor_available(context: str) -> bool:
    """The mentor is an invariant of a regular lesson context only."""
    return context == Attempt.Context.LESSON


def _provider_usage(provider_text) -> dict:
    prompt_tokens = max(int(getattr(provider_text, "prompt_tokens", 0) or 0), 0)
    completion_tokens = max(
        int(getattr(provider_text, "completion_tokens", 0) or 0), 0
    )
    input_rate = Decimal(str(settings.AI_MENTOR_COST_PER_1K_INPUT))
    output_rate = Decimal(str(settings.AI_MENTOR_COST_PER_1K_OUTPUT))
    cost = (
        Decimal(prompt_tokens) * input_rate / Decimal(1000)
        + Decimal(completion_tokens) * output_rate / Decimal(1000)
    ).quantize(Decimal("0.000001"))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "estimated_cost_rub": cost,
        "counts_toward_daily_limit": True,
    }


def mentor_usage_summary() -> dict:
    """Сводка расходов для методиста за сегодня и последние семь дней."""
    today = timezone.localdate()
    week_start = today - timezone.timedelta(days=6)
    hints = AiHintMessage.objects.filter(counts_toward_daily_limit=True)
    week_hints = hints.filter(created_at__date__gte=week_start)
    totals = week_hints.aggregate(
        hints=Count("id"),
        prompt_tokens=Sum("prompt_tokens"),
        completion_tokens=Sum("completion_tokens"),
        estimated_cost_rub=Sum("estimated_cost_rub"),
    )
    top_students = list(
        week_hints.values("session__student_id", "session__student__user__username")
        .annotate(hints=Count("id"))
        .order_by("-hints", "session__student_id")[:5]
    )
    return {
        "hints_today": hints.filter(created_at__date=today).count(),
        "hints_7_days": totals["hints"] or 0,
        "prompt_tokens": totals["prompt_tokens"] or 0,
        "completion_tokens": totals["completion_tokens"] or 0,
        "estimated_cost_rub": totals["estimated_cost_rub"] or Decimal("0"),
        "top_students": top_students,
    }


@transaction.atomic
def request_hint(student, assignment, question: str, context: str) -> dict:
    """Return {"session", "text", "escalated"} or raise HintNotAllowed."""
    if not mentor_available(context):
        raise HintNotAllowed("Наставник недоступен на пробниках, диагностике и отработке.")

    first_tag = assignment.skill_tags.select_related("node").first()
    session, _ = AiHintSession.objects.get_or_create(
        student=student, assignment=assignment,
        defaults={"node": first_tag.node if first_tag else None},
    )
    AiHintMessage.objects.create(
        session=session, role=AiHintMessage.Role.STUDENT, text=question
    )

    if session.hints_used >= settings.AI_MENTOR_MAX_HINTS:
        session.escalated_to_expert = True
        session.save(update_fields=["escalated_to_expert"])
        AiHintMessage.objects.create(
            session=session, role=AiHintMessage.Role.MENTOR, text=ESCALATION_TEXT
        )
        return {"session": session, "text": ESCALATION_TEXT, "escalated": True}

    # Блокировка профиля не даёт двум параллельным запросам одновременно
    # пройти проверку последнего доступного места дневного лимита.
    type(student).objects.select_for_update().get(pk=student.pk)
    hints_today = AiHintMessage.objects.filter(
        session__student=student,
        counts_toward_daily_limit=True,
        created_at__date=timezone.localdate(),
    ).count()
    if hints_today >= settings.AI_MENTOR_DAILY_HINT_LIMIT:
        raise DailyHintLimitExceeded(
            "Дневной лимит подсказок исчерпан. Новые подсказки будут доступны завтра."
        )

    session.hints_used += 1
    session.save(update_fields=["hints_used"])
    provider = get_provider()
    provider_name = "llm" if isinstance(provider, LLMHintProvider) else "mock"
    if isinstance(provider, HintProvider):
        provider_text = provider.generate_hint(
            assignment, question, session.hints_used, session=session
        )
    else:
        # Backward compatibility for small duck-typed providers used by deployments.
        provider_text = provider.generate_hint(assignment, question, session.hints_used)
    if provider_text is None:
        provider_name = "mock_fallback"
        provider_text = MockHintProvider().generate_hint(
            assignment, question, session.hints_used, session=session
        )
        if UNCERTAINTY_NOTE not in provider_text:
            provider_text = f"{provider_text}\n\n{UNCERTAINTY_NOTE}"
    usage = _provider_usage(provider_text)
    guardrail = check_hint(provider_text)
    failed_claims = list(guardrail.failed_claims)
    if (
        assignment.exam_part == assignment.Part.PART1
        and assignment.correct_answer
        and contains_final_answer(
            provider_text, assignment.correct_answer, assignment.statement
        )
    ):
        failed_claims.append("final_answer")

    from apps.events.models import Event
    from apps.events.services import log_event

    if not guardrail.passed or failed_claims:
        AiHintMessage.objects.create(
            session=session,
            role=AiHintMessage.Role.MENTOR,
            text=provider_text,
            is_blocked=True,
            failed_claims=failed_claims,
            unverified_claims=guardrail.unverified_claims,
            **usage,
        )
        session.escalated_to_expert = True
        session.save(update_fields=["escalated_to_expert"])
        AiHintMessage.objects.create(
            session=session,
            role=AiHintMessage.Role.MENTOR,
            text=GUARDRAIL_BLOCK_TEXT,
        )
        log_event(
            Event.Type.HINT_BLOCKED_BY_GUARDRAIL,
            student=student,
            assignment_id=assignment.id,
            hint_index=session.hints_used,
            failed_claims=failed_claims,
        )
        return {
            "session": session,
            "text": GUARDRAIL_BLOCK_TEXT,
            "escalated": True,
        }

    text = provider_text
    if guardrail.unverified_claims and UNCERTAINTY_NOTE not in text:
        text = f"{text}\n\n{UNCERTAINTY_NOTE}"
    AiHintMessage.objects.create(
        session=session,
        role=AiHintMessage.Role.MENTOR,
        text=text,
        unverified_claims=guardrail.unverified_claims,
        **usage,
    )
    log_event(
        Event.Type.HINT_ISSUED,
        student=student,
        assignment_id=assignment.id,
        hint_index=session.hints_used,
        provider=provider_name,
    )
    return {"session": session, "text": text, "escalated": False}
