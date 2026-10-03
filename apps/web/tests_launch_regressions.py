"""Regressions for the commercial-readiness audit (synthetic data only)."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.knowledge.tests import make_node, make_student
from apps.practice.tests import make_assignment


class LaunchRegressions(TestCase):
    def setUp(self):
        self.student = make_student("launch-test")
        self.node = make_node()
        self.assignment = make_assignment(self.node)
        self.api = APIClient()
        self.api.force_authenticate(self.student.user)

    @override_settings(BILLING_ENFORCED=True, TRIAL_DAYS=0, FREE_FEATURES=[])
    def test_paid_lesson_and_draft_are_not_readable(self):
        from apps.billing.tests_access import give_subscription
        from apps.content.models import Lesson, TheoryBlock
        lesson = Lesson.objects.create(node=self.node, title="Draft")
        TheoryBlock.objects.create(lesson=lesson, body="private draft")
        url = f"/api/lessons/{lesson.pk}/"
        self.assertEqual(self.api.get(url).status_code, 403)
        give_subscription(self.student)
        self.assertEqual(self.api.get(url).status_code, 404)
        lesson.status = Lesson.Status.PUBLISHED
        lesson.save()
        self.assertEqual(self.api.get(url).status_code, 200)

    def test_same_correct_answer_does_not_farm_mastery_or_xp(self):
        from apps.gamification.models import GamificationProfile
        from apps.knowledge.models import SkillMastery
        url = f"/api/assignments/{self.assignment.pk}/attempt/"
        for _ in range(4):
            self.assertEqual(self.api.post(url, {"answer": "42"}).status_code, 201)
        self.assertEqual(SkillMastery.objects.get(student=self.student, node=self.node).mastery, 30)
        self.assertEqual(GamificationProfile.objects.get(student=self.student).xp, 10)

    def test_hint_and_answer_oracle_blocked_during_mock(self):
        from apps.mocks.models import MockExam
        from apps.mocks.services import start_mock
        exam = MockExam.objects.create(title="Control")
        exam.assignments.add(self.assignment)
        start_mock(self.student, exam)
        url = f"/api/assignments/{self.assignment.pk}"
        self.assertEqual(self.api.post(url + "/hint/", {"context": "lesson"}).status_code, 403)
        self.assertEqual(self.api.post(url + "/attempt/", {"answer": "42"}).status_code, 403)

    def test_unknown_math_is_blocked(self):
        from apps.ai_mentor.guardrails import check_hint
        self.assertFalse(check_hint("Для неизвестного ограничения x > 0.").passed)
        self.assertTrue(check_hint("С какого свойства можно начать?").passed)

    def test_explicit_answer_from_statement_is_blocked(self):
        from apps.ai_mentor.guardrails import contains_final_answer
        self.assertTrue(contains_final_answer("Ответ: 2.", "2", "Решите 2x = 4."))
        self.assertFalse(contains_final_answer("Начни с коэффициента 2 из условия.", "2", "Решите 2x = 4."))

    @override_settings(BILLING_ENFORCED=True, TRIAL_DAYS=0, FREE_FEATURES=[])
    def test_tariff_exclusion_is_enforced(self):
        from apps.billing.access import Feature, feature_access
        from apps.billing.tests_access import give_subscription
        subscription = give_subscription(self.student)
        subscription.tariff.features = {"ai_hints": False, "lessons": True}
        subscription.tariff.save()
        self.assertFalse(feature_access(self.student.user, Feature.AI_HINTS).allowed)
        self.assertTrue(feature_access(self.student.user, Feature.LESSONS).allowed)

    def test_refunding_renewal_preserves_first_paid_period(self):
        from apps.billing.tests_access import make_tariff
        from apps.billing.services import start_payment, confirm_payment, refund_payment
        tariff = make_tariff()
        first, _ = start_payment(self.student, tariff, self.student.user, "first")
        original_end = confirm_payment(first).ends_at
        second, _ = start_payment(self.student, tariff, self.student.user, "second")
        subscription = confirm_payment(second)
        refund_payment(second)
        subscription.refresh_from_db()
        self.assertTrue(subscription.is_active_now)
        self.assertEqual(subscription.ends_at, original_end)

    def test_forecast_is_frozen_before_mock(self):
        from apps.mocks.models import MockExam
        from apps.mocks.services import start_mock, submit_mock
        from apps.progress.services import expected_primary
        exam = MockExam.objects.create(title="Control")
        exam.assignments.add(self.assignment)
        before = expected_primary(self.student)
        result = start_mock(self.student, exam)
        submit_mock(result, {str(self.assignment.pk): "42"})
        observation = self.student.forecast_observations.get(mock_result=result)
        self.assertEqual(observation.predicted_primary, round(before, 2))

    def test_deadline_finalizes_saved_answers_and_ignores_late_edits(self):
        from apps.mocks.models import MockExam, MockExamResult
        from apps.mocks.services import start_mock
        exam = MockExam.objects.create(title="Control")
        exam.assignments.add(self.assignment)
        result = start_mock(self.student, exam)
        url = f"/api/mocks/results/{result.pk}"
        saved = self.api.post(url + "/draft/", {"answers": {str(self.assignment.pk): "42"}}, format="json")
        self.assertEqual(saved.status_code, 200)
        MockExamResult.objects.filter(pk=result.pk).update(started_at=timezone.now() - timedelta(hours=5))
        response = self.api.post(url + "/submit/", {"answers": {str(self.assignment.pk): "wrong"}}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["primary_score"], 1)
        self.assertTrue(response.data["time_expired"])
        again = self.api.post(url + "/submit/", {"answers": {}}, format="json")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(self.student.attempts.count(), 1)

    def test_league_uses_base_xp(self):
        from apps.gamification.leagues import enable_leagues
        from apps.gamification.services import award_xp
        membership = enable_leagues(self.student)
        with patch("apps.economy.services.boosted_xp", return_value=20):
            award_xp(self.student, 10, "test")
        membership.refresh_from_db()
        self.assertEqual(membership.xp, 10)

    def test_review_result_is_checked_by_server(self):
        from apps.practice.models import MistakeBacklogItem
        from apps.practice.services import submit_attempt
        from apps.practice.models import Attempt
        submit_attempt(self.student, self.assignment, "wrong", Attempt.Context.LESSON)
        item = MistakeBacklogItem.objects.get(student=self.student)
        review = item.reviews.order_by("due_date").first()
        review.due_date = timezone.localdate()
        review.save(update_fields=["due_date"])

        response = self.api.post(
            f"/api/reviews/{review.pk}/complete/",
            {"answer": "wrong", "success": True}, format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_correct"])
        item.refresh_from_db()
        self.assertEqual(item.error_count, 2)

    def test_dashboard_continue_targets_due_review(self):
        from apps.practice.models import Attempt
        from apps.practice.services import submit_attempt
        submit_attempt(self.student, self.assignment, "wrong", Attempt.Context.LESSON)
        review = self.student.mistake_backlog.get().reviews.first()
        review.due_date = timezone.localdate()
        review.save(update_fields=["due_date"])
        self.client.force_login(self.student.user)

        response = self.client.get("/")

        self.assertContains(response, f'/practice/backlog/#review-{review.pk}')
