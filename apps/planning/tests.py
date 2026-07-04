from django.test import TestCase

from apps.knowledge.models import KnowledgeDependency, TopicCluster
from apps.knowledge.services import set_mastery
from apps.knowledge.tests import make_node, make_student
from apps.planning.models import StudyPlanItem
from apps.planning.services import build_study_plan, get_active_plan


class StudyPlanTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.cluster = TopicCluster.objects.create(title="Алгебра")
        self.basic = make_node("basic", cluster=self.cluster)
        self.advanced = make_node("advanced", cluster=self.cluster)
        KnowledgeDependency.objects.create(node=self.advanced, prerequisite=self.basic)

    def _node_order(self, plan):
        seen = []
        for item in plan.items.all():
            if item.node_id not in seen:
                seen.append(item.node_id)
        return seen

    def test_prerequisites_come_first(self):
        plan = build_study_plan(self.student)
        order = self._node_order(plan)
        self.assertLess(order.index(self.basic.id), order.index(self.advanced.id))

    def test_mastered_nodes_skipped(self):
        set_mastery(self.student, self.basic, 90)
        plan = build_study_plan(self.student)
        self.assertNotIn(self.basic.id, self._node_order(plan))
        self.assertIn(self.advanced.id, self._node_order(plan))

    def test_each_node_gets_lesson_and_practice(self):
        plan = build_study_plan(self.student)
        types = set(
            plan.items.filter(node=self.basic).values_list("item_type", flat=True)
        )
        self.assertEqual(
            types, {StudyPlanItem.ItemType.LESSON, StudyPlanItem.ItemType.PRACTICE}
        )

    def test_rebuild_archives_previous_plan(self):
        first = build_study_plan(self.student)
        second = build_study_plan(self.student)
        first.refresh_from_db()
        self.assertEqual(first.status, "archived")
        self.assertEqual(get_active_plan(self.student).id, second.id)

    def test_higher_weight_scheduled_earlier(self):
        heavy = make_node("heavy", cluster=self.cluster, weight=5.0)
        plan = build_study_plan(self.student)
        order = self._node_order(plan)
        self.assertEqual(order[0], heavy.id)

    def test_rebuild_after_inactivity_logs_major_change(self):
        from apps.planning.models import PlanChangeLog
        from apps.planning.services import rebuild_after_inactivity

        build_study_plan(self.student)
        plan = rebuild_after_inactivity(self.student, idle_days=14)
        self.assertIsNotNone(plan)
        change = PlanChangeLog.objects.get(reason=PlanChangeLog.Reason.INACTIVITY)
        self.assertTrue(change.is_major)
        self.assertFalse(change.acknowledged)
        # Снижение показываем фактом, без упрёка: в тексте есть прогноз.
        self.assertIn("прогноз", change.description.lower())

    def test_rebuild_after_inactivity_skips_students_without_plan(self):
        from apps.planning.services import rebuild_after_inactivity

        self.assertIsNone(rebuild_after_inactivity(self.student, idle_days=14))
