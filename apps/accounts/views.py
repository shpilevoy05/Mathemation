"""Вход и саморегистрация по коду приглашения."""

import logging

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView, PasswordResetConfirmView, PasswordResetView
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy

from django.contrib.auth.decorators import login_required

from .forms import (
    AccountSettingsForm, InviteRegistrationForm, ParentInviteAcceptanceForm,
    TwoFactorCodeForm,
)
from .models import Invite
from .services import (
    accept_invite,
    accept_parent_invite,
    active_parent_invites,
    clear_password_change_requirement,
    create_parent_invite,
    revoke_parent_invite,
    update_account,
)
from .throttling import (
    client_ip,
    invite_guard,
    login_guard,
    password_reset_guard,
    two_factor_guard,
)
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


class ThrottledPasswordResetView(PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")

    def post(self, request, *args, **kwargs):
        email = (request.POST.get("email") or "").strip().lower()
        senders = [f"ip:{client_ip(request)}"]
        if email:
            senders.append(f"email:{email}")
        if password_reset_guard.is_blocked(senders):
            logger.warning("password reset blocked: ip=%s", client_ip(request))
            return redirect(self.success_url)
        password_reset_guard.register_failure(senders)
        return super().post(request, *args, **kwargs)


class ClearingPasswordResetConfirmView(PasswordResetConfirmView):
    """Сброс по почте тоже завершает режим временного пароля."""

    def form_valid(self, form):
        response = super().form_valid(form)
        clear_password_change_requirement(form.user)
        return response


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
        if code and hasattr(request.user, "parent_profile"):
            invite = Invite.objects.select_related("for_student__user").filter(code=code).first()
            error = ""
            parent_form = ParentInviteAcceptanceForm(request.POST or None)
            if request.method == "POST" and invite is not None and parent_form.is_valid():
                try:
                    accept_parent_invite(
                        invite,
                        request.user.parent_profile,
                        parent_child_consent=parent_form.cleaned_data["parent_child_consent"],
                        consent_ip=client_ip(request),
                        consent_user_agent=request.META.get("HTTP_USER_AGENT", ""),
                    )
                except ValidationError as exc:
                    error = " ".join(exc.messages)
                else:
                    messages.success(request, "Ребёнок добавлен в ваш аккаунт.")
                    return redirect("parent_dashboard")
            elif invite is None:
                error = "Код приглашения не найден."
            return render(request, "registration/register.html", {
                "parent_invite": invite,
                "parent_invite_error": error,
                "parent_form": parent_form,
                "hide_nav": True,
            })
        return redirect("dashboard")

    if request.method == "POST":
        senders = [f"ip:{client_ip(request)}"]
        invite = Invite.objects.filter(code=(request.POST.get("code") or "").strip()).first()
        form = InviteRegistrationForm(request.POST, invite=invite)
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
                    email=form.cleaned_data["email"],
                    password=form.cleaned_data["password1"],
                    consent_ip=client_ip(request),
                    consent_user_agent=request.META.get("HTTP_USER_AGENT", ""),
                    parent_child_consent=form.cleaned_data.get("parent_child_consent", False),
                )
            except ValidationError as error:
                invite_guard.register_failure(senders)
                form.add_error("code", error)
            else:
                invite_guard.reset(senders)
                login(request, user)
                return redirect("parent_dashboard" if hasattr(user, "parent_profile") else "dashboard")
    else:
        invite = Invite.objects.filter(code=code).first() if code else None
        form = InviteRegistrationForm(initial={"code": code}, invite=invite)

    return render(
        request,
        "registration/register.html",
        {"form": form, "login_url": reverse("login")},
    )


@login_required
def account_settings(request):
    from apps.legal.views import latest_deletion_request
    initial = {
        "first_name": request.user.first_name,
        "last_name": request.user.last_name,
        "email": request.user.email,
    }
    if hasattr(request.user, "student_profile"):
        initial.update({
            "exam_date": request.user.student_profile.exam_date,
            "weekly_hours": request.user.student_profile.weekly_hours,
        })
    form = AccountSettingsForm(request.POST or None, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        update_account(request.user, **form.cleaned_data)
        messages.success(request, "Настройки сохранены.")
        return redirect("account_settings")
    return render(request, "registration/account_settings.html", {
        "form": form,
        "parent_invites": (
            active_parent_invites(request.user.student_profile)
            if hasattr(request.user, "student_profile") else []
        ),
        "deletion_request": latest_deletion_request(request.user),
    })


@login_required
def account_password(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        clear_password_change_requirement(user)
        update_session_auth_hash(request, user)
        messages.success(request, "Пароль изменён.")
        return redirect("account_settings")
    return render(request, "registration/account_password.html", {
        "form": form,
        "hide_nav": request.user.must_change_password,
    })


@login_required
def parent_invite_create(request):
    if request.method != "POST" or not hasattr(request.user, "student_profile"):
        return redirect("account_settings")
    invite = create_parent_invite(request.user.student_profile)
    messages.success(
        request, f"Ссылка для родителя: {request.build_absolute_uri(reverse('register_by_invite', args=[invite.code]))}"
    )
    return redirect("account_settings")


@login_required
def parent_invite_revoke(request, invite_id: int):
    if request.method != "POST" or not hasattr(request.user, "student_profile"):
        return redirect("account_settings")
    try:
        revoke_parent_invite(request.user.student_profile, invite_id)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Приглашение отозвано.")
    return redirect("account_settings")
