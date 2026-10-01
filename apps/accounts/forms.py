"""Формы регистрации и настроек аккаунта."""

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import User


class TwoFactorCodeForm(forms.Form):
    """Код из приложения или резервный код.

    Одно поле на оба случая: человек, потерявший телефон, не должен искать,
    куда именно вводить запасной код.
    """

    code = forms.CharField(label="Код", max_length=32)

    def clean_code(self):
        return self.cleaned_data["code"].strip().replace(" ", "")


class InviteRegistrationForm(forms.Form):
    """Регистрация ученика или родителя по одноразовому коду.

    Форма проверяет только то, что можно проверить без записи: занятость
    логина и стойкость пароля. Валидность самого кода остаётся за
    `accept_invite`, чтобы гонка двух регистраций по одному коду решалась в
    одной транзакции с блокировкой.
    """

    code = forms.CharField(label="Код приглашения", max_length=64)
    username = forms.CharField(label="Логин", max_length=150)
    email = forms.EmailField(label="Электронная почта", max_length=254)
    password1 = forms.CharField(label="Пароль", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(
        label="Пароль ещё раз", widget=forms.PasswordInput, strip=False
    )
    accept_terms = forms.BooleanField(label="Я принимаю пользовательское соглашение")
    accept_privacy = forms.BooleanField(
        label="Даю согласие на обработку персональных данных"
    )

    def __init__(self, *args, invite=None, **kwargs):
        super().__init__(*args, **kwargs)
        role = getattr(invite, "role", User.Role.STUDENT)
        if role == User.Role.STUDENT:
            self.fields["age_declaration"] = forms.BooleanField(
                label=(
                    "Мне есть 14 лет, а если мне меньше 18 — мой родитель "
                    "(законный представитель) знает о регистрации"
                )
            )
        if role == User.Role.PARENT and getattr(invite, "for_student_id", None):
            self.fields["parent_child_consent"] = forms.BooleanField(
                label=(
                    "Как законный представитель даю согласие на обработку "
                    "персональных данных ребёнка"
                )
            )

    def clean_code(self):
        return self.cleaned_data["code"].strip()

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("Пользователь с таким логином уже существует.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email, is_active=True).exists():
            raise ValidationError(
                "Этот адрес электронной почты уже используется другим активным пользователем."
            )
        return email

    def clean(self):
        cleaned = super().clean()
        password1, password2 = cleaned.get("password1"), cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Пароли не совпадают.")
        elif password1:
            try:
                validate_password(password1)
            except ValidationError as error:
                self.add_error("password1", error)
        return cleaned


class ParentInviteAcceptanceForm(forms.Form):
    parent_child_consent = forms.BooleanField(
        label=(
            "Как законный представитель даю согласие на обработку "
            "персональных данных ребёнка"
        )
    )


class AccountSettingsForm(forms.Form):
    first_name = forms.CharField(label="Имя", max_length=150, required=False)
    last_name = forms.CharField(label="Фамилия", max_length=150, required=False)
    email = forms.EmailField(label="Электронная почта", max_length=254)
    exam_date = forms.DateField(
        label="Дата экзамена", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    weekly_hours = forms.IntegerField(
        label="Часов в неделю", required=True, min_value=1, max_value=40
    )

    def __init__(self, *args, user: User, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if not hasattr(user, "student_profile"):
            self.fields.pop("exam_date")
            self.fields.pop("weekly_hours")
        else:
            self.initial.setdefault("weekly_hours", user.student_profile.weekly_hours)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email, is_active=True).exclude(pk=self.user.pk).exists():
            raise ValidationError(
                "Этот адрес электронной почты уже используется другим активным пользователем."
            )
        return email
