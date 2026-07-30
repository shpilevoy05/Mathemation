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
                  group: StudentGroup | None = None, ttl_days: int = INVITE_TTL_DAYS) -> Invite:
    return Invite.objects.create(
        code=secrets.token_urlsafe(INVITE_CODE_BYTES),
        role=role,
        group=group,
        created_by=created_by,
        expires_at=timezone.now() + timedelta(days=ttl_days),
    )


@transaction.atomic
def accept_invite(code: str, *, username: str, password: str) -> User:
    """Зарегистрировать человека по коду и завести ему профиль роли."""
    invite = (
        Invite.objects.select_for_update().filter(code=code).first()
        if Invite.objects.filter(code=code).exists()
        else None
    )
    if invite is None:
        raise ValidationError("Код приглашения не найден.")
    if invite.is_used:
        raise ValidationError("Код приглашения уже использован.")
    if invite.expires_at < timezone.now():
        raise ValidationError("Срок действия кода истёк.")
    if User.objects.filter(username=username).exists():
        raise ValidationError("Пользователь с таким логином уже существует.")

    user = User.objects.create_user(username=username, password=password, role=invite.role)
    if invite.role == User.Role.STUDENT:
        profile = StudentProfile.objects.create(user=user)
        if invite.group is not None:
            invite.group.students.add(profile)
    elif invite.role == User.Role.PARENT:
        ParentProfile.objects.create(user=user)

    invite.used_by = user
    invite.used_at = timezone.now()
    invite.save(update_fields=["used_by", "used_at"])
    return user


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
