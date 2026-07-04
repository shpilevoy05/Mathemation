"""AI mentor rules: available only inside regular lesson tasks, max 2 leading
hints, never a final answer, everything is logged for the parent."""
from django.conf import settings

from apps.practice.models import Attempt

from .models import AiHintMessage, AiHintSession
from .providers import get_provider

DISALLOWED_CONTEXTS = {Attempt.Context.MOCK, Attempt.Context.DIAGNOSTIC, Attempt.Context.REVIEW}

ESCALATION_TEXT = (
    "Подсказки исчерпаны. Если решение всё ещё не складывается — отправь свою "
    "попытку на проверку эксперту, он разберёт её по шагам."
)


class HintNotAllowed(Exception):
    pass


def request_hint(student, assignment, question: str, context: str) -> dict:
    """Return {"session", "text", "escalated"} or raise HintNotAllowed."""
    if context in DISALLOWED_CONTEXTS:
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
    text = get_provider().generate_hint(assignment, question, session.hints_used)
    AiHintMessage.objects.create(
        session=session, role=AiHintMessage.Role.MENTOR, text=text
    )
    return {"session": session, "text": text, "escalated": False}
