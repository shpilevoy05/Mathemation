from django.test import TestCase

from apps.knowledge.tests import make_node, make_student
from apps.practice.models import Attempt
from apps.practice.tests import make_assignment

from .services import HintNotAllowed, request_hint


class AiMentorTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.node = make_node()
        self.assignment = make_assignment(self.node)

    def test_max_two_hints_then_escalation(self):
        r1 = request_hint(self.student, self.assignment, "не понимаю", Attempt.Context.LESSON)
        r2 = request_hint(self.student, self.assignment, "всё ещё", Attempt.Context.LESSON)
        r3 = request_hint(self.student, self.assignment, "help", Attempt.Context.LESSON)
        self.assertFalse(r1["escalated"])
        self.assertFalse(r2["escalated"])
        self.assertTrue(r3["escalated"])
        self.assertEqual(r3["session"].hints_used, 2)

    def test_hint_never_contains_answer(self):
        r = request_hint(self.student, self.assignment, "подскажи", Attempt.Context.LESSON)
        self.assertNotIn(self.assignment.correct_answer, r["text"])

    def test_disabled_on_mock_diagnostic_review(self):
        for context in (Attempt.Context.MOCK, Attempt.Context.DIAGNOSTIC, Attempt.Context.REVIEW):
            with self.assertRaises(HintNotAllowed):
                request_hint(self.student, self.assignment, "hint?", context)

    def test_usage_logged_for_parent(self):
        request_hint(self.student, self.assignment, "вопрос", Attempt.Context.LESSON)
        session = self.student.hint_sessions.get()
        self.assertEqual(session.hints_used, 1)
        self.assertEqual(session.node, self.node)
        self.assertEqual(session.messages.count(), 2)  # student + mentor
