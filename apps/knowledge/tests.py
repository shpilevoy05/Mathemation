from datetime import timedelta

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import StudentProfile, User
from apps.knowledge.models import (
    KnowledgeDependency,
    KnowledgeNode,
    SkillMastery,
    TopicCluster,
)
from apps.knowledge.services import apply_decay, node_states, set_mastery, update_mastery


def make_student(username="s1", **kwargs):
    user = User.objects.create_user(username=username, role=User.Role.STUDENT)
    return StudentProfile.objects.create(user=user, **kwargs)


def make_node(code="alg-1", cluster=None, **kwargs):
    cluster = cluster or TopicCluster.objects.create(title="Алгебра")
    return KnowledgeNode.objects.create(code=code, title=code, cluster=cluster, **kwargs)


class MasteryUpdateTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.node = make_node()

    def test_correct_attempt_raises_mastery(self):
        sm = update_mastery(self.student, self.node, correct=True)
        self.assertEqual(sm.mastery, 30.0)  # 0 + 0.3 * (100 - 0)
        self.assertEqual(sm.status, SkillMastery.Status.IN_PROGRESS)

    def test_wrong_attempt_lowers_mastery(self):
        set_mastery(self.student, self.node, 80)
        sm = update_mastery(self.student, self.node, correct=False)
        self.assertEqual(sm.mastery, 56.0)  # 80 + 0.3 * (0 - 80)
        self.assertEqual(sm.status, SkillMastery.Status.PRACTICED)

    def test_weight_scales_step(self):
        sm = update_mastery(self.student, self.node, correct=True, weight=0.5)
        self.assertEqual(sm.mastery, 15.0)

    def test_status_thresholds(self):
        self.assertEqual(
            set_mastery(self.student, self.node, 0).status, SkillMastery.Status.NOT_STARTED
        )
        self.assertEqual(
            set_mastery(self.student, self.node, 75).status, SkillMastery.Status.MASTERED
        )

    def test_mastery_clamped_to_bounds(self):
        sm = set_mastery(self.student, self.node, 150)
        self.assertEqual(sm.mastery, 100.0)


class DecayTests(TestCase):
    """Забывание: узел «остывает» после паузы и возвращается в план."""

    def setUp(self):
        self.student = make_student()
        self.node = make_node()

    def _age_peak(self, sm, days):
        sm.peak_at = timezone.now() - timedelta(days=days)
        sm.save(update_fields=["peak_at"])

    def test_no_decay_within_grace_period(self):
        sm = set_mastery(self.student, self.node, 90)
        self._age_peak(sm, settings.DECAY_GRACE_DAYS - 1)
        apply_decay(self.student)
        sm.refresh_from_db()
        self.assertEqual(sm.mastery, 90.0)
        self.assertEqual(sm.status, SkillMastery.Status.MASTERED)

    def test_mastered_node_decays_to_forgotten_state(self):
        from apps.planning.services import build_study_plan

        build_study_plan(self.student)
        sm = set_mastery(self.student, self.node, 90)
        self._age_peak(sm, settings.DECAY_GRACE_DAYS + 60)
        newly = apply_decay(self.student)
        sm.refresh_from_db()
        self.assertLess(sm.mastery, 70)
        self.assertEqual(sm.status, SkillMastery.Status.DECAYED)
        self.assertGreater(sm.decay_percent, 0)
        self.assertEqual(len(newly), 1)
        # Узел сам вернулся в план с пометкой «подзабылось».
        from apps.planning.models import PlanChangeLog, StudyPlanItem

        self.assertTrue(
            StudyPlanItem.objects.filter(
                plan__student=self.student, node=self.node,
                status=StudyPlanItem.Status.PENDING,
            ).exists()
        )
        self.assertTrue(
            PlanChangeLog.objects.filter(reason=PlanChangeLog.Reason.DECAY).exists()
        )

    def test_apply_decay_idempotent(self):
        sm = set_mastery(self.student, self.node, 90)
        self._age_peak(sm, settings.DECAY_GRACE_DAYS + 30)
        apply_decay(self.student)
        first = SkillMastery.objects.get(pk=sm.pk).mastery
        apply_decay(self.student)
        self.assertEqual(SkillMastery.objects.get(pk=sm.pk).mastery, first)

    def test_practice_resets_forgetting_curve(self):
        sm = set_mastery(self.student, self.node, 90)
        self._age_peak(sm, settings.DECAY_GRACE_DAYS + 60)
        apply_decay(self.student)
        update_mastery(self.student, self.node, correct=True)
        sm.refresh_from_db()
        self.assertEqual(sm.peak_mastery, sm.mastery)
        self.assertGreater(sm.peak_at, timezone.now() - timedelta(minutes=1))


class NodeStatesTests(TestCase):
    """Состояния карты: закрыто / можно начинать / освоено."""

    def test_locked_until_prerequisite_mastered(self):
        student = make_student()
        base = make_node("base")
        adv = make_node("adv", cluster=base.cluster)
        KnowledgeDependency.objects.create(node=adv, prerequisite=base)

        states = node_states(student)
        self.assertEqual(states[base.id]["state"], "available")
        self.assertEqual(states[adv.id]["state"], "locked")

        set_mastery(student, base, 80)
        states = node_states(student)
        self.assertEqual(states[base.id]["state"], "mastered")
        self.assertEqual(states[adv.id]["state"], "available")

    def test_each_dependency_uses_its_own_mastery_threshold(self):
        student = make_student()
        base = make_node("base")
        threshold_50 = make_node("threshold-50", cluster=base.cluster)
        threshold_80 = make_node("threshold-80", cluster=base.cluster)
        KnowledgeDependency.objects.create(
            node=threshold_50, prerequisite=base, min_mastery=50
        )
        KnowledgeDependency.objects.create(
            node=threshold_80, prerequisite=base, min_mastery=80
        )

        set_mastery(student, base, 45)
        states = node_states(student)
        self.assertEqual(states[threshold_50.id]["state"], "locked")
        self.assertEqual(states[threshold_50.id]["unmet_conditions"][0]["current_mastery"], 45)

        set_mastery(student, base, 55)
        states = node_states(student)
        self.assertEqual(states[threshold_50.id]["state"], "available")
        self.assertEqual(states[threshold_80.id]["state"], "locked")
        self.assertEqual(states[threshold_80.id]["unmet_conditions"][0]["required_mastery"], 80)


class KnowledgeMapApiTests(TestCase):
    def test_locked_node_exposes_unmet_opening_condition(self):
        student = make_student()
        base = make_node("api-base")
        child = make_node("api-child", cluster=base.cluster)
        KnowledgeDependency.objects.create(
            node=child, prerequisite=base, min_mastery=80
        )
        set_mastery(student, base, 55)
        self.client.force_login(student.user)

        response = self.client.get("/api/knowledge-map/")

        self.assertEqual(response.status_code, 200)
        child_payload = next(
            node
            for cluster in response.json()["clusters"]
            for node in cluster["nodes"]
            if node["id"] == child.id
        )
        self.assertEqual(child_payload["state"], "locked")
        self.assertEqual(
            child_payload["unmet_conditions"][0],
            {
                "node_id": base.id,
                "title": base.title,
                "required_mastery": 80,
                "current_mastery": 55.0,
            },
        )
