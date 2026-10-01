from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import StudentProfile, User

from .models import ConsentRecord, DataDeletionRequest, Feedback

EXPORT_ROW_LIMIT = 5000


def _version_for(kind: str) -> str:
    key = "terms" if kind == ConsentRecord.Kind.TERMS else "privacy"
    return settings.LEGAL_DOCUMENT_VERSIONS[key]


def is_consent_exempt(user: User) -> bool:
    return bool(
        user.is_superuser
        or user.is_staff
        or user.role in {User.Role.METHODIST, User.Role.EXPERT}
    )


def has_current_consents(user: User) -> bool:
    if is_consent_exempt(user):
        return True
    required = (
        (ConsentRecord.Kind.TERMS, settings.LEGAL_DOCUMENT_VERSIONS["terms"]),
        (ConsentRecord.Kind.PERSONAL_DATA, settings.LEGAL_DOCUMENT_VERSIONS["privacy"]),
    )
    for kind, version in required:
        if not ConsentRecord.objects.filter(
            user=user, kind=kind, document_version=version
        ).exists():
            return False
    if hasattr(user, "parent_profile"):
        child_ids = set(user.parent_profile.children.values_list("pk", flat=True))
        consented_ids = set(
            ConsentRecord.objects.filter(
                user=user,
                kind=ConsentRecord.Kind.PARENT_FOR_CHILD,
                document_version=settings.LEGAL_DOCUMENT_VERSIONS["privacy"],
                subject_student_id__in=child_ids,
            ).values_list("subject_student_id", flat=True)
        )
        if child_ids - consented_ids:
            return False
    return True


@transaction.atomic
def record_current_consents(
    user: User, *, ip: str | None, user_agent: str,
    subject_students=(),
) -> list[ConsentRecord]:
    records = []
    common = {"ip": ip or None, "user_agent": (user_agent or "")[:300]}
    for kind in (ConsentRecord.Kind.TERMS, ConsentRecord.Kind.PERSONAL_DATA):
        version = _version_for(kind)
        record = ConsentRecord.objects.filter(
            user=user, kind=kind, document_version=version,
            subject_student__isnull=True,
        ).first()
        if record is None:
            record = ConsentRecord.objects.create(
                user=user, kind=kind, document_version=version, **common
            )
        records.append(record)
    for student in subject_students:
        record = ConsentRecord.objects.filter(
            user=user,
            kind=ConsentRecord.Kind.PARENT_FOR_CHILD,
            document_version=settings.LEGAL_DOCUMENT_VERSIONS["privacy"],
            subject_student=student,
        ).first()
        if record is None:
            record = ConsentRecord.objects.create(
                user=user,
                kind=ConsentRecord.Kind.PARENT_FOR_CHILD,
                document_version=settings.LEGAL_DOCUMENT_VERSIONS["privacy"],
                subject_student=student,
                **common,
            )
        records.append(record)
    return records


def _limited_values(queryset, *fields):
    return list(queryset.order_by("pk").values(*fields)[:EXPORT_ROW_LIMIT])


def export_user_data(user: User) -> dict:
    """Собрать только данные самого пользователя с ограничением каждой коллекции."""
    data = {
        "exported_at": timezone.now(),
        "limits": {"rows_per_collection": EXPORT_ROW_LIMIT},
        "profile": {
            "id": user.pk,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "role": user.role,
            "date_joined": user.date_joined,
        },
        "consents": _limited_values(
            ConsentRecord.objects.filter(user=user),
            "id", "kind", "document_version", "subject_student_id",
            "accepted_at", "ip", "user_agent",
        ),
        "attempts": [],
        "plan_items": [],
        "mistakes": [],
        "hint_sessions": [],
        "hint_messages": [],
        "mock_results": [],
        "expert_reviews": [],
        "wallet_ledger": [],
        "events": [],
    }
    if hasattr(user, "parent_profile"):
        data["profile"]["child_ids"] = list(
            user.parent_profile.children.order_by("pk").values_list("pk", flat=True)
        )
    if not hasattr(user, "student_profile"):
        return data

    student = user.student_profile
    data["profile"]["student"] = {
        "id": student.pk,
        "target_score": student.target_score,
        "exam_date": student.exam_date,
        "start_score": student.start_score,
        "weekly_hours": student.weekly_hours,
    }
    from apps.ai_mentor.models import AiHintMessage, AiHintSession
    from apps.economy.models import LedgerEntry
    from apps.events.models import Event
    from apps.expert_review.models import ExpertReviewRequest
    from apps.mocks.models import MockExamResult
    from apps.planning.models import StudyPlanItem
    from apps.practice.models import Attempt, MistakeBacklogItem

    data["attempts"] = _limited_values(
        Attempt.objects.filter(student=student),
        "id", "assignment_id", "assignment_version_id", "context",
        "submitted_answer", "is_correct", "diagnostic_result_id", "mock_result_id",
        "created_at",
    )
    data["plan_items"] = _limited_values(
        StudyPlanItem.objects.filter(plan__student=student),
        "id", "plan_id", "node_id", "item_type", "order", "week_index",
        "due_date", "status", "completed_at",
    )
    data["mistakes"] = _limited_values(
        MistakeBacklogItem.objects.filter(student=student),
        "id", "assignment_id", "node_id", "status", "error_count", "error_type",
        "created_at", "resolved_at",
    )
    sessions = AiHintSession.objects.filter(student=student)
    data["hint_sessions"] = _limited_values(
        sessions, "id", "assignment_id", "node_id", "hints_used",
        "escalated_to_expert", "created_at",
    )
    data["hint_messages"] = _limited_values(
        AiHintMessage.objects.filter(session__student=student),
        "id", "session_id", "role", "text", "is_blocked", "created_at",
    )
    data["mock_results"] = _limited_values(
        MockExamResult.objects.filter(student=student),
        "id", "exam_id", "status", "primary_score", "part2_primary_score",
        "scaled_score", "time_expired", "started_at", "completed_at",
    )
    data["expert_reviews"] = _limited_values(
        ExpertReviewRequest.objects.filter(student=student),
        "id", "assignment_id", "attempt_id", "mock_result_id", "status",
        "reviewer_id", "score_by_criteria", "total_score", "lost_points",
        "created_at", "reviewed_at",
    )
    data["wallet_ledger"] = _limited_values(
        LedgerEntry.objects.filter(wallet__student=student),
        "id", "amount", "reason", "reference", "balance_after", "comment", "created_at",
    )
    data["events"] = _limited_values(
        Event.objects.filter(student=student),
        "id", "event_type", "payload", "created_at",
    )
    return data


def request_data_deletion(user: User) -> DataDeletionRequest:
    pending = DataDeletionRequest.objects.filter(
        user=user, status=DataDeletionRequest.Status.PENDING
    ).first()
    return pending or DataDeletionRequest.objects.create(user=user)


@transaction.atomic
def anonymize_user(
    deletion_request: DataDeletionRequest, *, processed_by: User, comment: str = ""
) -> DataDeletionRequest:
    deletion_request = DataDeletionRequest.objects.select_for_update().select_related("user").get(
        pk=deletion_request.pk
    )
    if deletion_request.status != DataDeletionRequest.Status.PENDING:
        raise ValidationError("Запрос уже обработан.")
    user = deletion_request.user
    student = getattr(user, "student_profile", None)
    if student is not None:
        from apps.ai_mentor.services import redact_student_hint_messages
        from apps.expert_review.services import delete_student_solution_files

        delete_student_solution_files(student)
        redact_student_hint_messages(student)
    from apps.accounts.services import anonymize_account

    anonymize_account(user)
    deletion_request.status = DataDeletionRequest.Status.DONE
    deletion_request.processed_by = processed_by
    deletion_request.processed_at = timezone.now()
    deletion_request.comment = comment
    deletion_request.save(
        update_fields=["status", "processed_by", "processed_at", "comment"]
    )
    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.ADMIN_ACTION,
        student=student,
        action="data_deletion.complete",
        target=f"deletion_request:{deletion_request.pk}",
        actor_id=processed_by.pk,
        actor=processed_by.username,
    )
    return deletion_request


def create_feedback(user: User, *, message: str, page_url: str = "") -> Feedback:
    feedback = Feedback.objects.create(
        user=user, page_url=(page_url or "")[:500], message=message
    )
    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.FEEDBACK_CREATED,
        student=getattr(user, "student_profile", None),
        feedback_id=feedback.pk,
        user_id=user.pk,
    )
    return feedback


def update_feedback(feedback: Feedback, *, status: str, staff_comment: str) -> Feedback:
    feedback.status = status
    feedback.staff_comment = staff_comment
    feedback.save(update_fields=["status", "staff_comment"])
    return feedback
