"""Формы саморегистрации по коду приглашения."""

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
    password1 = forms.CharField(label="Пароль", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(
        label="Пароль ещё раз", widget=forms.PasswordInput, strip=False
    )

    def clean_code(self):
        return self.cleaned_data["code"].strip()

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("Пользователь с таким логином уже существует.")
        return username

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
