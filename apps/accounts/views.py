"""Вход и саморегистрация по коду приглашения."""

import logging

from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse

from django.contrib.auth.decorators import login_required

from .forms import InviteRegistrationForm, TwoFactorCodeForm
from .services import accept_invite
from .throttling import client_ip, invite_guard, login_guard, two_factor_guard
from .two_factor import is_required_for, provisioning_uri
from .two_factor_services import (
    check_code,
    confirm_enrollment,
    get_device,
    mark_session_passed,
    session_passed,
    start_enrollment,
)

logger = logging.getLogger("matemacia.security")

BLOCKED_MESSAGE = (
    "Слишком много неудачных попыток. Подождите 15 минут или напишите куратору."
)
INVITE_BLOCKED_MESSAGE = (
    "Слишком много попыток ввести код. Попробуйте через час или попросите "
    "куратора выдать новый код."
)
TWO_FACTOR_BLOCKED_MESSAGE = (
    "Слишком много неверных кодов. Подождите 15 минут — за это время код в "
    "приложении сменится несколько раз."
)


class ThrottledLoginView(LoginView):
    """Вход с ограничением перебора.

    Считаем и по адресу, и по логину: за одним адресом может сидеть весь класс,
    а один логин подбирают с разных адресов.
    """

    template_name = "registration/login.html"

    def _senders(self, request) -> list[str]:
        username = (request.POST.get("username") or "").strip().lower()
        senders = [f"ip:{client_ip(request)}"]
        if username:
            senders.append(f"user:{username}")
        return senders

    def post(self, request, *args, **kwargs):
        senders = self._senders(request)
        if login_guard.is_blocked(senders):
            logger.warning("login blocked: senders=%s", senders)
            form = self.get_form()
            form.add_error(None, BLOCKED_MESSAGE)
            return self.render_to_response(self.get_context_data(form=form))
        self._current_senders = senders
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        login_guard.reset(getattr(self, "_current_senders", []))
        return super().form_valid(form)

    def form_invalid(self, form):
        login_guard.register_failure(getattr(self, "_current_senders", []))
        return super().form_invalid(form)


@login_required
def two_factor_setup(request):
    """Настройка второго фактора: секрет, подтверждение и резервные коды."""
    if not is_required_for(request.user):
        return redirect("dashboard")
    device = get_device(request.user)
    if device is not None and device.is_confirmed:
        return redirect("two_factor_verify" if not session_passed(request) else "dashboard")

    form = TwoFactorCodeForm(request.POST or None)
    recovery_codes = None
    if request.method == "POST" and form.is_valid():
        recovery_codes = confirm_enrollment(request.user, form.cleaned_data["code"])
        if recovery_codes is None:
            form.add_error("code", "Код не подошёл. Проверьте время на телефоне.")
        else:
            # Фактор настроен — эта же сессия считается пройденной, второй раз
            # вводить код сразу после настройки бессмысленно.
            mark_session_passed(request)
            device = get_device(request.user)
    if recovery_codes is None:
        device = device or start_enrollment(request.user)

    return render(request, "registration/two_factor_setup.html", {
        "hide_nav": True,
        "form": form,
        "secret": device.secret if device else "",
        "otpauth_url": provisioning_uri(request.user, device.secret) if device else "",
        "recovery_codes": recovery_codes,
    })


@login_required
def two_factor_verify(request):
    """Ввод кода при входе сотрудника."""
    if not is_required_for(request.user) or session_passed(request):
        return redirect("dashboard")
    device = get_device(request.user)
    if device is None or not device.is_confirmed:
        return redirect("two_factor_setup")

    senders = [f"ip:{client_ip(request)}", f"user:{request.user.pk}"]
    form = TwoFactorCodeForm(request.POST or None)
    if request.method == "POST":
        if two_factor_guard.is_blocked(senders):
            # Код всего шесть цифр: без лимита он подбирается за вечер.
            logger.warning("two factor blocked: user=%s", request.user.pk)
            form.add_error(None, TWO_FACTOR_BLOCKED_MESSAGE)
        elif form.is_valid():
            if check_code(request.user, form.cleaned_data["code"]):
                two_factor_guard.reset(senders)
                mark_session_passed(request)
                return redirect(request.GET.get("next") or "dashboard")
            two_factor_guard.register_failure(senders)
            logger.warning("two factor failed: user=%s", request.user.pk)
            form.add_error("code", "Код не подошёл.")

    return render(request, "registration/two_factor_verify.html", {
        "hide_nav": True, "form": form, "recovery_left": device.recovery_left,
    })


def register_by_invite(request, code: str = ""):
    """Завести аккаунт по коду и сразу пустить человека в кабинет.

    Код приходит либо из ссылки методиста, либо руками в поле формы, поэтому
    вид один на оба входа.
    """
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        senders = [f"ip:{client_ip(request)}"]
        form = InviteRegistrationForm(request.POST)
        if invite_guard.is_blocked(senders):
            # Код одноразовый и достаточно длинный, но перебирать его всё равно
            # не должно быть дёшево.
            logger.warning("invite blocked: senders=%s", senders)
            form.add_error(None, INVITE_BLOCKED_MESSAGE)
        elif form.is_valid():
            try:
                user = accept_invite(
                    form.cleaned_data["code"],
                    username=form.cleaned_data["username"],
                    password=form.cleaned_data["password1"],
                )
            except ValidationError as error:
                invite_guard.register_failure(senders)
                form.add_error("code", error)
            else:
                invite_guard.reset(senders)
                login(request, user)
                return redirect("parent_dashboard" if hasattr(user, "parent_profile") else "dashboard")
    else:
        form = InviteRegistrationForm(initial={"code": code})

    return render(
        request,
        "registration/register.html",
        {"form": form, "login_url": reverse("login")},
    )
