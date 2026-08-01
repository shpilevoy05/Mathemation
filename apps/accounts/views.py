"""Страница саморегистрации по коду приглашения."""

from django.contrib.auth import login
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import InviteRegistrationForm
from .services import accept_invite


def register_by_invite(request, code: str = ""):
    """Завести аккаунт по коду и сразу пустить человека в кабинет.

    Код приходит либо из ссылки методиста, либо руками в поле формы, поэтому
    вид один на оба входа.
    """
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = InviteRegistrationForm(request.POST)
        if form.is_valid():
            try:
                user = accept_invite(
                    form.cleaned_data["code"],
                    username=form.cleaned_data["username"],
                    password=form.cleaned_data["password1"],
                )
            except ValidationError as error:
                form.add_error("code", error)
            else:
                login(request, user)
                return redirect("parent_dashboard" if hasattr(user, "parent_profile") else "dashboard")
    else:
        form = InviteRegistrationForm(initial={"code": code})

    return render(
        request,
        "registration/register.html",
        {"form": form, "login_url": reverse("login")},
    )
