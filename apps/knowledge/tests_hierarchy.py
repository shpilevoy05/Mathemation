"""Папки навыков и два вида связей.

Разметка методистов различает навык и папку над навыками, обязательную связь
и поддерживающую. Тесты фиксируют разницу там, где она меняет поведение
продукта: план, карта, прогноз и ворота открытия тем.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.content.models import Lesson
from apps.planning.services import build_study_plan, get_active_plan, order_pending_nodes
from apps.practice.tests import make_assignment
from apps.progress.services import weak_topics
from apps.web.services import knowledge_map_context

from .models import KnowledgeDependency, KnowledgeNode, SkillMastery
from .services import group_mastery, node_states, set_mastery
from .tests import make_node, make_student


def make_group(code="group", cluster=None, **kwargs) -> KnowledgeNode:
    return make_node(code, cluster=cluster, node_type=KnowledgeNode.NodeType.GROUP, **kwargs)


class HierarchyRulesTests(TestCase):
    def setUp(self):
        self.group = make_group("odz")
        self.child = make_node("odz-denominator", cluster=self.group.cluster, parent=self.group)

    def test_folder_holds_skills(self):
        self.assertEqual(list(self.group.children.all()), [self.child])

    def test_skill_cannot_parent_a_skill(self):
        other = make_node("plain", cluster=self.group.cluster)
        other.parent = self.child

        with self.assertRaises(ValidationError):
            other.full_clean()

    def test_folder_cannot_nest_in_a_folder(self):
        inner = make_group("inner", cluster=self.group.cluster)
        inner.parent = self.group

        with self.assertRaises(ValidationError):
            inner.full_clean()

    def test_dependency_between_folders_is_refused(self):
        other = make_node("other", cluster=self.group.cluster)

        with self.assertRaises(ValidationError):
            KnowledgeDependency.objects.create(node=other, prerequisite=self.group)


class EdgeKindTests(TestCase):
    def setUp(self):
        self.student = make_student("edge-student")
        self.target = make_node("target")
        self.gate = make_node("gate", cluster=self.target.cluster)
        self.helper = make_node("helper", cluster=self.target.cluster)

    def test_supporting_edge_does_not_lock_the_topic(self):
        KnowledgeDependency.objects.create(
            node=self.target, prerequisite=self.helper,
            kind=KnowledgeDependency.Kind.SUPPORTS, min_mastery=70,
        )

        state = node_states(self.student)[self.target.id]

        # Поддерживающая связь объясняет порядок, но тему не закрывает.
        self.assertEqual(state["state"], "available")
        self.assertEqual(state["unmet_conditions"], [])
        self.assertEqual(state["supporting"][0]["node_id"], self.helper.id)

    def test_required_edge_locks_the_topic(self):
        KnowledgeDependency.objects.create(
            node=self.target, prerequisite=self.gate, min_mastery=70
        )

        state = node_states(self.student)[self.target.id]

        self.assertEqual(state["state"], "locked")
        self.assertEqual(state["unmet_conditions"][0]["node_id"], self.gate.id)

    def test_supporting_edges_may_point_both_ways(self):
        KnowledgeDependency.objects.create(
            node=self.target, prerequisite=self.helper,
            kind=KnowledgeDependency.Kind.SUPPORTS,
        )

        # «Одно помогает понять другое» в обе стороны — нормальное методическое
        # утверждение, и циклом оно не считается.
        KnowledgeDependency.objects.create(
            node=self.helper, prerequisite=self.target,
            kind=KnowledgeDependency.Kind.SUPPORTS,
        )

        self.assertEqual(KnowledgeDependency.objects.count(), 2)

    def test_required_edges_still_cannot_form_a_cycle(self):
        KnowledgeDependency.objects.create(node=self.target, prerequisite=self.gate)

        with self.assertRaises(ValidationError):
            KnowledgeDependency.objects.create(node=self.gate, prerequisite=self.target)


class FolderMasteryTests(TestCase):
    def setUp(self):
        self.student = make_student("folder-student")
        self.group = make_group("selection")
        self.first = make_node("circle", cluster=self.group.cluster, parent=self.group)
        self.second = make_node("inequalities", cluster=self.group.cluster, parent=self.group)

    def test_average_is_the_default(self):
        set_mastery(self.student, self.first, 80)
        set_mastery(self.student, self.second, 40)

        self.assertEqual(node_states(self.student)[self.group.id]["mastery"], 60)

    def test_minimum_follows_the_weakest_child(self):
        self.group.group_aggregation = KnowledgeNode.GroupAggregation.MINIMUM
        self.group.save(update_fields=["group_aggregation"])
        set_mastery(self.student, self.first, 80)
        set_mastery(self.student, self.second, 40)

        self.assertEqual(node_states(self.student)[self.group.id]["mastery"], 40)

    def test_empty_folder_proves_nothing(self):
        empty = make_group("empty", cluster=self.group.cluster)

        state = node_states(self.student)[empty.id]

        self.assertEqual(state["mastery"], 0)
        self.assertEqual(state["state"], "locked")

    def test_folder_has_no_mastery_row_of_its_own(self):
        set_mastery(self.student, self.first, 90)
        node_states(self.student)

        self.assertFalse(
            SkillMastery.objects.filter(student=self.student, node=self.group).exists()
        )

    def test_aggregation_helper_handles_both_modes(self):
        self.assertEqual(group_mastery(self.group, [10, 50]), 30)
        self.group.group_aggregation = KnowledgeNode.GroupAggregation.MINIMUM
        self.assertEqual(group_mastery(self.group, [10, 50]), 10)
        self.assertEqual(group_mastery(self.group, []), 0.0)


class FolderStaysOutOfLearningTests(TestCase):
    def setUp(self):
        self.student = make_student("plan-folder-student")
        self.group = make_group("substitution")
        self.skill = make_node("choose-substitution", cluster=self.group.cluster, parent=self.group)
        make_assignment(self.skill, answer="1")

    def test_folder_is_not_planned(self):
        build_study_plan(self.student)

        node_ids = set(
            get_active_plan(self.student).items.values_list("node_id", flat=True)
        )
        self.assertIn(self.skill.id, node_ids)
        self.assertNotIn(self.group.id, node_ids)

    def test_folder_is_not_in_the_learning_order(self):
        self.assertNotIn(self.group.id, [node.id for node in order_pending_nodes(self.student)])

    def test_folder_is_not_a_track_point(self):
        from apps.web.services import track_context

        Lesson.objects.create(
            node=self.skill, title="Занятие", status=Lesson.Status.PUBLISHED
        )
        Lesson.objects.create(
            node=self.group, title="Занятие папки", status=Lesson.Status.PUBLISHED
        )

        points = [
            point
            for cluster in track_context(self.student)["track_clusters"]
            for point in cluster["points"]
        ]

        self.assertTrue(points)
        self.assertNotIn(self.group.id, {point["node_id"] for point in points})

    def test_folder_is_not_a_weak_topic(self):
        set_mastery(self.student, self.skill, 90)

        self.assertNotIn(
            self.group.id, {topic["node_id"] for topic in weak_topics(self.student)}
        )

    def test_map_shows_the_folder_as_a_section_not_a_card(self):
        context = knowledge_map_context(self.student)
        cluster = context["clusters"][0]

        self.assertEqual([group["id"] for group in cluster["groups"]], [self.group.id])
        self.assertEqual([node["id"] for node in cluster["groups"][0]["nodes"]], [self.skill.id])
        self.assertEqual(cluster["loose_nodes"], [])
        # В графе рисуются навыки: у папки нет ни связей, ни практики.
        self.assertNotIn(self.group.id, {node["id"] for node in context["graph"]["nodes"]})
