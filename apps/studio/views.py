from __future__ import annotations

import calendar as month_calendar
from datetime import date, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.forms.utils import ErrorDict
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.adminpanel.audit import log_admin_action
from apps.billing.models import AddOn, Promotion, Tariff
from apps.billing.services import (
    active_tariffs,
    promotion_preview,
    promotion_status,
    save_promotion,
    update_addon,
    update_tariff_details,
)
from apps.content.models import Assignment, DailyChallenge, Lesson
from apps.content.services import publish_lesson, unpublish_lesson
from apps.diagnostics.models import DiagnosticTest
from apps.diagnostics.services import remove_diagnostic_assignment, save_diagnostic_test
from apps.knowledge.models import KnowledgeDependency, KnowledgeNode, TopicCluster
from apps.mocks.models import MockExam
from apps.mocks.services import remove_mock_assignment, save_mock_exam
from apps.web.permissions import is_methodist

from .forms import (
    AssignmentForm,
    AssignmentSkillFormSet,
    AddOnForm,
    DailyChallengeForm,
    DependencyForm,
    DiagnosticBuilderForm,
    KnowledgeNodeForm,
    LessonForm,
    MockBuilderForm,
    PromotionForm,
    TariffDetailsForm,
    TariffFeatureFormSet,
    TariffPriceForm,
    TaskPickerFilterForm,
    TheoryBlockFormSet,
)
from .services import (
    ASSIGNMENT_VERSION_FIELDS,
    add_dependency,
    assignment_order_key,
    audit_saved,
    change_tariff_price,
    delete_dependency,
    delete_daily,
    filter_assignments,
    markup_membership,
    save_assignment,
    save_daily,
    save_lesson,
    save_node,
)


def methodist_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not is_methodist(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def _add_validation_error(form, error: ValidationError):
    if not hasattr(form, "cleaned_data"):
        form.cleaned_data = {}
        form._errors = ErrorDict()
    if hasattr(error, "message_dict"):
        for field, field_messages in error.message_dict.items():
            target = field if field in form.fields else None
            for message in field_messages:
                form.add_error(target, message)
    else:
        for message in error.messages:
            form.add_error(None, message)


def _integer_filter(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@methodist_required
def lesson_list(request):
    lessons = (
        Lesson.objects.select_related("node__cluster")
        .annotate(
            theory_count=Count("theory_blocks", distinct=True),
            task_count=Count("assignments", distinct=True),
        )
        .order_by("node__cluster__order", "node__order", "order", "title")
    )
    cluster = request.GET.get("cluster", "")
    status = request.GET.get("status", "")
    search = request.GET.get("q", "").strip()
    cluster_id = _integer_filter(cluster)
    if cluster_id is not None:
        lessons = lessons.filter(node__cluster_id=cluster_id)
    if status:
        lessons = lessons.filter(status=status)
    if search:
        lessons = lessons.filter(title__icontains=search)
    return render(
        request,
        "studio/lesson_list.html",
        {
            "lessons": lessons,
            "clusters": TopicCluster.objects.all(),
            "statuses": Lesson.Status.choices,
            "filters": {"cluster": cluster, "status": status, "q": search},
        },
    )


@methodist_required
def lesson_edit(request, lesson_id=None):
    lesson = get_object_or_404(Lesson, pk=lesson_id) if lesson_id else Lesson()
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action in ("publish", "unpublish") and lesson.pk:
            form = LessonForm(instance=lesson)
            theory_formset = TheoryBlockFormSet(instance=lesson, prefix="theory")
            try:
                if action == "publish":
                    publish_lesson(lesson)
                    audit_action = "lesson.publish"
                    success = "Урок опубликован."
                else:
                    unpublish_lesson(lesson)
                    audit_action = "lesson.unpublish"
                    success = "Урок снят с публикации."
                log_admin_action(
                    request.user, audit_action, target=f"lesson:{lesson.pk}", title=lesson.title
                )
                messages.success(request, success)
                return redirect("studio_lesson_edit", lesson_id=lesson.pk)
            except ValidationError as error:
                _add_validation_error(form, error)
        else:
            form = LessonForm(request.POST, instance=lesson)
            theory_formset = TheoryBlockFormSet(
                request.POST, instance=lesson, prefix="theory"
            )
            if form.is_valid() and theory_formset.is_valid():
                lesson = save_lesson(
                    actor=request.user, form=form, theory_formset=theory_formset
                )
                messages.success(request, "Урок сохранён.")
                return redirect("studio_lesson_edit", lesson_id=lesson.pk)
    else:
        form = LessonForm(instance=lesson)
        theory_formset = TheoryBlockFormSet(instance=lesson, prefix="theory")
    assignments = lesson.assignments.order_by("title") if lesson.pk else []
    return render(
        request,
        "studio/lesson_form.html",
        {
            "lesson": lesson,
            "form": form,
            "theory_formset": theory_formset,
            "assignments": assignments,
        },
    )


@methodist_required
def task_list(request):
    assignments = (
        Assignment.objects.select_related("lesson")
        .prefetch_related("skills")
        .annotate(version_count=Count("versions", distinct=True))
        .order_by("title", "pk")
    )
    filters = {
        key: request.GET.get(key, "").strip()
        for key in (
            "q", "cluster", "node", "ege", "part", "difficulty", "arena",
            "missing_answer", "missing_solution",
        )
    }
    if filters["q"]:
        assignments = assignments.filter(
            Q(title__icontains=filters["q"]) | Q(statement__icontains=filters["q"])
        )
    cluster_id = _integer_filter(filters["cluster"])
    node_id = _integer_filter(filters["node"])
    if cluster_id is not None:
        assignments = assignments.filter(skill_tags__node__cluster_id=cluster_id)
    if node_id is not None:
        assignments = assignments.filter(skill_tags__node_id=node_id)
    if filters["ege"]:
        ege_number = _integer_filter(filters["ege"])
        if ege_number is not None:
            node_ids = [
                node.pk
                for node in KnowledgeNode.objects.only("pk", "ege_task_numbers")
                if ege_number in (node.ege_task_numbers or [])
            ]
            assignments = assignments.filter(skill_tags__node_id__in=node_ids)
    part = _integer_filter(filters["part"])
    difficulty = _integer_filter(filters["difficulty"])
    if part is not None:
        assignments = assignments.filter(exam_part=part)
    if difficulty is not None:
        assignments = assignments.filter(difficulty=difficulty)
    if filters["arena"] in ("yes", "no"):
        assignments = assignments.filter(arena_enabled=filters["arena"] == "yes")
    if filters["missing_answer"] == "yes":
        assignments = assignments.filter(correct_answer="")
    if filters["missing_solution"] == "yes":
        assignments = assignments.filter(reference_solution="")
    assignments = assignments.distinct()
    page = Paginator(assignments, 30).get_page(request.GET.get("page"))
    page_query = request.GET.copy()
    page_query.pop("page", None)
    return render(
        request,
        "studio/task_list.html",
        {
            "page": page,
            "clusters": TopicCluster.objects.all(),
            "nodes": KnowledgeNode.objects.select_related("cluster"),
            "parts": Assignment.Part.choices,
            "filters": filters,
            "page_query": page_query.urlencode(),
        },
    )


@methodist_required
def task_edit(request, assignment_id=None):
    assignment = (
        get_object_or_404(Assignment, pk=assignment_id)
        if assignment_id else Assignment()
    )
    old_values = (
        {name: getattr(assignment, name) for name in ASSIGNMENT_VERSION_FIELDS}
        if assignment.pk else None
    )
    has_attempts = assignment.pk and assignment.attempts.exists()
    if request.method == "POST":
        form = AssignmentForm(request.POST, instance=assignment)
        skill_formset = AssignmentSkillFormSet(
            request.POST, instance=assignment, prefix="skills"
        )
        forms_valid = form.is_valid() and skill_formset.is_valid()
        version_changed = forms_valid and has_attempts and any(
            form.cleaned_data[name] != old_values[name]
            for name in ASSIGNMENT_VERSION_FIELDS
        )
        if version_changed and not form.cleaned_data["change_note"].strip():
            form.add_error("change_note", "Добавьте комментарий к новой версии.")
            forms_valid = False
        if forms_valid:
            assignment, version = save_assignment(
                actor=request.user,
                form=form,
                skill_formset=skill_formset,
                old_version_values=old_values,
                has_attempts=bool(has_attempts),
            )
            messages.success(
                request,
                "Новая версия задачи сохранена." if version else "Задача сохранена.",
            )
            return redirect("studio_task_edit", assignment_id=assignment.pk)
    else:
        initial = {}
        lesson_id = request.GET.get("lesson")
        if not assignment.pk and lesson_id:
            initial["lesson"] = lesson_id
        form = AssignmentForm(instance=assignment, initial=initial)
        skill_formset = AssignmentSkillFormSet(instance=assignment, prefix="skills")
    versions = assignment.versions.select_related("created_by") if assignment.pk else []
    return render(
        request,
        "studio/task_form.html",
        {
            "assignment": assignment,
            "form": form,
            "skill_formset": skill_formset,
            "versions": versions,
            "has_attempts": has_attempts,
        },
    )


@methodist_required
def graph_overview(request):
    search = request.GET.get("q", "").strip()
    nodes = (
        KnowledgeNode.objects.select_related("cluster")
        .annotate(
            prerequisite_count=Count("dependencies", distinct=True),
            dependent_count=Count("dependents", distinct=True),
            lesson_count=Count("lessons", distinct=True),
            task_count=Count("assignments", distinct=True),
        )
        .order_by("cluster__order", "cluster__title", "order", "title")
    )
    if search:
        nodes = nodes.filter(Q(title__icontains=search) | Q(code__icontains=search))
    managed_nodes, _ = markup_membership()
    for node in nodes:
        node.is_markup_managed = node.code in managed_nodes
    return render(
        request,
        "studio/graph_overview.html",
        {"nodes": nodes, "search": search},
    )


@methodist_required
def node_edit(request, node_id=None):
    node = get_object_or_404(KnowledgeNode, pk=node_id) if node_id else KnowledgeNode()
    dependency_form = DependencyForm(current_node=node if node.pk else None)
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "add_dependency" and node.pk:
            form = KnowledgeNodeForm(instance=node)
            dependency_form = DependencyForm(request.POST, current_node=node)
            if dependency_form.is_valid():
                try:
                    add_dependency(
                        actor=request.user,
                        current_node=node,
                        cleaned_data=dependency_form.cleaned_data,
                    )
                    messages.success(request, "Связь добавлена.")
                    return redirect("studio_node_edit", node_id=node.pk)
                except ValidationError as error:
                    _add_validation_error(dependency_form, error)
        else:
            form = KnowledgeNodeForm(request.POST, instance=node)
            if form.is_valid():
                node = save_node(actor=request.user, form=form)
                messages.success(request, "Тема сохранена.")
                return redirect("studio_node_edit", node_id=node.pk)
    else:
        form = KnowledgeNodeForm(instance=node)

    prerequisites = (
        node.dependencies.select_related("prerequisite") if node.pk else []
    )
    dependents = node.dependents.select_related("node") if node.pk else []
    managed_nodes, managed_edges = markup_membership()
    if node.pk:
        for dependency in list(prerequisites) + list(dependents):
            dependency.is_markup_managed = (
                dependency.node.code, dependency.prerequisite.code
            ) in managed_edges
    return render(
        request,
        "studio/node_form.html",
        {
            "node": node,
            "form": form,
            "dependency_form": dependency_form,
            "prerequisites": prerequisites,
            "dependents": dependents,
            "is_markup_managed": node.pk and node.code in managed_nodes,
        },
    )


@methodist_required
def dependency_delete(request, node_id, dependency_id):
    if request.method != "POST":
        raise Http404
    node = get_object_or_404(KnowledgeNode, pk=node_id)
    dependency = get_object_or_404(KnowledgeDependency, pk=dependency_id)
    if node.pk not in (dependency.node_id, dependency.prerequisite_id):
        raise Http404
    delete_dependency(actor=request.user, dependency=dependency)
    messages.success(request, "Связь удалена.")
    return redirect("studio_node_edit", node_id=node.pk)


def _picker_filters(request):
    return {key: request.GET.get(key, "").strip() for key in ("q", "node", "ege", "part")}


@methodist_required
def task_picker(request):
    filters = _picker_filters(request)
    return render(
        request,
        "studio/_task_picker.html",
        {
            "picker_filter_form": TaskPickerFilterForm(request.GET or None),
            "picker_assignments": filter_assignments(filters),
            "picker_mode": "single" if request.GET.get("mode") == "single" else "multi",
            "picker_standalone": True,
            "picker_filters": filters,
        },
    )


def _calendar_month(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        first = date(year, month, 1)
    except (TypeError, ValueError):
        first = today.replace(day=1)
    previous = (first.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first, previous, next_month


@methodist_required
def daily_calendar(request):
    first, previous, next_month = _calendar_month(request)
    today = timezone.localdate()
    challenges = {
        challenge.date: challenge
        for challenge in DailyChallenge.objects.filter(
            date__year=first.year, date__month=first.month
        ).select_related("assignment")
    }
    weeks = []
    for week in month_calendar.Calendar(firstweekday=0).monthdatescalendar(first.year, first.month):
        rows = []
        for day in week:
            in_month = day.month == first.month
            rows.append({
                "date": day,
                "in_month": in_month,
                "is_past": day < today,
                "challenge": challenges.get(day) if in_month else None,
            })
        weeks.append(rows)
    return render(
        request,
        "studio/daily_calendar.html",
        {
            "first": first,
            "previous": previous,
            "next_month": next_month,
            "month_label": month_calendar.month_name[first.month],
            "weekday_labels": ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"),
            "weeks": weeks,
        },
    )


@methodist_required
def daily_edit(request, day):
    try:
        challenge_date = date.fromisoformat(day)
    except ValueError as error:
        raise Http404 from error
    challenge = DailyChallenge.objects.filter(date=challenge_date).select_related("assignment").first()
    is_past = challenge_date < timezone.localdate()
    filters = _picker_filters(request)
    include_ids = [challenge.assignment_id] if challenge else []
    picker_assignments = filter_assignments(filters, include_ids=include_ids)
    if request.method == "POST":
        if is_past:
            raise PermissionDenied
        action = request.POST.get("action", "save")
        if action == "delete" and challenge is not None:
            try:
                delete_daily(actor=request.user, challenge=challenge)
                messages.success(request, "Задание дня удалено.")
                return redirect("studio_daily")
            except ValidationError as error:
                form = DailyChallengeForm(
                    challenge=challenge, date=challenge_date,
                    assignment_queryset=filter_assignments({}, include_ids=include_ids),
                )
                _add_validation_error(form, error)
        else:
            form = DailyChallengeForm(
                request.POST,
                challenge=challenge,
                date=challenge_date,
                assignment_queryset=filter_assignments({}),
            )
            if form.is_valid():
                try:
                    challenge = save_daily(
                        actor=request.user,
                        instance=challenge,
                        date=challenge_date,
                        assignment=form.cleaned_data["assignment"],
                        title=form.cleaned_data["title"],
                        description=form.cleaned_data["description"],
                        reward_xp=form.cleaned_data["reward_xp"],
                        is_active=form.cleaned_data["is_active"],
                    )
                    messages.success(request, "Задание дня сохранено.")
                    return redirect("studio_daily_edit", day=challenge_date.isoformat())
                except ValidationError as error:
                    _add_validation_error(form, error)
    else:
        form = DailyChallengeForm(
            challenge=challenge, date=challenge_date, assignment_queryset=picker_assignments
        )
    return render(
        request,
        "studio/daily_form.html",
        {
            "challenge": challenge, "challenge_date": challenge_date,
            "is_past": is_past, "can_delete": bool(challenge and challenge_date > timezone.localdate()),
            "form": form,
            "picker_filter_form": TaskPickerFilterForm(request.GET or None),
            "picker_assignments": picker_assignments,
            "picker_field": form["assignment"], "picker_mode": "single",
            "picker_filters": filters,
        },
    )


PROMOTION_LABELS = {
    "live": ("действует", "chip-live"),
    "scheduled": ("запланирована", "chip-draft"),
    "ended": ("закончилась", "chip-mute"),
    "exhausted": ("исчерпана", "chip-warn"),
    "disabled": ("выключена", "chip-mute"),
}


@methodist_required
def pricing_overview(request):
    promotions = list(Promotion.objects.all())
    for promotion in promotions:
        promotion.status_code = promotion_status(promotion)
        promotion.status_label, promotion.status_chip = PROMOTION_LABELS[promotion.status_code]
    return render(
        request,
        "studio/pricing.html",
        {
            "tariffs": active_tariffs(),
            "archived_tariffs": Tariff.objects.filter(is_active=False),
            "addons": AddOn.objects.all(),
            "promotions": promotions,
        },
    )


@methodist_required
def tariff_edit(request, tariff_id):
    tariff = get_object_or_404(Tariff, pk=tariff_id, is_active=True)
    feature_initial = [{"key": key, "value": value} for key, value in tariff.features.items()]
    if request.method == "POST":
        form = TariffDetailsForm(request.POST, instance=tariff)
        feature_formset = TariffFeatureFormSet(request.POST, prefix="features")
        if form.is_valid() and feature_formset.is_valid():
            tariff = update_tariff_details(
                tariff,
                title=form.cleaned_data["title"],
                description=form.cleaned_data["description"],
                features=feature_formset.as_dict(),
                is_active=form.cleaned_data["is_active"],
            )
            audit_saved(request.user, "tariff.details", tariff, code=tariff.code)
            messages.success(request, "Описание тарифа сохранено.")
            if tariff.is_active:
                return redirect("studio_tariff_edit", tariff_id=tariff.pk)
            return redirect("studio_pricing")
    else:
        form = TariffDetailsForm(instance=tariff)
        feature_formset = TariffFeatureFormSet(initial=feature_initial, prefix="features")
    return render(request, "studio/tariff_form.html", {
        "tariff": tariff, "form": form, "feature_formset": feature_formset,
    })


@methodist_required
def tariff_price(request, tariff_id):
    tariff = get_object_or_404(Tariff, pk=tariff_id, is_active=True)
    if request.method == "POST":
        form = TariffPriceForm(request.POST)
        if form.is_valid():
            updated = change_tariff_price(
                actor=request.user, tariff=tariff, price_rub=form.cleaned_data["price_rub"]
            )
            messages.success(request, "Создана новая версия тарифа с новой ценой.")
            return redirect("studio_tariff_edit", tariff_id=updated.pk)
    else:
        form = TariffPriceForm(initial={"price_rub": tariff.price_rub})
    return render(request, "studio/tariff_price_form.html", {"tariff": tariff, "form": form})


@methodist_required
def addon_edit(request, addon_id):
    addon = get_object_or_404(AddOn, pk=addon_id)
    if request.method == "POST":
        form = AddOnForm(request.POST, instance=addon)
        if form.is_valid():
            addon = update_addon(addon, **form.cleaned_data)
            audit_saved(request.user, "addon.save", addon, code=addon.code)
            messages.success(request, "Докупка сохранена.")
            return redirect("studio_addon_edit", addon_id=addon.pk)
    else:
        form = AddOnForm(instance=addon)
    return render(request, "studio/addon_form.html", {"addon": addon, "form": form})


@methodist_required
def promotion_edit(request, promotion_id=None):
    promotion = get_object_or_404(Promotion, pk=promotion_id) if promotion_id else Promotion()
    if request.method == "POST":
        form = PromotionForm(request.POST, instance=promotion)
        if form.is_valid():
            try:
                promotion = save_promotion(promotion, **{
                    name: form.cleaned_data[name] for name in form._meta.fields
                })
                audit_saved(request.user, "promotion.save", promotion, code=promotion.code)
                messages.success(request, "Акция сохранена.")
                return redirect("studio_promotion_edit", promotion_id=promotion.pk)
            except ValidationError as error:
                _add_validation_error(form, error)
    else:
        form = PromotionForm(instance=promotion)
    previews = []
    if promotion.pk:
        previews = [promotion_preview(promotion, tariff) for tariff in active_tariffs()]
    return render(request, "studio/promotion_form.html", {
        "promotion": promotion, "form": form, "previews": previews,
    })


@methodist_required
def test_list(request):
    diagnostics = DiagnosticTest.objects.annotate(task_count=Count("assignments"))
    mocks = MockExam.objects.annotate(task_count=Count("assignments"))
    return render(request, "studio/test_list.html", {
        "diagnostics": diagnostics, "mocks": mocks,
    })


def _builder_context(request, current_ids=()):
    filters = _picker_filters(request)
    return filters, filter_assignments(filters, include_ids=current_ids)


@methodist_required
def diagnostic_edit(request, test_id=None):
    diagnostic = get_object_or_404(DiagnosticTest, pk=test_id) if test_id else DiagnosticTest()
    current_ids = list(diagnostic.assignments.values_list("pk", flat=True)) if diagnostic.pk else []
    filters, picker_assignments = _builder_context(request, current_ids)
    if request.method == "POST":
        remove_id = request.POST.get("remove_task")
        if remove_id and diagnostic.pk:
            assignment = get_object_or_404(Assignment, pk=remove_id)
            remove_diagnostic_assignment(diagnostic, assignment)
            audit_saved(request.user, "diagnostic.save", diagnostic, removed_assignment=assignment.pk)
            return redirect("studio_diagnostic_edit", test_id=diagnostic.pk)
        form = DiagnosticBuilderForm(
            request.POST, instance=diagnostic, assignment_queryset=filter_assignments({})
        )
        if form.is_valid():
            diagnostic = save_diagnostic_test(
                diagnostic, title=form.cleaned_data["title"],
                is_active=form.cleaned_data["is_active"],
                add_assignments=form.cleaned_data["add_tasks"],
            )
            audit_saved(request.user, "diagnostic.save", diagnostic, title=diagnostic.title)
            messages.success(request, "Диагностика сохранена.")
            return redirect("studio_diagnostic_edit", test_id=diagnostic.pk)
    else:
        form = DiagnosticBuilderForm(instance=diagnostic, assignment_queryset=picker_assignments)
    tasks = sorted(
        diagnostic.assignments.prefetch_related("skills") if diagnostic.pk else [],
        key=assignment_order_key,
    )
    return render(request, "studio/test_form.html", {
        "kind": "diagnostic", "object": diagnostic, "form": form, "tasks": tasks,
        "picker_filter_form": TaskPickerFilterForm(request.GET or None),
        "picker_assignments": picker_assignments, "picker_field": form["add_tasks"],
        "picker_mode": "multi", "picker_filters": filters,
        "warning": any(not task.correct_answer for task in tasks),
        "warning_text": "В диагностике есть задачи без ответа.",
    })


@methodist_required
def mock_edit(request, exam_id=None):
    exam = get_object_or_404(MockExam, pk=exam_id) if exam_id else MockExam()
    current_ids = list(exam.assignments.values_list("pk", flat=True)) if exam.pk else []
    filters, picker_assignments = _builder_context(request, current_ids)
    if request.method == "POST":
        remove_id = request.POST.get("remove_task")
        if remove_id and exam.pk:
            assignment = get_object_or_404(Assignment, pk=remove_id)
            remove_mock_assignment(exam, assignment)
            audit_saved(request.user, "mock.save", exam, removed_assignment=assignment.pk)
            return redirect("studio_mock_edit", exam_id=exam.pk)
        form = MockBuilderForm(
            request.POST, instance=exam, assignment_queryset=filter_assignments({})
        )
        if form.is_valid():
            exam = save_mock_exam(
                exam, title=form.cleaned_data["title"],
                duration_minutes=form.cleaned_data["duration_minutes"],
                is_active=form.cleaned_data["is_active"],
                add_assignments=form.cleaned_data["add_tasks"],
            )
            audit_saved(request.user, "mock.save", exam, title=exam.title)
            messages.success(request, "Пробник сохранён.")
            return redirect("studio_mock_edit", exam_id=exam.pk)
    else:
        form = MockBuilderForm(instance=exam, assignment_queryset=picker_assignments)
    tasks = sorted(
        exam.assignments.prefetch_related("skills") if exam.pk else [],
        key=assignment_order_key,
    )
    has_part2 = any(task.exam_part == Assignment.Part.PART2 for task in tasks)
    return render(request, "studio/test_form.html", {
        "kind": "mock", "object": exam, "form": form, "tasks": tasks,
        "picker_filter_form": TaskPickerFilterForm(request.GET or None),
        "picker_assignments": picker_assignments, "picker_field": form["add_tasks"],
        "picker_mode": "multi", "picker_filters": filters,
        "warning": len(tasks) < 19 or not has_part2,
        "warning_text": "В пробнике меньше 19 задач или нет задач второй части.",
    })
