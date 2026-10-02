"""Транзакционная оркестрация форм рабочего места методиста."""

from __future__ import annotations

from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.adminpanel.audit import log_admin_action
from apps.content.services import publish_assignment_version
from apps.knowledge.models import KnowledgeDependency


ASSIGNMENT_VERSION_FIELDS = (
    "statement", "correct_answer", "reference_solution", "max_score", "difficulty"
)


@transaction.atomic
def save_lesson(*, actor, form, theory_formset):
    lesson = form.save()
    theory_formset.instance = lesson
    theory_formset.save()
    log_admin_action(
        actor,
        "lesson.save",
        target=f"lesson:{lesson.pk}",
        title=lesson.title,
    )
    return lesson


@transaction.atomic
def save_assignment(
    *, actor, form, skill_formset, old_version_values=None, has_attempts=False
):
    assignment = form.save(commit=False)
    is_new = assignment.pk is None
    version_changes = {}
    if not is_new and old_version_values:
        version_changes = {
            name: form.cleaned_data[name]
            for name in ASSIGNMENT_VERSION_FIELDS
            if form.cleaned_data[name] != old_version_values[name]
        }

    version = None
    if has_attempts and version_changes:
        for name in ASSIGNMENT_VERSION_FIELDS:
            setattr(assignment, name, old_version_values[name])
        direct_fields = [
            name for name in form._meta.fields if name not in ASSIGNMENT_VERSION_FIELDS
        ]
        assignment.save(update_fields=direct_fields)
        version = publish_assignment_version(
            assignment,
            change_note=form.cleaned_data["change_note"],
            created_by=actor,
            **version_changes,
        )
        log_admin_action(
            actor,
            "assignment.new_version",
            target=f"assignment:{assignment.pk}",
            title=assignment.title,
            version=version.number,
        )
    else:
        assignment.save()
        log_admin_action(
            actor,
            "assignment.save",
            target=f"assignment:{assignment.pk}",
            title=assignment.title,
        )

    skill_formset.instance = assignment
    skill_formset.save()
    return assignment, version


@transaction.atomic
def save_node(*, actor, form):
    node = form.save()
    log_admin_action(
        actor,
        "knowledge_node.save",
        target=f"knowledge_node:{node.pk}",
        title=node.title,
    )
    return node


@transaction.atomic
def add_dependency(*, actor, current_node, cleaned_data):
    other = cleaned_data["other_node"]
    if cleaned_data["direction"] == "this_requires":
        node, prerequisite = current_node, other
    else:
        node, prerequisite = other, current_node
    if KnowledgeDependency.objects.filter(
        node=node, prerequisite=prerequisite
    ).exists():
        raise ValidationError("Такая связь уже существует.")
    dependency = KnowledgeDependency(
        node=node,
        prerequisite=prerequisite,
        kind=cleaned_data["kind"],
        min_mastery=cleaned_data["min_mastery"],
    )
    dependency.save()
    log_admin_action(
        actor,
        "knowledge_dependency.add",
        target=f"knowledge_dependency:{dependency.pk}",
        node_id=node.pk,
        prerequisite_id=prerequisite.pk,
    )
    return dependency


@transaction.atomic
def delete_dependency(*, actor, dependency):
    target = f"knowledge_dependency:{dependency.pk}"
    payload = {
        "node_id": dependency.node_id,
        "prerequisite_id": dependency.prerequisite_id,
    }
    dependency.delete()
    log_admin_action(actor, "knowledge_dependency.delete", target=target, **payload)


def markup_membership():
    """Коды и рёбра, которые следующая загрузка методической книги обновит."""
    from apps.knowledge.markup import MARKUP_SETS

    node_codes = set()
    edge_codes = set()
    for markup in MARKUP_SETS.values():
        node_codes.update(skill["code"] for skill in markup.SKILLS)
        edge_codes.update(
            (edge["node"], edge["prerequisite"]) for edge in markup.EDGES
        )
    return node_codes, edge_codes


def filter_assignments(filters, *, include_ids=()):
    """Общий read-side фильтр банка для списков и picker."""
    from apps.content.models import Assignment
    from apps.knowledge.models import KnowledgeNode

    queryset = Assignment.objects.prefetch_related("skills").order_by("title", "pk")
    filtered = queryset
    search = (filters.get("q") or "").strip()
    if search:
        filtered = filtered.filter(Q(title__icontains=search) | Q(statement__icontains=search))
    for key, lookup in (("node", "skill_tags__node_id"), ("part", "exam_part")):
        try:
            value = int(filters.get(key) or "")
        except (TypeError, ValueError):
            value = None
        if value is not None:
            filtered = filtered.filter(**{lookup: value})
    try:
        ege_number = int(filters.get("ege") or "")
    except (TypeError, ValueError):
        ege_number = None
    if ege_number is not None:
        node_ids = [
            node.pk for node in KnowledgeNode.objects.only("pk", "ege_task_numbers")
            if ege_number in (node.ege_task_numbers or [])
        ]
        filtered = filtered.filter(skill_tags__node_id__in=node_ids)
    if include_ids:
        filtered = queryset.filter(Q(pk__in=include_ids) | Q(pk__in=filtered.values("pk")))
    return filtered.distinct()


def assignment_order_key(assignment):
    numbers = [
        number for node in assignment.skills.all()
        for number in (node.ege_task_numbers or [])
    ]
    return (min(numbers) if numbers else 999, assignment.exam_part, assignment.title.lower())


@transaction.atomic
def save_daily(*, actor, **kwargs):
    from apps.content.services import save_daily_challenge

    challenge = save_daily_challenge(created_by=actor, **kwargs)
    log_admin_action(
        actor, "daily_challenge.save", target=f"daily_challenge:{challenge.pk}",
        date=challenge.date.isoformat(), assignment_id=challenge.assignment_id,
    )
    return challenge


@transaction.atomic
def delete_daily(*, actor, challenge):
    from apps.content.services import delete_daily_challenge

    target = f"daily_challenge:{challenge.pk}"
    date = challenge.date.isoformat()
    delete_daily_challenge(challenge)
    log_admin_action(actor, "daily_challenge.delete", target=target, date=date)


@transaction.atomic
def change_tariff_price(*, actor, tariff, price_rub):
    from apps.billing.services import new_tariff_version

    updated = new_tariff_version(tariff, price_rub=price_rub)
    log_admin_action(
        actor, "tariff.new_version", target=f"tariff:{updated.pk}",
        code=updated.code, version=updated.version,
        price_from=str(tariff.price_rub), price_to=str(updated.price_rub),
    )
    return updated


def audit_saved(actor, action, instance, **payload):
    log_admin_action(
        actor, action,
        target=f"{instance._meta.model_name}:{instance.pk}",
        **payload,
    )
