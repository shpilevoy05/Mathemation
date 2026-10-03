"""Перенумерация заданий ЕГЭ при переходе на структуру 2027 года."""

from django.test import TestCase

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

    def test_merged_tasks_land_on_nine(self):
        # Производная по графику и наибольшее значение слились в задание 9.
        self.assertEqual(EGE_2027_RENUMBERING[8], 9)
        self.assertEqual(EGE_2027_RENUMBERING[12], 9)

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

    def test_merged_numbers_are_not_duplicated(self):
        # Узел, отвечавший и за 8, и за 12, получает один номер 9, а не два.
        self.assertEqual(renumber([8, 12]), [9])

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
