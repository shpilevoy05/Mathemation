"""Требование второго фактора на входе в бэкофис.

Проверять фактор во вьюхе входа недостаточно: в систему пускает не только наша
форма, но и `/admin/login/`, а завтра появится ещё один вход. Поэтому условие
одно и стоит перед каждым запросом: у сотрудника в сессии должна быть отметка
о пройденном факторе, иначе он видит только страницу фактора и выход.

Отдельный случай — сотрудник, которому фактор нужен, но ещё не настроен: его
не выкидывают, а ведут настраивать. Иначе включение требования означало бы
одновременную потерю доступа всей командой.
"""

from __future__ import annotations

from django.shortcuts import redirect
from django.urls import reverse

from .two_factor import is_required_for
from .two_factor_services import get_device, session_passed


class TwoFactorMiddleware:
    """Пускает сотрудника дальше только после второго фактора."""

    def __init__(self, get_response):
        self.get_response = get_response

    def _allowed(self, path: str) -> bool:
        # Страницы самого фактора, выход и служебные точки: без них человек
        # не сможет ни пройти проверку, ни выйти из аккаунта.
        allowed = (
            reverse("two_factor_verify"),
            reverse("two_factor_setup"),
            reverse("logout"),
            reverse("login"),
            "/healthz",
            "/readyz",
            "/static/",
        )
        return any(path.startswith(prefix) for prefix in allowed)

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and is_required_for(user)
            and not session_passed(request)
            and not self._allowed(request.path)
        ):
            device = get_device(user)
            target = "two_factor_verify" if device is not None and device.is_confirmed else "two_factor_setup"
            return redirect(target)
        return self.get_response(request)
