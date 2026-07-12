import json
from unittest.mock import patch
from urllib.error import URLError

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
from .models import AiHintMessage, AiHintSession
from .providers import LLMHintProvider, UNCERTAINTY_NOTE
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


class LLMHintProviderTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.node = make_node()
        self.assignment = make_assignment(self.node, answer="314159")
        self.assignment.statement = "Найдите значение выражения."
        self.assignment.reference_solution = (
            "Используй определение. В конце получится 314159."
        )
        self.assignment.save(update_fields=["statement", "reference_solution"])
        self.session = AiHintSession.objects.create(
            student=self.student, assignment=self.assignment, node=self.node
        )
        AiHintMessage.objects.create(
            session=self.session, role=AiHintMessage.Role.STUDENT, text="С чего начать?"
        )
        AiHintMessage.objects.create(
            session=self.session,
            role=AiHintMessage.Role.MENTOR,
            text="Этот текст заблокирован",
            is_blocked=True,
        )
        AiHintMessage.objects.create(
            session=self.session,
            role=AiHintMessage.Role.MENTOR,
            text="Какое определение подходит?",
        )

    @override_settings(
        AI_MENTOR_LLM_FORMAT="openai",
        AI_MENTOR_LLM_BASE_URL="https://llm.example/v1/chat/completions",
        AI_MENTOR_LLM_API_KEY="test-key",
        AI_MENTOR_LLM_MODEL="test-model",
        AI_MENTOR_LLM_MAX_TOKENS=400,
        AI_MENTOR_LLM_TEMPERATURE=0.3,
    )
    def test_openai_payload_is_grounded_and_excludes_answer_and_blocked_history(self):
        captured = {}

        def transport(url, headers, payload):
            captured.update(url=url, headers=headers, payload=payload)
            return {"choices": [{"message": {"content": "С чего стоит начать?"}}]}

        text = LLMHintProvider(transport=transport).generate_hint(
            self.assignment, "Помоги", 1, session=self.session
        )

        self.assertEqual(text, "С чего стоит начать?")
        self.assertEqual(captured["url"], "https://llm.example/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-key")
        payload = captured["payload"]
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["max_tokens"], 400)
        self.assertEqual(payload["temperature"], 0.3)
        self.assertIn("НИКОГДА", payload["messages"][0]["content"])
        self.assertIn("не более двух", payload["messages"][0]["content"])
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(self.assignment.correct_answer, serialized)
        self.assertIn("С чего начать?", serialized)
        self.assertIn("Какое определение подходит?", serialized)
        self.assertNotIn("Этот текст заблокирован", serialized)

    @override_settings(
        AI_MENTOR_LLM_FORMAT="yandexgpt",
        AI_MENTOR_LLM_BASE_URL="https://llm.api.cloud.yandex.net/completion",
        AI_MENTOR_LLM_API_KEY="test-key",
        AI_MENTOR_LLM_MODEL="yandexgpt-lite",
        AI_MENTOR_LLM_FOLDER_ID="folder-id",
        AI_MENTOR_LLM_MAX_TOKENS=321,
        AI_MENTOR_LLM_TEMPERATURE=0.2,
    )
    def test_yandexgpt_payload_and_response(self):
        captured = {}

        def transport(url, headers, payload):
            captured.update(headers=headers, payload=payload)
            return {
                "result": {
                    "alternatives": [{"message": {"text": "Что известно из условия?"}}]
                }
            }

        text = LLMHintProvider(transport=transport).generate_hint(
            self.assignment, "Подскажи", 2, session=self.session
        )

        self.assertEqual(text, "Что известно из условия?")
        self.assertEqual(captured["headers"]["Authorization"], "Api-Key test-key")
        self.assertEqual(captured["payload"]["modelUri"], "gpt://folder-id/yandexgpt-lite")
        self.assertEqual(
            captured["payload"]["completionOptions"],
            {"stream": False, "temperature": 0.2, "maxTokens": 321},
        )
        self.assertIn("text", captured["payload"]["messages"][0])

    @override_settings(
        AI_MENTOR_LLM_FORMAT="yandexgpt",
        AI_MENTOR_LLM_API_KEY="test-key",
        AI_MENTOR_LLM_MODEL="gpt://folder/custom-model",
    )
    def test_yandexgpt_full_model_uri_is_preserved(self):
        captured = {}

        def transport(url, headers, payload):
            captured["payload"] = payload
            return {
                "result": {"alternatives": [{"message": {"text": "С чего начнёшь?"}}]}
            }

        LLMHintProvider(transport=transport).generate_hint(
            self.assignment, "Подскажи", 1, session=self.session
        )

        self.assertEqual(captured["payload"]["modelUri"], "gpt://folder/custom-model")


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
        event = Event.objects.get(event_type=Event.Type.HINT_ISSUED)
        self.assertEqual(event.payload["provider"], "mock")

    @override_settings(
        AI_MENTOR_LLM_FORMAT="openai",
        AI_MENTOR_LLM_BASE_URL="https://llm.example/v1/chat/completions",
        AI_MENTOR_LLM_API_KEY="test-key",
        AI_MENTOR_LLM_MODEL="test-model",
    )
    def test_successful_llm_hint_records_provider(self):
        def transport(url, headers, payload):
            return {"choices": [{"message": {"content": "С чего стоит начать?"}}]}

        provider = LLMHintProvider(transport=transport)
        with patch("apps.ai_mentor.services.get_provider", return_value=provider):
            result = request_hint(
                self.student, self.assignment, "Подскажи", Attempt.Context.LESSON
            )

        self.assertEqual(result["text"], "С чего стоит начать?")
        event = Event.objects.get(event_type=Event.Type.HINT_ISSUED)
        self.assertEqual(event.payload["provider"], "llm")

    @override_settings(
        AI_MENTOR_LLM_FORMAT="openai",
        AI_MENTOR_LLM_BASE_URL="https://llm.example/v1/chat/completions",
        AI_MENTOR_LLM_API_KEY="test-key",
        AI_MENTOR_LLM_MODEL="test-model",
    )
    def test_false_llm_claim_uses_the_same_guardrail_path(self):
        def transport(url, headers, payload):
            return {
                "choices": [{"message": {"content": "Значит 2 + 2 = 5."}}]
            }

        provider = LLMHintProvider(transport=transport)
        with patch("apps.ai_mentor.services.get_provider", return_value=provider):
            result = request_hint(
                self.student, self.assignment, "Подскажи", Attempt.Context.LESSON
            )

        self.assertEqual(result["text"], GUARDRAIL_BLOCK_TEXT)
        self.assertTrue(result["escalated"])
        self.assertTrue(
            Event.objects.filter(
                event_type=Event.Type.HINT_BLOCKED_BY_GUARDRAIL
            ).exists()
        )

    @override_settings(
        AI_MENTOR_LLM_FORMAT="openai",
        AI_MENTOR_LLM_BASE_URL="https://llm.example/v1/chat/completions",
        AI_MENTOR_LLM_API_KEY="test-key",
        AI_MENTOR_LLM_MODEL="test-model",
    )
    def test_network_error_retries_then_falls_back_to_mock(self):
        attempts = []

        def transport(url, headers, payload):
            attempts.append(url)
            raise URLError("offline")

        provider = LLMHintProvider(transport=transport)
        with patch("apps.ai_mentor.services.get_provider", return_value=provider):
            result = request_hint(
                self.student, self.assignment, "Подскажи", Attempt.Context.LESSON
            )

        self.assertEqual(len(attempts), 2)
        self.assertIn(UNCERTAINTY_NOTE, result["text"])
        event = Event.objects.get(event_type=Event.Type.HINT_ISSUED)
        self.assertEqual(event.payload["provider"], "mock_fallback")

    @override_settings(
        AI_MENTOR_LLM_FORMAT="openai",
        AI_MENTOR_LLM_API_KEY="",
        AI_MENTOR_LLM_MODEL="test-model",
    )
    def test_missing_api_key_falls_back_without_transport_call(self):
        calls = []

        def transport(url, headers, payload):
            calls.append(url)
            return {"choices": [{"message": {"content": "Не должно вызываться"}}]}

        provider = LLMHintProvider(transport=transport)
        with patch("apps.ai_mentor.services.get_provider", return_value=provider):
            result = request_hint(
                self.student, self.assignment, "Подскажи", Attempt.Context.LESSON
            )

        self.assertEqual(calls, [])
        self.assertIn(UNCERTAINTY_NOTE, result["text"])
        event = Event.objects.get(event_type=Event.Type.HINT_ISSUED)
        self.assertEqual(event.payload["provider"], "mock_fallback")

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
