"""Применение разметки из кода к графу знаний.

Загрузка обязана быть безопасной для действующих учеников: у навыков есть
история освоения, ошибок и планов, поэтому перенос новой версии книги — это
обновление на месте по коду навыка, а не «снести и залить заново».

Что делает загрузчик и чего не делает:

* создаёт и обновляет узлы и связи, сравнивая с тем, что уже в базе;
* показывает разницу до изменения — так видно, что именно приедет с новой
  версией книги;
* никогда не удаляет молча. Узел, исчезнувший из книги, попадает в отчёт как
  «лишний», а удаляется только явной командой и только если на него не
  ссылаются задачи и история учеников.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from .models import KnowledgeDependency, KnowledgeNode, TopicCluster

# Поля узла, которыми управляет разметка. Всё остальное (часы, вес, порядок)
# методист правит в панели, и перезапись затёрла бы его работу.
MANAGED_FIELDS = (
    "title", "node_type", "skill_class", "layer", "assessment_mode",
    "is_cross_domain", "exam_part", "ege_task_numbers",
)


@dataclass
class LoadReport:
    """Что изменилось при применении разметки."""

    markup: str = ""
    version: str = ""
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: int = 0
    changes: list[str] = field(default_factory=list)
    edges_created: int = 0
    edges_updated: int = 0
    edges_removed: int = 0
    orphans: list[str] = field(default_factory=list)
    blocked_orphans: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.created or self.updated or self.removed
            or self.edges_created or self.edges_updated or self.edges_removed
        )

    def lines(self) -> list[str]:
        out = [f"Разметка «{self.markup}» ({self.version})"]
        out.append(
            f"  узлы: создано {len(self.created)}, обновлено {len(self.updated)}, "
            f"без изменений {self.unchanged}"
        )
        out.extend(f"    {line}" for line in self.changes)
        out.append(
            f"  связи: создано {self.edges_created}, обновлено {self.edges_updated}, "
            f"удалено {self.edges_removed}"
        )
        if self.orphans:
            out.append("  лишние узлы (в книге их больше нет): " + ", ".join(self.orphans))
        if self.blocked_orphans:
            out.append(
                "  не удалить — есть задачи или история учеников: "
                + ", ".join(self.blocked_orphans)
            )
        if self.removed:
            out.append("  удалено: " + ", ".join(self.removed))
        return out


def _target_values(markup, skill: dict) -> dict:
    """Поля узла по строке разметки."""
    is_group = skill.get("node_type") == KnowledgeNode.NodeType.GROUP
    skill_class = skill.get("skill_class", KnowledgeNode.SkillClass.PROCEDURAL)
    cross_domain = bool(skill.get("cross_domain"))
    return {
        "title": skill["title"],
        "node_type": skill.get("node_type", KnowledgeNode.NodeType.ATOMIC),
        "skill_class": skill_class,
        # Оформление ответа — отдельный слой: предметное освоение оно менять
        # не должно (RULE-12 книги).
        "layer": (
            KnowledgeNode.Layer.EXAM_READINESS
            if skill_class == KnowledgeNode.SkillClass.FORMATTING
            else KnowledgeNode.Layer.SUBJECT
        ),
        # Пока шагов путей нет, способ проверки выводим из класса навыка:
        # обоснование проверяет человек, остальное — правило.
        "assessment_mode": (
            KnowledgeNode.AssessmentMode.RUBRIC
            if skill_class == KnowledgeNode.SkillClass.PROOF
            else KnowledgeNode.AssessmentMode.DETERMINISTIC
        ),
        "is_cross_domain": cross_domain,
        "exam_part": KnowledgeNode.Part.PART2,
        # Навык из другого раздела не относится к номеру этой разметки: иначе
        # прогноз засчитал бы номеру чужое умение.
        "ege_task_numbers": [] if (cross_domain or is_group) else list(markup.EGE_TASK_NUMBERS),
    }


def _diff(node: KnowledgeNode, target: dict) -> list[str]:
    changes = []
    for name in MANAGED_FIELDS:
        current, wanted = getattr(node, name), target[name]
        if current != wanted:
            changes.append(f"{node.code}.{name}: {current!r} → {wanted!r}")
    return changes


def load_markup(name: str, *, dry_run: bool = False, prune: bool = False) -> LoadReport:
    """Применить разметку к графу. Идемпотентна: повтор ничего не меняет."""
    from .markup import MARKUP_SETS

    markup = MARKUP_SETS[name]
    report = LoadReport(markup=name, version=getattr(markup, "VERSION", ""))

    with transaction.atomic():
        cluster, _ = TopicCluster.objects.get_or_create(
            title=markup.CLUSTER["title"],
            defaults={
                "exam_weight": markup.CLUSTER.get("exam_weight", 1.0),
                "color": markup.CLUSTER.get("color", "#4F6BEA"),
            },
        )
        existing = {node.code: node for node in KnowledgeNode.objects.filter(cluster=cluster)}
        wanted_codes = {skill["code"] for skill in markup.SKILLS}

        # Первый проход: сами узлы, без родителей — родитель может быть описан
        # ниже по списку.
        for order, skill in enumerate(markup.SKILLS):
            target = _target_values(markup, skill)
            node = existing.get(skill["code"])
            if node is None:
                node = KnowledgeNode(code=skill["code"], cluster=cluster, order=order, **target)
                if not dry_run:
                    node.save()
                existing[skill["code"]] = node
                report.created.append(skill["code"])
                continue
            changes = _diff(node, target)
            if not changes:
                report.unchanged += 1
                continue
            report.updated.append(skill["code"])
            report.changes.extend(changes)
            for field_name, value in target.items():
                setattr(node, field_name, value)
            if not dry_run:
                node.save(update_fields=list(target))

        # Второй проход: родители. Ссылки внутри набора уже существуют.
        for skill in markup.SKILLS:
            node = existing.get(skill["code"])
            parent_code = skill.get("parent") or None
            parent = existing.get(parent_code) if parent_code else None
            if node is None or node.parent_id == (parent.pk if parent else None):
                continue
            node.parent = parent
            report.changes.append(f"{node.code}.parent: → {parent_code or '—'}")
            if node.code not in report.created and node.code not in report.updated:
                report.updated.append(node.code)
                report.unchanged = max(0, report.unchanged - 1)
            if not dry_run:
                node.save(update_fields=["parent"])

        _load_edges(markup, existing, report, dry_run=dry_run)
        _handle_orphans(existing, wanted_codes, report, dry_run=dry_run, prune=prune)

        if dry_run:
            transaction.set_rollback(True)
    return report


def _load_edges(markup, nodes: dict[str, KnowledgeNode], report: LoadReport, *, dry_run: bool):
    """Связи набора. Разметка владеет ими целиком: лишние удаляются.

    Связь — это конфигурация графа, а не история ученика: её безопасно
    привести к тому, что написано в книге.
    """
    node_ids = [node.pk for node in nodes.values() if node.pk]
    existing = {
        (dependency.node_id, dependency.prerequisite_id): dependency
        for dependency in KnowledgeDependency.objects.filter(
            node_id__in=node_ids, prerequisite_id__in=node_ids
        )
    }
    wanted = set()
    for edge in markup.EDGES:
        node, prerequisite = nodes.get(edge["node"]), nodes.get(edge["prerequisite"])
        if node is None or prerequisite is None:
            raise ValueError(
                f"Связь ссылается на неизвестный навык: {edge['prerequisite']} → {edge['node']}"
            )
        if dry_run and (node.pk is None or prerequisite.pk is None):
            # Узлы ещё не созданы (сухой прогон на пустой базе) — считаем связь новой.
            report.edges_created += 1
            continue
        wanted.add((node.pk, prerequisite.pk))
        kind = edge.get("kind", KnowledgeDependency.Kind.PREREQUISITE)
        min_mastery = edge.get("min_mastery", 70)
        dependency = existing.get((node.pk, prerequisite.pk))
        if dependency is None:
            report.edges_created += 1
            if not dry_run:
                KnowledgeDependency.objects.create(
                    node=node, prerequisite=prerequisite, kind=kind, min_mastery=min_mastery
                )
            continue
        if dependency.kind == kind and dependency.min_mastery == min_mastery:
            continue
        report.edges_updated += 1
        report.changes.append(
            f"{prerequisite.code} → {node.code}: {dependency.kind} → {kind}"
        )
        if not dry_run:
            dependency.kind = kind
            dependency.min_mastery = min_mastery
            dependency.save(update_fields=["kind", "min_mastery"])

    for key, dependency in existing.items():
        if key in wanted:
            continue
        report.edges_removed += 1
        if not dry_run:
            dependency.delete()


def _handle_orphans(
    nodes: dict[str, KnowledgeNode], wanted: set[str], report: LoadReport,
    *, dry_run: bool, prune: bool,
):
    """Узлы, которых в книге больше нет.

    Удаление узла уносит с собой освоение, ошибки и пункты планов учеников,
    поэтому по умолчанию мы только сообщаем. С `--prune` удаляем — но лишь то,
    за что никто не держится.
    """
    from apps.content.models import AssignmentSkillTag

    for code, node in nodes.items():
        if code in wanted or node.pk is None:
            continue
        report.orphans.append(code)
        held_by_tasks = AssignmentSkillTag.objects.filter(node=node).exists()
        held_by_students = node.masteries.exists() or node.children.exists()
        if held_by_tasks or held_by_students:
            report.blocked_orphans.append(code)
            continue
        if prune:
            report.removed.append(code)
            if not dry_run:
                node.delete()
