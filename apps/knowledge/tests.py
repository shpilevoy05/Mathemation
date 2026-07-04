from django.test import TestCase

from apps.accounts.models import StudentProfile, User
from apps.knowledge.models import KnowledgeNode, SkillMastery, TopicCluster
from apps.knowledge.services import set_mastery, update_mastery


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
