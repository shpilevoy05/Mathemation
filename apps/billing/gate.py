"""Проверка подписки на границе приложения: API и веб-страницы.

Правило одно, а точек входа две, и ведут они себя по-разному: API обязан
ответить машиночитаемым отказом, страница — привести человека на витрину.
Поэтому здесь два тонких адаптера над `access.feature_access`, а не два
независимых правила.
"""

from __future__ import annotations

from functools import wraps
from urllib.parse import urlencode

from django.shortcuts import redirect
from rest_framework import permissions

from .access import deny_payload, feature_access


class HasFeature(permissions.BasePermission):
    """DRF-разрешение. View задаёт `feature = Feature.<...>`."""

    def has_permission(self, request, view):
        feature = getattr(view, "feature", "")
        if not feature:
            return True
        access = feature_access(request.user, feature)
        if access.allowed:
            return True
        # Тело отказа кладём на request: DRF отдаёт только `detail`, а
        # интерфейсу нужны причина и ссылка на тарифы.
        self.message = deny_payload(access)
        return False


def require_feature(feature: str):
    """Декоратор страницы: без доступа уводит на витрину с объяснением."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            access = feature_access(request.user, feature)
            if access.allowed:
                return view(request, *args, **kwargs)
            query = urlencode({"locked": feature, "reason": access.reason})
            return redirect(f"/pricing/?{query}")

        return wrapper

    return decorator
