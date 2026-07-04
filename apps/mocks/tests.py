from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.content.models import Assignment
from apps.expert_review.services import finish_review, submit_solution
from apps.knowledge.tests import make_node, make_student
from apps.mocks.models import MockExam, MockExamResult
from apps.mocks.services import complete_mock_part1
from apps.practice.models import Attempt
from apps.practice.services import submit_attempt
from apps.practice.tests import make_assignment


def _solution_file():
    return SimpleUploadedFile("solution.jpg", b"scan")


class MockLifecycleTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.node1 = make_node("m1")
        self.node2 = make_node("m2", cluster=self.node1.cluster)
        self.a1 = make_assignment(self.node1, answer="7")
        self.a2 = make_assignment(self.node2, answer="", part=Assignment.Part.PART2)
        self.a2.max_score = 2
        self.a2.save()
        self.exam = MockExam.objects.create(title="Пробник", duration_minutes=235)
        self.exam.assignments.set([self.a1, self.a2])
        self.expert = get_user_model().objects.create_user(
            username="exp", role="expert"
        )

    def _run_part1(self, correct=True):
        result = MockExamResult.objects.create(student=self.student, exam=self.exam)
        submit_attempt(
            self.student, self.a1, "7" if correct else "0",
            context=Attempt.Context.MOCK, mock_result=result,
        )
        return complete_mock_part1(result)

    def test_part1_checked_waits_for_expert(self):
        result = self._run_part1()
        self.assertEqual(result.status, MockExamResult.Status.PART1_CHECKED)
        self.assertEqual(result.primary_score, 1)
        # Калибровка не трогается, пока вторая часть у эксперта.
        self.student.refresh_from_db()
        self.assertEqual(self.student.forecast_calibration, 0)

    def test_expert_verdict_completes_mock_and_calibrates(self):
        result = self._run_part1()
        review = submit_solution(
            self.student, self.a2, _solution_file(), mock_result=result
        )
        finish_review(review, self.expert, {"К1": 1, "К2": 1}, comment="Отлично")
        result.refresh_from_db()
        self.assertEqual(result.status, MockExamResult.Status.COMPLETED)
        self.assertEqual(result.part2_primary_score, 2)
        self.assertEqual(result.total_primary_score, 3)
        self.assertIsNotNone(result.scaled_score)
        self.student.refresh_from_db()
        self.assertNotEqual(self.student.forecast_calibration, 0)

    def test_exam_without_part2_completes_immediately(self):
        self.exam.assignments.set([self.a1])
        result = self._run_part1()
        self.assertEqual(result.status, MockExamResult.Status.COMPLETED)

    def test_deadline_property(self):
        result = MockExamResult.objects.create(student=self.student, exam=self.exam)
        delta = result.deadline - result.started_at
        self.assertEqual(delta.total_seconds(), 235 * 60)
