"""Перенумерация заданий ЕГЭ при переходе на структуру 2027 года."""

from importlib import import_module
from types import SimpleNamespace

from django.apps import apps as django_apps
from django.db import connection
from django.test import TestCase

from apps.exams.models import ExamProfile, ExamTask

from .models import KnowledgeNode, TopicCluster
from .numbering import EGE_2027_RENUMBERING, NEW_IN_2027, renumber, renumber_nodes


class MapTests(TestCase):
    def test_part_one_shifts_after_the_new_task_six(self):
        # Прежнее задание 6 (простейшие уравнения) стало седьмым.
        self.assertEqual(EGE_2027_RENUMBERING[6], 7)
        self.assertEqual(EGE_2027_RENUMBERING[5], 5)

    def test_part_two_shifts_by_one(self):
        self.assertEqual(EGE_2027_RENUMBERING[13], 14)
        self.assertEqual(EGE_2027_RENUMBERING[19], 20)

    def test_moved_tasks_land_on_their_own_numbers(self):
        self.assertEqual(EGE_2027_RENUMBERING[8], 9)
        self.assertEqual(EGE_2027_RENUMBERING[12], 17)
        self.assertEqual(EGE_2027_RENUMBERING[16], 13)

    def test_new_tasks_have_no_predecessor(self):
        for number in NEW_IN_2027:
            self.assertNotIn(number, EGE_2027_RENUMBERING.values())

    def test_map_covers_the_whole_old_exam(self):
        self.assertEqual(sorted(EGE_2027_RENUMBERING), list(range(1, 20)))

    def test_every_new_number_is_reachable(self):
        covered = set(EGE_2027_RENUMBERING.values()) | set(NEW_IN_2027)

        self.assertEqual(covered, set(range(1, 21)))


class RenumberTests(TestCase):
    def test_numbers_are_translated(self):
        self.assertEqual(renumber([6, 13]), [7, 14])

    def test_graph_derivative_and_extremum_are_not_merged(self):
        self.assertEqual(renumber([8, 12]), [9, 17])

    def test_order_is_kept(self):
        self.assertEqual(renumber([19, 1]), [20, 1])

    def test_empty_stays_empty(self):
        self.assertEqual(renumber([]), [])
        self.assertEqual(renumber(None), [])

    def test_unknown_numbers_are_left_alone(self):
        # Номер 20 в старой нумерации не существовал: его не за что двигать.
        self.assertEqual(renumber([20]), [20])


class RenumberNodesTests(TestCase):
    def setUp(self):
        self.cluster = TopicCluster.objects.create(title="Тема", order=0)

    def node(self, code: str, numbers: list[int]) -> KnowledgeNode:
        return KnowledgeNode.objects.create(
            code=code, title=code, cluster=self.cluster, ege_task_numbers=numbers
        )

    def test_nodes_move_to_the_new_numbering(self):
        node = self.node("trig-eq", [13])

        changed = renumber_nodes(KnowledgeNode)

        node.refresh_from_db()
        self.assertEqual(node.ege_task_numbers, [14])
        self.assertEqual(changed, 1)

    def test_untouched_nodes_are_not_counted(self):
        self.node("planimetry", [1])

        self.assertEqual(renumber_nodes(KnowledgeNode), 0)

    def test_folders_without_numbers_survive(self):
        folder = self.node("folder", [])

        renumber_nodes(KnowledgeNode)

        folder.refresh_from_db()
        self.assertEqual(folder.ege_task_numbers, [])


class RepairMigrationTests(TestCase):
    def setUp(self):
        cluster = TopicCluster.objects.create(title="Ремонт нумерации", order=0)
        self.deriv = KnowledgeNode.objects.create(
            code="deriv-graph", title="Производная по графику", cluster=cluster,
            ege_task_numbers=[9],
        )
        self.extrema = KnowledgeNode.objects.create(
            code="extrema", title="Экстремумы", cluster=cluster,
            ege_task_numbers=[9],
        )
        self.economics = KnowledgeNode.objects.create(
            code="economics", title="Экономическая задача", cluster=cluster,
            ege_task_numbers=[17],
        )
        self.personal_finance = KnowledgeNode.objects.create(
            code="personal-finance", title="Личные финансы", cluster=cluster,
            ege_task_numbers=[13],
        )
        self.migration = import_module(
            "apps.knowledge.migrations.0010_repair_ege_tasks_2027"
        )

    def test_reference_node_repair_is_explicit_and_idempotent(self):
        first = self.migration.repair_reference_nodes(KnowledgeNode)
        second = self.migration.repair_reference_nodes(KnowledgeNode)

        self.deriv.refresh_from_db()
        self.extrema.refresh_from_db()
        self.economics.refresh_from_db()
        self.assertEqual(first, 2)
        self.assertEqual(second, 0)
        self.assertEqual(self.deriv.ege_task_numbers, [9])
        self.assertEqual(self.extrema.ege_task_numbers, [17])
        self.assertEqual(self.economics.ege_task_numbers, [13])

    def test_forward_reloads_profile_and_corrected_skill_links(self):
        editor = SimpleNamespace(connection=connection)

        self.migration.forward(django_apps, editor)
        self.migration.forward(django_apps, editor)

        profile = ExamProfile.active()
        task13 = ExamTask.objects.get(profile=profile, number=13)
        task17 = ExamTask.objects.get(profile=profile, number=17)
        self.assertEqual(task13.max_score, 1)
        self.assertEqual(
            set(task13.skills.values_list("node__code", flat=True)),
            {"economics", "personal-finance"},
        )
        self.assertEqual(
            set(task17.skills.values_list("node__code", flat=True)),
            {"extrema"},
        )
