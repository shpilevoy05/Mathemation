"""AI mentor rules: available only inside regular lesson tasks, max 2 leading
hints, never a final answer, everything is logged for the parent."""
from django.conf import settings

from apps.practice.models import Attempt

from .guardrails import check_hint, contains_final_answer
from .models import AiHintMessage, AiHintSession
from .providers import UNCERTAINTY_NOTE, get_provider

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


def mentor_available(context: str) -> bool:
    """The mentor is an invariant of a regular lesson context only."""
    return context == Attempt.Context.LESSON


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

    session.hints_used += 1
    session.save(update_fields=["hints_used"])
    provider_text = get_provider().generate_hint(assignment, question, session.hints_used)
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
    )
    log_event(
        Event.Type.HINT_ISSUED,
        student=student,
        assignment_id=assignment.id,
        hint_index=session.hints_used,
    )
    return {"session": session, "text": text, "escalated": False}
