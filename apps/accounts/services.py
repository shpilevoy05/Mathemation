"""Приглашения, группы и деактивация учеников."""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Invite, ParentProfile, StudentGroup, StudentProfile, User

INVITE_TTL_DAYS = 14
INVITE_CODE_BYTES = 8


def create_invite(created_by: User | None, *, role: str = User.Role.STUDENT,
                  group: StudentGroup | None = None,
                  for_student: StudentProfile | None = None,
                  ttl_days: int = INVITE_TTL_DAYS) -> Invite:
    if for_student is not None and role != User.Role.PARENT:
        raise ValidationError("Ученика можно указать только для приглашения родителя.")
    invite = Invite.objects.create(
        code=secrets.token_urlsafe(INVITE_CODE_BYTES),
        role=role,
        group=group,
        for_student=for_student,
        created_by=created_by,
        expires_at=timezone.now() + timedelta(days=ttl_days),
    )
    if for_student is not None:
        _log_account_event(
            "parent_invite.create", actor=created_by, student=for_student,
            invite_id=invite.pk,
        )
    return invite


@transaction.atomic
def accept_invite(
    code: str, *, username: str, email: str, password: str,
    consent_ip: str | None = None, consent_user_agent: str = "",
    parent_child_consent: bool = False,
) -> User:
    """Зарегистрировать человека по коду и завести ему профиль роли."""
    invite = Invite.objects.select_for_update().select_related("for_student").filter(code=code).first()
    if invite is None:
        raise ValidationError("Код приглашения не найден.")
    if invite.is_used:
        raise ValidationError("Код приглашения уже использован.")
    if invite.expires_at < timezone.now():
        raise ValidationError("Срок действия кода истёк.")
    if User.objects.filter(username=username).exists():
        raise ValidationError("Пользователь с таким логином уже существует.")
    email = email.strip().lower()
    if User.objects.filter(email__iexact=email, is_active=True).exists():
        raise ValidationError(
            "Этот адрес электронной почты уже используется другим активным пользователем."
        )

    user = User.objects.create_user(
        username=username, email=email, password=password, role=invite.role
    )
    if invite.role == User.Role.STUDENT:
        profile = StudentProfile.objects.create(user=user)
        if invite.group is not None:
            invite.group.students.add(profile)
    elif invite.role == User.Role.PARENT:
        parent = ParentProfile.objects.create(user=user)
        if invite.for_student_id:
            if not parent_child_consent:
                raise ValidationError("Нужно согласие законного представителя.")
            parent.children.add(invite.for_student)

    from apps.legal.services import record_current_consents

    record_current_consents(
        user,
        ip=consent_ip,
        user_agent=consent_user_agent,
        subject_students=[invite.for_student] if invite.for_student_id else [],
    )

    invite.used_by = user
    invite.used_at = timezone.now()
    invite.save(update_fields=["used_by", "used_at"])
    if invite.for_student_id:
        _log_account_event(
            "parent_invite.accept", actor=user, student=invite.for_student,
            invite_id=invite.pk,
        )
    return user


@transaction.atomic
def accept_parent_invite(
    invite: Invite, parent: ParentProfile, *, parent_child_consent: bool,
    consent_ip: str | None = None, consent_user_agent: str = "",
) -> StudentProfile:
    invite = Invite.objects.select_for_update().select_related("for_student").get(pk=invite.pk)
    if invite.role != User.Role.PARENT or invite.for_student_id is None:
        raise ValidationError("Это приглашение не предназначено для привязки родителя.")
    if invite.is_used:
        raise ValidationError("Код приглашения уже использован.")
    if invite.expires_at < timezone.now():
        raise ValidationError("Срок действия кода истёк.")
    if not parent_child_consent:
        raise ValidationError("Нужно согласие законного представителя.")
    parent.children.add(invite.for_student)
    from apps.legal.services import record_current_consents

    record_current_consents(
        parent.user,
        ip=consent_ip,
        user_agent=consent_user_agent,
        subject_students=[invite.for_student],
    )
    invite.used_by = parent.user
    invite.used_at = timezone.now()
    invite.save(update_fields=["used_by", "used_at"])
    _log_account_event(
        "parent_invite.accept", actor=parent.user, student=invite.for_student,
        invite_id=invite.pk,
    )
    return invite.for_student


def active_parent_invites(student: StudentProfile):
    return Invite.objects.filter(
        for_student=student,
        role=User.Role.PARENT,
        used_by__isnull=True,
        expires_at__gt=timezone.now(),
    )


def create_parent_invite(student: StudentProfile) -> Invite:
    return create_invite(
        student.user, role=User.Role.PARENT, for_student=student
    )


def revoke_parent_invite(student: StudentProfile, invite_id: int) -> Invite:
    invite = Invite.objects.filter(
        pk=invite_id,
        for_student=student,
        role=User.Role.PARENT,
        used_by__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()
    if invite is None:
        raise ValidationError("Активное приглашение не найдено.")
    invite.expires_at = timezone.now()
    invite.save(update_fields=["expires_at"])
    _log_account_event(
        "parent_invite.revoke", actor=student.user, student=student,
        invite_id=invite.pk,
    )
    return invite


@transaction.atomic
def update_account(user: User, *, first_name: str, last_name: str, email: str,
                   exam_date=None, weekly_hours: int | None = None) -> User:
    email = email.strip().lower()
    if User.objects.filter(email__iexact=email, is_active=True).exclude(pk=user.pk).exists():
        raise ValidationError(
            "Этот адрес электронной почты уже используется другим активным пользователем."
        )
    user.first_name = first_name.strip()
    user.last_name = last_name.strip()
    user.email = email
    user.save(update_fields=["first_name", "last_name", "email"])
    if hasattr(user, "student_profile"):
        student = user.student_profile
        normalized_weekly_hours = (
            weekly_hours if weekly_hours is not None else student.weekly_hours
        )
        schedule_changed = (
            student.exam_date != exam_date
            or student.weekly_hours != normalized_weekly_hours
        )
        student.exam_date = exam_date
        student.weekly_hours = normalized_weekly_hours
        student.save(update_fields=["exam_date", "weekly_hours"])
        if schedule_changed:
            from apps.planning.models import PlanChangeLog
            from apps.planning.services import rebuild_unfinished_plan

            rebuild_unfinished_plan(
                student,
                reason=PlanChangeLog.Reason.MANUAL,
                description=(
                    "Расписание пересобрано после изменения даты экзамена "
                    "или недельной нагрузки."
                ),
                is_major=False,
            )
    return user


def issue_temporary_password(user: User) -> str:
    temporary_password = secrets.token_urlsafe(18)
    user.set_password(temporary_password)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password"])
    return temporary_password


def clear_password_change_requirement(user: User) -> None:
    if user.must_change_password:
        user.must_change_password = False
        user.save(update_fields=["must_change_password"])


def anonymize_account(user: User) -> User:
    if hasattr(user, "student_profile"):
        user.student_profile.parents.clear()
    if hasattr(user, "parent_profile"):
        user.parent_profile.children.clear()
    user.is_active = False
    user.username = f"deleted-{user.pk}"
    user.first_name = ""
    user.last_name = ""
    user.email = ""
    user.set_unusable_password()
    user.save(update_fields=[
        "is_active", "username", "first_name", "last_name", "email", "password",
    ])
    return user


def _log_account_event(action: str, *, actor: User | None,
                       student: StudentProfile | None = None, **payload) -> None:
    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.ADMIN_ACTION,
        student=student,
        action=action,
        actor_id=getattr(actor, "pk", None),
        actor=getattr(actor, "username", ""),
        **payload,
    )


def deactivate_student(student: StudentProfile) -> StudentProfile:
    """Отключить доступ, сохранив историю.

    Удалять ученика нельзя: вместе с ним каскадом уходят попытки, ошибки,
    работы второй части и снапшоты прогресса — данные, на которых держатся
    калибровка прогноза и отчёты родителю.
    """
    user = student.user
    user.is_active = False
    user.save(update_fields=["is_active"])
    return student


def reactivate_student(student: StudentProfile) -> StudentProfile:
    user = student.user
    user.is_active = True
    user.save(update_fields=["is_active"])
    return student


def set_group_students(group: StudentGroup, students) -> StudentGroup:
    group.students.set(students)
    return group


def active_students(group: StudentGroup | None = None):
    queryset = StudentProfile.objects.filter(user__is_active=True)
    return queryset.filter(groups=group) if group is not None else queryset
