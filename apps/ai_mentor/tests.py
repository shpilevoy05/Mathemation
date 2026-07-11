from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.content.models import Assignment
from apps.events.models import Event
from apps.knowledge.tests import make_node, make_student
from apps.practice.models import Attempt
from apps.practice.tests import make_assignment

from .guardrails import check_hint, extract_math_claims, verify_claim
from .models import AiHintMessage
from .services import GUARDRAIL_BLOCK_TEXT, HintNotAllowed, request_hint


class FalseClaimProvider:
    def generate_hint(self, assignment, question: str, hint_number: int) -> str:
        return "Проверь вычисление: 2 + 2 = 5."


class FinalAnswerProvider:
    def generate_hint(self, assignment, question: str, hint_number: int) -> str:
        return f"Попробуй получить число {assignment.correct_answer}."


class StatementNumberProvider:
    def generate_hint(self, assignment, question: str, hint_number: int) -> str:
        return "Начни с коэффициента 2 из условия."


class GuardrailUnitTests(TestCase):
    def test_valid_claims(self):
        for claim in (
            "2^3 = 8",
            "3/4 + 5/8 = 11/8",
            "sin(pi/6) = 1/2",
            "x² − 4 = (x−2)(x+2)",
            "log2(32) = 5",
        ):
            with self.subTest(claim=claim):
                self.assertIs(verify_claim(claim), True)

    def test_invalid_claims(self):
        for claim in ("2 + 2 = 5", "(a+b)² = a²+b²"):
            with self.subTest(claim=claim):
                self.assertIs(verify_claim(claim), False)

    def test_unparseable_claim_is_unverified(self):
        self.assertIsNone(verify_claim("unknown_function(2) = 3"))

    def test_new_symbol_definition_is_not_extracted(self):
        self.assertEqual(extract_math_claims("пусть t = x+1"), [])

    def test_unverified_claim_does_not_block(self):
        result = check_hint("Для неизвестного ограничения x > 0.")
        self.assertTrue(result.passed)
        self.assertEqual(result.unverified_claims, ["x > 0"])

    def test_malformed_provider_text_never_breaks_guardrail(self):
        malformed_hints = (
            "().__class__ = 0",
            "((( = )))",
            "a!!! = ///",
            "😀 кириллица слева = кириллица справа 🧮",
        )

        for hint in malformed_hints:
            with self.subTest(hint=hint):
                result = check_hint(hint)
                self.assertTrue(result.passed)
                self.assertEqual(result.failed_claims, [])


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

    @override_settings(AI_MENTOR_PROVIDER="apps.ai_mentor.tests.FalseClaimProvider")
    def test_false_claim_is_blocked_by_api_and_audited(self):
        client = APIClient()
        client.force_authenticate(user=self.student.user)

        response = client.post(
            f"/api/assignments/{self.assignment.id}/hint/",
            {"question": "Подскажи", "context": Attempt.Context.LESSON},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["hint"], GUARDRAIL_BLOCK_TEXT)
        self.assertNotContains(response, "2 + 2 = 5")
        self.assertTrue(response.data["escalated_to_expert"])
        blocked = AiHintMessage.objects.get(is_blocked=True)
        self.assertIn("2 + 2 = 5", blocked.text)
        self.assertEqual(blocked.failed_claims, ["2 + 2 = 5"])
        self.assertTrue(
            Event.objects.filter(
                event_type=Event.Type.HINT_BLOCKED_BY_GUARDRAIL
            ).exists()
        )

    @override_settings(AI_MENTOR_PROVIDER="apps.ai_mentor.tests.FinalAnswerProvider")
    def test_final_part1_answer_is_blocked(self):
        client = APIClient()
        client.force_authenticate(user=self.student.user)

        response = client.post(
            f"/api/assignments/{self.assignment.id}/hint/",
            {"question": "Подскажи"},
            format="json",
        )

        self.assertEqual(response.data["hint"], GUARDRAIL_BLOCK_TEXT)
        self.assertEqual(
            AiHintMessage.objects.get(is_blocked=True).failed_claims,
            ["final_answer"],
        )

    @override_settings(AI_MENTOR_PROVIDER="apps.ai_mentor.tests.StatementNumberProvider")
    def test_number_from_statement_is_not_blocked(self):
        self.assignment.correct_answer = "2"
        self.assignment.statement = "Решите уравнение 2x + 1 = 5."
        self.assignment.save(update_fields=["correct_answer", "statement"])
        client = APIClient()
        client.force_authenticate(user=self.student.user)

        response = client.post(
            f"/api/assignments/{self.assignment.id}/hint/",
            {"question": "Подскажи"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("коэффициента 2", response.data["hint"])
        self.assertFalse(AiHintMessage.objects.filter(is_blocked=True).exists())


class DemoMentorGuardrailTests(TestCase):
    def test_seed_demo_reference_solution_hint_passes_guardrail(self):
        call_command("seed_demo", verbosity=0)
        user = User.objects.get(username="student")
        assignment = Assignment.objects.get(
            title="Тригонометрическое уравнение (задача 13)"
        )
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.post(
            f"/api/assignments/{assignment.id}/hint/",
            {"question": "С чего начать?", "context": Attempt.Context.LESSON},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data["hint"], GUARDRAIL_BLOCK_TEXT)
        self.assertFalse(response.data["escalated_to_expert"])
