"""Права доступа по ролям для API.

Роли и группы проверяются в `apps.web.permissions` — одно правило и для
серверных страниц, и для API. Панель ведёт методист; флаг `is_staff` относится
к Django-админке и панель сам по себе не открывает.
"""

from __future__ import annotations

from rest_framework import permissions

from apps.web.permissions import is_expert, is_methodist


class IsPlatformAdmin(permissions.BasePermission):
    """Панель администратора: методист или суперпользователь."""

    message = "Нужны права методиста платформы."

    def has_permission(self, request, view) -> bool:
        return is_methodist(request.user)


class IsExpert(permissions.BasePermission):
    """Очередь проверки второй части."""

    message = "Нужны права эксперта."

    def has_permission(self, request, view) -> bool:
        return is_expert(request.user) or is_methodist(request.user)
