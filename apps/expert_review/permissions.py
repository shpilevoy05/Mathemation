"""Object-level права на работу ученика.

Работа второй части — персональные данные ребёнка. Доступ имеют только:
сам ученик, его родитель, эксперт (назначенный либо ещё не назначенный — он
берёт работу в очереди) и методист.

Роли проверяются через `apps.web.permissions`, чтобы правило было одно и то же
для веб-кабинетов и для API. Отказ отдаётся как 404, а не 403: 403 подтверждает
существование объекта.
"""

from __future__ import annotations

from apps.web.permissions import is_expert, is_methodist


def can_view_solution(user, review) -> bool:
    """Может ли `user` видеть файл решения из `review`."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or is_methodist(user):
        return True

    student = getattr(user, "student_profile", None)
    if student is not None and review.student_id == student.pk:
        return True

    parent = getattr(user, "parent_profile", None)
    if parent is not None and parent.children.filter(pk=review.student_id).exists():
        return True

    if is_expert(user):
        # Назначенный эксперт — всегда; свободную работу может взять любой.
        return review.reviewer_id in (None, user.pk)

    return False
