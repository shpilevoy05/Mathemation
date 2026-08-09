"""Вход и саморегистрация по коду приглашения."""

import logging

from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import InviteRegistrationForm
from .services import accept_invite
from .throttling import client_ip, invite_guard, login_guard

logger = logging.getLogger("matemacia.security")

BLOCKED_MESSAGE = (
    "Слишком много неудачных попыток. Подождите 15 минут или напишите куратору."
)
INVITE_BLOCKED_MESSAGE = (
    "Слишком много попыток ввести код. Попробуйте через час или попросите "
    "куратора выдать новый код."
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
