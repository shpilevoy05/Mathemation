from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.arena.models import Match, MatchParticipant, MatchQuestion
from apps.content.models import DailyChallenge
from apps.content.services import challenge_state
from apps.knowledge.tests import make_node, make_student
from apps.mocks.models import MockExam, MockExamResult

from .tests import make_assignment


class AssessmentPracticeAccessTests(TestCase):
    def setUp(self):
        self.student = make_student("assessment-access")
        self.assignment = make_assignment(make_node("assessment-access-node"), answer="7")
        self.client = APIClient()
        self.client.force_authenticate(self.student.user)
        self.attempt_url = f"/api/assignments/{self.assignment.pk}/attempt/"

    def test_expired_mock_finalizes_draft_and_daily_challenge_opens(self):
        DailyChallenge.objects.create(
            date=timezone.localdate(), assignment=self.assignment
        )
        exam = MockExam.objects.create(title="Пробник ЕГЭ №1", duration_minutes=60)
        exam.assignments.add(self.assignment)
        result = MockExamResult.objects.create(
            student=self.student,
            exam=exam,
            draft_answers={str(self.assignment.pk): "7"},
        )
        MockExamResult.objects.filter(pk=result.pk).update(
            started_at=timezone.now() - timedelta(hours=2)
        )

        response = self.client.post(self.attempt_url, {"answer": "7"}, format="json")

        self.assertEqual(response.status_code, 201)
        result.refresh_from_db()
        self.assertEqual(result.status, MockExamResult.Status.COMPLETED)
        saved_attempt = result.attempts.get(assignment=self.assignment)
        self.assertEqual(saved_attempt.submitted_answer, "7")
        self.assertTrue(saved_attempt.is_correct)
        self.assertTrue(challenge_state(self.student)["solved"])

    def test_running_mock_blocks_and_names_mock(self):
        exam = MockExam.objects.create(title="Пробник ЕГЭ №1", duration_minutes=60)
        exam.assignments.add(self.assignment)
        result = MockExamResult.objects.create(student=self.student, exam=exam)

        response = self.client.post(self.attempt_url, {"answer": "7"}, format="json")

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["code"], "assessment_in_progress")
        self.assertEqual(payload["kind"], "mock")
        self.assertEqual(payload["title"], exam.title)
        self.assertEqual(payload["url"], f"/mocks/run/{result.pk}/")
        self.assertIn("Пробник ЕГЭ №1", payload["detail"])
        self.assertIn("Завершите его", payload["detail"])

        hint_response = self.client.post(
            f"/api/assignments/{self.assignment.pk}/hint/",
            {"question": "С чего начать?", "context": "lesson"},
            format="json",
        )
        self.assertEqual(hint_response.status_code, 403)
        self.assertEqual(hint_response.json()["code"], "assessment_in_progress")
        self.assertEqual(hint_response.json()["kind"], "mock")

    def test_stale_arena_lobby_does_not_block(self):
        match = Match.objects.create(
            created_by=self.student, status=Match.Status.LOBBY
        )
        MatchParticipant.objects.create(match=match, student=self.student)
        MatchQuestion.objects.create(
            match=match, order=1, assignment=self.assignment
        )
        Match.objects.filter(pk=match.pk).update(
            created_at=timezone.now() - timedelta(minutes=6)
        )

        response = self.client.post(self.attempt_url, {"answer": "7"}, format="json")

        self.assertEqual(response.status_code, 201)
        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.CANCELLED)

    def test_live_arena_match_returns_structured_block(self):
        match = Match.objects.create(
            created_by=self.student, status=Match.Status.ACTIVE
        )
        MatchParticipant.objects.create(match=match, student=self.student)
        MatchQuestion.objects.create(
            match=match, order=1, assignment=self.assignment
        )

        response = self.client.post(self.attempt_url, {"answer": "7"}, format="json")

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["kind"], "arena")
        self.assertEqual(payload["url"], f"/arena/match/{match.pk}/")
