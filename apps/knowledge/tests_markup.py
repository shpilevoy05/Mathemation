"""Разметка в коде: целостность данных и безопасность загрузки.

Лист QA книги проверял разметку глазами перед передачей. Здесь те же проверки
идут в CI: разметка стала кодом, а значит ошибка в ней ломает сборку, а не
обнаруживается на ученике через месяц.
"""

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from io import StringIO

from apps.content.models import AssignmentSkillTag
from apps.practice.tests import make_assignment

from .markup import MARKUP_SETS, ege13
from .markup_loader import load_markup
from .models import KnowledgeDependency, KnowledgeNode
from .services import would_create_cycle
from .tests import make_student


class MarkupIntegrityTests(TestCase):
    """Проверки самих данных — без базы: ошибку видно до загрузки."""

    def test_counts_match_the_book(self):
        groups = [s for s in ege13.SKILLS if s["node_type"] == "group"]

        self.assertEqual(len(ege13.SKILLS), 66)
        self.assertEqual(len(groups), 5)
        self.assertEqual(len(ege13.SKILLS) - len(groups), 61)
        self.assertEqual(len(ege13.EDGES), 60)

    def test_codes_are_unique(self):
        codes = [skill["code"] for skill in ege13.SKILLS]

        self.assertEqual(len(codes), len(set(codes)))

    def test_every_parent_exists_and_is_a_folder(self):
        by_code = {skill["code"]: skill for skill in ege13.SKILLS}

        for skill in ege13.SKILLS:
            parent_code = skill.get("parent")
            if not parent_code:
                continue
            self.assertIn(parent_code, by_code, f"{skill['code']}: нет родителя {parent_code}")
            self.assertEqual(by_code[parent_code]["node_type"], "group", parent_code)
            self.assertEqual(skill["node_type"], "atomic", skill["code"])

    def test_every_folder_has_children(self):
        parents = {skill.get("parent") for skill in ege13.SKILLS}

        for skill in ege13.SKILLS:
            if skill["node_type"] == "group":
                self.assertIn(skill["code"], parents, f"папка без детей: {skill['code']}")

    def test_edges_reference_known_skills(self):
        codes = {skill["code"] for skill in ege13.SKILLS}

        for edge in ege13.EDGES:
            self.assertIn(edge["prerequisite"], codes)
            self.assertIn(edge["node"], codes)
            self.assertNotEqual(edge["prerequisite"], edge["node"])

    def test_edges_never_touch_folders(self):
        folders = {s["code"] for s in ege13.SKILLS if s["node_type"] == "group"}

        for edge in ege13.EDGES:
            self.assertNotIn(edge["prerequisite"], folders)
            self.assertNotIn(edge["node"], folders)

    def test_edges_are_unique(self):
        pairs = [(edge["prerequisite"], edge["node"]) for edge in ege13.EDGES]

        self.assertEqual(len(pairs), len(set(pairs)))

    def test_gates_form_an_acyclic_graph(self):
        gates: dict[str, list[str]] = {}
        for edge in ege13.EDGES:
            if edge.get("kind", "prerequisite") == "prerequisite":
                gates.setdefault(edge["node"], []).append(edge["prerequisite"])

        # Обход в глубину с цветами: серый узел на пути означает цикл.
        state: dict[str, int] = {}

        def visit(code: str) -> None:
            if state.get(code) == 2:
                return
            self.assertNotEqual(state.get(code), 1, f"цикл через {code}")
            state[code] = 1
            for prerequisite in gates.get(code, []):
                visit(prerequisite)
            state[code] = 2

        for code in list(gates):
            visit(code)

    def test_gate_count_matches_the_hard_dependencies_of_the_book(self):
        gates = [e for e in ege13.EDGES if e.get("kind", "prerequisite") == "prerequisite"]

        # 33 жёстких prerequisite книги; остальные 27 — поддерживающие,
        # включая шесть мягких prerequisite.
        self.assertEqual(len(gates), 33)

    def test_every_markup_set_declares_its_version(self):
        for name, markup in MARKUP_SETS.items():
            self.assertTrue(getattr(markup, "VERSION", ""), name)
            self.assertTrue(markup.CLUSTER.get("title"), name)


class MarkupLoadTests(TestCase):
    def setUp(self):
        self.report = load_markup("ege13")

    def test_graph_matches_the_markup(self):
        self.assertEqual(len(self.report.created), 66)
        self.assertEqual(KnowledgeNode.objects.filter(code__startswith="SK-MA-").count(), 66)
        self.assertEqual(KnowledgeDependency.objects.count(), 60)
        self.assertEqual(
            KnowledgeDependency.objects.filter(
                kind=KnowledgeDependency.Kind.PREREQUISITE
            ).count(),
            33,
        )

    def test_repeat_changes_nothing(self):
        second = load_markup("ege13")

        self.assertFalse(second.has_changes)
        self.assertEqual(second.unchanged, 66)

    def test_folders_and_parents_arrive(self):
        folder = KnowledgeNode.objects.get(code="SK-MA-0014")

        self.assertTrue(folder.is_group)
        self.assertEqual(folder.children.count(), 4)
        self.assertTrue(all(not child.is_group for child in folder.children.all()))

    def test_formatting_skill_goes_to_the_exam_layer(self):
        node = KnowledgeNode.objects.get(code="SK-MA-0018")

        # Оформление ответа не должно ронять предметное освоение.
        self.assertEqual(node.layer, KnowledgeNode.Layer.EXAM_READINESS)

    def test_proof_skill_is_marked_for_the_expert(self):
        node = KnowledgeNode.objects.get(code="SK-MA-0017")

        self.assertEqual(node.assessment_mode, KnowledgeNode.AssessmentMode.RUBRIC)

    def test_cross_domain_skill_is_not_credited_to_the_task_number(self):
        borrowed = KnowledgeNode.objects.get(code="SK-MA-0059")
        own = KnowledgeNode.objects.get(code="SK-MA-0001")

        self.assertTrue(borrowed.is_cross_domain)
        self.assertEqual(borrowed.ege_task_numbers, [])
        self.assertEqual(own.ege_task_numbers, [13])

    def test_folder_carries_no_task_number(self):
        self.assertEqual(KnowledgeNode.objects.get(code="SK-MA-0014").ege_task_numbers, [])

    def test_changed_title_is_updated_in_place(self):
        node = KnowledgeNode.objects.get(code="SK-MA-0001")
        node.title = "Старое название"
        node.save(update_fields=["title"])

        report = load_markup("ege13")

        node.refresh_from_db()
        self.assertIn("SK-MA-0001", report.updated)
        self.assertNotEqual(node.title, "Старое название")

    def test_hand_edited_hours_survive_the_reload(self):
        node = KnowledgeNode.objects.get(code="SK-MA-0001")
        node.hours_estimate = 0.5
        node.save(update_fields=["hours_estimate"])

        load_markup("ege13")

        node.refresh_from_db()
        # Часами и весом управляет методист в панели: разметка их не трогает.
        self.assertEqual(node.hours_estimate, 0.5)

    def test_dry_run_writes_nothing(self):
        KnowledgeNode.objects.filter(code="SK-MA-0001").update(title="Черновик")

        report = load_markup("ege13", dry_run=True)

        self.assertTrue(report.has_changes)
        self.assertEqual(
            KnowledgeNode.objects.get(code="SK-MA-0001").title, "Черновик"
        )

    def test_stale_edge_is_removed(self):
        first = KnowledgeNode.objects.get(code="SK-MA-0001")
        second = KnowledgeNode.objects.get(code="SK-MA-0003")
        KnowledgeDependency.objects.create(
            node=second, prerequisite=first, kind=KnowledgeDependency.Kind.SUPPORTS
        )

        report = load_markup("ege13")

        self.assertEqual(report.edges_removed, 1)
        self.assertEqual(KnowledgeDependency.objects.count(), 60)


class OrphanTests(TestCase):
    def setUp(self):
        load_markup("ege13")
        self.cluster = KnowledgeNode.objects.get(code="SK-MA-0001").cluster
        self.orphan = KnowledgeNode.objects.create(
            code="SK-MA-9999", title="Навык из прошлой версии", cluster=self.cluster
        )

    def test_orphan_is_reported_but_kept(self):
        report = load_markup("ege13")

        self.assertIn("SK-MA-9999", report.orphans)
        self.assertTrue(KnowledgeNode.objects.filter(code="SK-MA-9999").exists())

    def test_free_orphan_is_removed_on_request(self):
        report = load_markup("ege13", prune=True)

        self.assertIn("SK-MA-9999", report.removed)
        self.assertFalse(KnowledgeNode.objects.filter(code="SK-MA-9999").exists())

    def test_orphan_with_tasks_is_never_removed_silently(self):
        make_assignment(self.orphan, answer="1")

        report = load_markup("ege13", prune=True)

        self.assertIn("SK-MA-9999", report.blocked_orphans)
        self.assertTrue(KnowledgeNode.objects.filter(code="SK-MA-9999").exists())
        self.assertTrue(AssignmentSkillTag.objects.filter(node=self.orphan).exists())

    def test_orphan_with_student_history_is_never_removed_silently(self):
        from .services import set_mastery

        set_mastery(make_student("orphan-student"), self.orphan, 50)

        report = load_markup("ege13", prune=True)

        self.assertIn("SK-MA-9999", report.blocked_orphans)
        self.assertTrue(KnowledgeNode.objects.filter(code="SK-MA-9999").exists())


class CommandTests(TestCase):
    def test_command_loads_and_reports(self):
        out = StringIO()

        call_command("load_markup", stdout=out)

        output = out.getvalue()
        self.assertIn("WBS 2 v4.1", output)
        self.assertIn("создано 66", output)

    def test_dry_run_says_it_changed_nothing(self):
        call_command("load_markup", stdout=StringIO())
        out = StringIO()

        call_command("load_markup", "--dry-run", stdout=out)

        self.assertIn("уже применена", out.getvalue())

    def test_unknown_set_is_refused(self):
        with self.assertRaises(CommandError):
            call_command("load_markup", "--set", "ege42", stdout=StringIO())


class LoadedGraphBehaviourTests(TestCase):
    """Загруженный граф ведёт себя как граф, а не как список."""

    def setUp(self):
        load_markup("ege13")

    def test_gates_keep_the_graph_acyclic_in_the_database(self):
        first = KnowledgeNode.objects.get(code="SK-MA-0023")
        second = KnowledgeNode.objects.get(code="SK-MA-0024")

        # 0023 → 0024 уже есть: обратная обязательная связь замкнула бы граф.
        self.assertTrue(would_create_cycle(first, second))

    def test_supporting_edges_did_not_become_gates(self):
        node = KnowledgeNode.objects.get(code="SK-MA-0010")

        supporting = node.dependencies.filter(kind=KnowledgeDependency.Kind.SUPPORTS)

        self.assertTrue(supporting.exists())

    def test_folders_stay_out_of_the_learning_order(self):
        from apps.planning.services import order_pending_nodes

        student = make_student("markup-student")
        ordered = {node.code for node in order_pending_nodes(student)}

        self.assertNotIn("SK-MA-0014", ordered)
        self.assertIn("SK-MA-0027", ordered)
