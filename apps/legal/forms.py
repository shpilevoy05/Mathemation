from django import forms

from apps.accounts.models import User


class ConsentAcceptanceForm(forms.Form):
    accept_terms = forms.BooleanField(label="Я принимаю пользовательское соглашение")
    accept_privacy = forms.BooleanField(
        label="Даю согласие на обработку персональных данных"
    )
    age_declaration = forms.BooleanField(
        required=False,
        label=(
            "Мне есть 14 лет, а если мне меньше 18 — мой родитель "
            "(законный представитель) знает о регистрации"
        ),
    )
    parent_child_consent = forms.BooleanField(
        required=False,
        label=(
            "Как законный представитель даю согласие на обработку "
            "персональных данных ребёнка"
        ),
    )

    def __init__(self, *args, user: User, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(user, "student_profile"):
            self.fields["age_declaration"].required = True
        else:
            self.fields.pop("age_declaration")
        children = list(getattr(getattr(user, "parent_profile", None), "children", []).all()) \
            if hasattr(user, "parent_profile") else []
        self.children = children
        if children:
            self.fields["parent_child_consent"].required = True
        else:
            self.fields.pop("parent_child_consent")


class DataDeletionRequestForm(forms.Form):
    password = forms.CharField(label="Текущий пароль", widget=forms.PasswordInput)

    def __init__(self, *args, user: User, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise forms.ValidationError("Пароль не подошёл.")
        return password
