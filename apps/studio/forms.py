from __future__ import annotations

from django import forms
from django.forms import BaseFormSet, BaseInlineFormSet, formset_factory, inlineformset_factory

from apps.billing.models import AddOn, Promotion, Tariff
from apps.content.models import Assignment, AssignmentSkillTag, DailyChallenge, Lesson, TheoryBlock
from apps.diagnostics.models import DiagnosticTest
from apps.knowledge.models import KnowledgeDependency, KnowledgeNode, TopicCluster
from apps.mocks.models import MockExam


class AccessibleFieldsMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field, GroupedNodeField):
                field.refresh_choices()
            field_id = f"id_{self.add_prefix(name)}"
            field.widget.attrs["aria-describedby"] = f"{field_id}-hint {field_id}-error"


def grouped_node_choices(*, include_groups: bool = False, exclude_id: int | None = None):
    nodes = KnowledgeNode.objects.select_related("cluster").order_by(
        "cluster__order", "cluster__title", "order", "title"
    )
    if not include_groups:
        nodes = nodes.exclude(node_type=KnowledgeNode.NodeType.GROUP)
    if exclude_id:
        nodes = nodes.exclude(pk=exclude_id)
    groups: dict[str, list[tuple[str, str]]] = {}
    for node in nodes:
        groups.setdefault(node.cluster.title, []).append((str(node.pk), node.title))
    return [(title, choices) for title, choices in groups.items()]


class GroupedNodeField(forms.ChoiceField):
    def __init__(self, *args, include_groups=False, exclude_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.include_groups = include_groups
        self.exclude_id = exclude_id

    def refresh_choices(self):
        self.choices = grouped_node_choices(
            include_groups=self.include_groups, exclude_id=self.exclude_id
        )
        # Пустой вариант нужен и обязательному полю: без него новая строка
        # формы показывала первую тему списка так, будто её уже выбрали.
        empty = ("", "Все темы") if not self.required else ("", "— выберите тему —")
        self.choices = [empty, *self.choices]

    def clean(self, value):
        value = super().clean(value)
        if value in self.empty_values and not self.required:
            return None
        try:
            return KnowledgeNode.objects.get(pk=value)
        except (KnowledgeNode.DoesNotExist, ValueError, TypeError) as error:
            raise forms.ValidationError("Выбранная тема не найдена.") from error


class LessonForm(AccessibleFieldsMixin, forms.ModelForm):
    node = GroupedNodeField(label="Тема")

    class Meta:
        model = Lesson
        fields = (
            "node", "title", "order", "video_provider", "video_url",
            "video_duration_minutes",
        )
        labels = {
            "title": "Название",
            "order": "Порядок",
            "video_provider": "Видеосервис",
            "video_url": "ID или ссылка на видео",
            "video_duration_minutes": "Длительность, минут",
        }
        help_texts = {
            "video_url": "Для Kinescope достаточно указать только ID видео.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["node"] = str(self.instance.node_id)


class TheoryBlockForm(AccessibleFieldsMixin, forms.ModelForm):
    class Meta:
        model = TheoryBlock
        fields = ("title", "body", "order")
        labels = {"title": "Заголовок", "body": "Текст", "order": "Порядок"}
        widgets = {"body": forms.Textarea(attrs={"rows": 8})}
        help_texts = {"body": "Можно использовать Markdown."}


TheoryBlockFormSet = inlineformset_factory(
    Lesson,
    TheoryBlock,
    form=TheoryBlockForm,
    extra=1,
    can_delete=True,
)


class AssignmentForm(AccessibleFieldsMixin, forms.ModelForm):
    change_note = forms.CharField(
        label="Комментарий к правке",
        max_length=300,
        required=False,
        help_text="Нужен, если условие или ответ уже решавшейся задачи изменились.",
    )

    class Meta:
        model = Assignment
        fields = (
            "title", "lesson", "statement", "exam_part", "difficulty", "max_score",
            "answer_type", "correct_answer", "answer_spec", "reference_solution",
            "arena_enabled",
        )
        labels = {
            "title": "Название",
            "lesson": "Урок",
            "statement": "Условие",
            "exam_part": "Часть экзамена",
            "difficulty": "Сложность",
            "max_score": "Максимальный балл",
            "answer_type": "Тип ответа",
            "correct_answer": "Правильный ответ",
            "answer_spec": "Структура ответа",
            "reference_solution": "Эталонный разбор",
            "arena_enabled": "Использовать в арене",
        }
        widgets = {
            "statement": forms.Textarea(attrs={"rows": 10}),
            "reference_solution": forms.Textarea(attrs={"rows": 10}),
            "answer_spec": forms.Textarea(attrs={"rows": 5, "data-answer-spec": ""}),
            "answer_type": forms.Select(attrs={"data-answer-type": ""}),
        }
        help_texts = {
            "answer_spec": (
                'Для множеств: {"roots": ["7*pi/6"]}; '
                'для семейств: {"families": ["pi/6 + 2*pi*k"]}.'
            ),
        }

    EXAM_PART_LABELS = [
        (Assignment.Part.PART1, "Часть 1 — краткий ответ"),
        (Assignment.Part.PART2, "Часть 2 — развёрнутое решение"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # В модели у частей экзамена нет русских подписей (Part1/Part2), а менять
        # choices ради подписи — лишняя миграция.
        self.fields["exam_part"].choices = self.EXAM_PART_LABELS
        self.fields["difficulty"].widget = forms.NumberInput(attrs={"min": 1, "max": 5})
        self.fields["difficulty"].help_text = "1 — базовая, 5 — сложнее экзаменационной."
        self.fields["max_score"].widget = forms.NumberInput(attrs={"min": 1, "max": 4})

    def clean_difficulty(self):
        value = self.cleaned_data["difficulty"]
        if not 1 <= value <= 5:
            raise forms.ValidationError("Укажите сложность от 1 до 5.")
        return value


class AssignmentSkillForm(AccessibleFieldsMixin, forms.ModelForm):
    node = GroupedNodeField(label="Тема")
    weight = forms.FloatField(label="Вес", min_value=0, max_value=1)

    class Meta:
        model = AssignmentSkillTag
        fields = ("node", "weight")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["node"] = str(self.instance.node_id)


class BaseAssignmentSkillFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        node_ids = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            node = form.cleaned_data.get("node")
            if node:
                node_ids.append(node.pk)
        if len(node_ids) != len(set(node_ids)):
            raise forms.ValidationError("Одна тема добавлена к задаче несколько раз.")


AssignmentSkillFormSet = inlineformset_factory(
    Assignment,
    AssignmentSkillTag,
    form=AssignmentSkillForm,
    formset=BaseAssignmentSkillFormSet,
    extra=1,
    can_delete=True,
)


class KnowledgeNodeForm(AccessibleFieldsMixin, forms.ModelForm):
    ege_numbers = forms.CharField(
        label="Номера ЕГЭ",
        required=False,
        help_text="Через запятую, например: 6, 12.",
    )

    class Meta:
        model = KnowledgeNode
        fields = ("code", "title", "cluster", "hours_estimate", "weight")
        labels = {
            "code": "Код",
            "title": "Название",
            "cluster": "Кластер",
            "hours_estimate": "Оценка часов",
            "weight": "Вес",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["ege_numbers"] = ", ".join(
                str(number) for number in self.instance.ege_task_numbers
            )
            self.fields["code"].disabled = True

    def clean_ege_numbers(self):
        raw = self.cleaned_data["ege_numbers"].strip()
        if not raw:
            return []
        try:
            numbers = [int(part.strip()) for part in raw.split(",") if part.strip()]
        except ValueError as error:
            raise forms.ValidationError("Укажите целые номера через запятую.") from error
        if any(number <= 0 for number in numbers):
            raise forms.ValidationError("Номер задания должен быть положительным.")
        return list(dict.fromkeys(numbers))

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.ege_task_numbers = self.cleaned_data["ege_numbers"]
        if commit:
            instance.save()
        return instance


class DependencyForm(AccessibleFieldsMixin, forms.Form):
    THIS_REQUIRES = "this_requires"
    OTHER_REQUIRES = "other_requires"
    direction = forms.ChoiceField(
        label="Направление",
        choices=(
            (THIS_REQUIRES, "Эта тема требует выбранную"),
            (OTHER_REQUIRES, "Выбранная тема требует эту"),
        ),
    )
    other_node = GroupedNodeField(label="Другая тема")
    kind = forms.ChoiceField(label="Вид связи", choices=KnowledgeDependency.Kind.choices)
    min_mastery = forms.IntegerField(
        label="Минимальное освоение, %", min_value=0, max_value=100, initial=70
    )

    def __init__(self, *args, current_node=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_node = current_node
        self.fields["other_node"] = GroupedNodeField(
            label="Другая тема", exclude_id=getattr(current_node, "pk", None)
        )
        self.fields["other_node"].refresh_choices()
        field_id = f"id_{self.add_prefix('other_node')}"
        self.fields["other_node"].widget.attrs["aria-describedby"] = (
            f"{field_id}-hint {field_id}-error"
        )


class TaskPickerFilterForm(AccessibleFieldsMixin, forms.Form):
    q = forms.CharField(label="Поиск", required=False)
    node = GroupedNodeField(label="Тема", required=False)
    ege = forms.IntegerField(label="Номер ЕГЭ", required=False, min_value=1)
    part = forms.ChoiceField(
        label="Часть", required=False,
        choices=(("", "Все части"), *Assignment.Part.choices),
    )


class AssignmentChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, assignment):
        return f"{assignment.title} · часть {assignment.exam_part} · сложность {assignment.difficulty}"


class DailyChallengeForm(AccessibleFieldsMixin, forms.Form):
    date = forms.DateField(label="Дата", disabled=True)
    assignment = AssignmentChoiceField(
        label="Задача", queryset=Assignment.objects.none(), widget=forms.RadioSelect
    )
    title = forms.CharField(label="Название", max_length=200, required=False)
    description = forms.CharField(
        label="Описание", required=False, widget=forms.Textarea(attrs={"rows": 5})
    )
    reward_xp = forms.IntegerField(label="Награда XP", min_value=0, initial=20)
    is_active = forms.BooleanField(label="Активно", required=False, initial=True)

    def __init__(self, *args, challenge=None, date=None, assignment_queryset=None, **kwargs):
        initial = kwargs.setdefault("initial", {})
        initial.setdefault("date", date)
        if challenge is not None:
            initial.update({
                "assignment": challenge.assignment_id,
                "title": challenge.title,
                "description": challenge.description,
                "reward_xp": challenge.reward_xp,
                "is_active": challenge.is_active,
            })
        super().__init__(*args, **kwargs)
        self.fields["assignment"].queryset = assignment_queryset or Assignment.objects.none()


class BaseFeatureFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        keys = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            key = form.cleaned_data.get("key", "").strip()
            value = form.cleaned_data.get("value", "").strip()
            if not key and not value:
                continue
            if not key or not value:
                raise forms.ValidationError("Для каждой особенности заполните подпись и значение.")
            keys.append(key)
        if len(keys) != len(set(keys)):
            raise forms.ValidationError("Подписи особенностей не должны повторяться.")

    def as_dict(self):
        return {
            form.cleaned_data["key"].strip(): form.cleaned_data["value"].strip()
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
            and form.cleaned_data.get("key", "").strip()
        }


class TariffFeatureForm(AccessibleFieldsMixin, forms.Form):
    key = forms.CharField(label="Подпись", required=False, max_length=200)
    value = forms.CharField(label="Значение", required=False, max_length=300)


TariffFeatureFormSet = formset_factory(
    TariffFeatureForm, formset=BaseFeatureFormSet, extra=1, can_delete=True
)


class TariffDetailsForm(AccessibleFieldsMixin, forms.ModelForm):
    class Meta:
        model = Tariff
        fields = ("title", "description", "is_active")
        labels = {
            "title": "Название", "description": "Описание",
            "is_active": "Активен",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}


class TariffPriceForm(AccessibleFieldsMixin, forms.Form):
    price_rub = forms.DecimalField(
        label="Новая цена, ₽", min_value=0, max_digits=10, decimal_places=2
    )


class AddOnForm(AccessibleFieldsMixin, forms.ModelForm):
    class Meta:
        model = AddOn
        fields = ("title", "description", "price_rub", "quantity", "unit_label", "is_active")
        labels = {
            "title": "Название", "description": "Описание", "price_rub": "Цена, ₽",
            "quantity": "Количество", "unit_label": "Единица", "is_active": "Активна",
        }

    def clean_price_rub(self):
        price = self.cleaned_data["price_rub"]
        if price < 0:
            raise forms.ValidationError("Цена не может быть отрицательной.")
        return price


class PromotionForm(AccessibleFieldsMixin, forms.ModelForm):
    tariff_codes = forms.MultipleChoiceField(
        label="Тарифы", required=False, widget=forms.CheckboxSelectMultiple,
        help_text="Не выбирайте ничего, чтобы акция действовала на все тарифы.",
    )

    class Meta:
        model = Promotion
        fields = (
            "title", "description", "code", "kind", "value", "tariff_codes",
            "starts_at", "ends_at", "max_uses", "is_active",
        )
        labels = {
            "title": "Название", "description": "Описание", "code": "Промокод",
            "kind": "Вид скидки", "value": "Размер скидки",
            "starts_at": "Начало", "ends_at": "Окончание",
            "max_uses": "Максимум применений", "is_active": "Активна",
        }
        help_texts = {
            "code": "Необязательно. Код будет сохранён заглавными буквами.",
            "max_uses": "0 — без ограничения.",
        }
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        codes = []
        seen = set()
        for tariff in Tariff.objects.filter(is_active=True).order_by("code", "-version"):
            if tariff.code not in seen:
                codes.append((tariff.code, tariff.title))
                seen.add(tariff.code)
        self.fields["tariff_codes"].choices = codes
        self.fields["starts_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["ends_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        if self.instance.pk:
            self.initial["tariff_codes"] = self.instance.tariff_codes


class DiagnosticBuilderForm(AccessibleFieldsMixin, forms.ModelForm):
    add_tasks = forms.ModelMultipleChoiceField(
        label="Добавить задачи", required=False, queryset=Assignment.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = DiagnosticTest
        fields = ("title", "is_active")
        labels = {"title": "Название", "is_active": "Активна"}

    def __init__(self, *args, assignment_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["add_tasks"].queryset = assignment_queryset or Assignment.objects.none()


class MockBuilderForm(AccessibleFieldsMixin, forms.ModelForm):
    add_tasks = forms.ModelMultipleChoiceField(
        label="Добавить задачи", required=False, queryset=Assignment.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = MockExam
        fields = ("title", "duration_minutes", "is_active")
        labels = {
            "title": "Название", "duration_minutes": "Длительность, минут",
            "is_active": "Активен",
        }

    def __init__(self, *args, assignment_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["add_tasks"].queryset = assignment_queryset or Assignment.objects.none()
