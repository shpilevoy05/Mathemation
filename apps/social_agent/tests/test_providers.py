from decimal import Decimal

from django.test import TestCase, override_settings

from apps.social_agent.models import LlmCall
from apps.social_agent.providers import LLMProvider, LlmResult, MockProvider, record_llm_call


class ProviderTests(TestCase):
    def test_mock_is_deterministic(self):
        provider = MockProvider()
        first = provider.generate([], purpose="draft")
        second = provider.generate([{"role": "user", "content": "ignored"}], purpose="draft")
        self.assertEqual(first, second)
        self.assertEqual(first.text, "mock:draft")

    @override_settings(SOCIAL_AGENT_LLM_FORMAT="openai", SOCIAL_AGENT_LLM_API_KEY="secret-key", SOCIAL_AGENT_LLM_MODEL="model")
    def test_openai_payload_and_key_not_logged(self):
        captured = {}

        def transport(url, headers, payload):
            captured.update(url=url, headers=headers, payload=payload)
            return {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 2, "completion_tokens": 3}}

        with self.assertLogs("apps.social_agent.providers", level="DEBUG") as logs:
            result = LLMProvider(transport).generate([{"role": "user", "content": "hello"}], purpose="draft")
        self.assertEqual(result.text, "ok")
        self.assertEqual(captured["payload"]["messages"][0]["content"], "hello")
        self.assertNotIn("secret-key", "\n".join(logs.output))

    @override_settings(SOCIAL_AGENT_LLM_FORMAT="yandexgpt", SOCIAL_AGENT_LLM_API_KEY="secret-key", SOCIAL_AGENT_LLM_MODEL="model", SOCIAL_AGENT_LLM_FOLDER_ID="folder")
    def test_yandex_payload_and_key_not_logged(self):
        captured = {}

        def transport(url, headers, payload):
            captured["payload"] = payload
            return {"result": {"alternatives": [{"message": {"text": "да"}}], "usage": {"inputTextTokens": 4, "completionTokens": 5}}}

        with self.assertLogs("apps.social_agent.providers", level="DEBUG") as logs:
            result = LLMProvider(transport).generate([{"role": "user", "content": "текст"}], purpose="check")
        self.assertEqual(result.prompt_tokens, 4)
        self.assertEqual(captured["payload"]["modelUri"], "gpt://folder/model")
        self.assertEqual(captured["payload"]["messages"][0]["text"], "текст")
        self.assertNotIn("secret-key", "\n".join(logs.output))

    @override_settings(SOCIAL_AGENT_COST_PER_1K_INPUT=Decimal("2"), SOCIAL_AGENT_COST_PER_1K_OUTPUT=Decimal("4"))
    def test_record_llm_call_computes_cost(self):
        call = record_llm_call(LlmResult("ok", 100, 50, "model"), purpose=LlmCall.Purpose.DRAFT)
        self.assertEqual(call.cost, Decimal("0.400000"))

    @override_settings(SOCIAL_AGENT_COST_PER_1K_INPUT=Decimal("2"), SOCIAL_AGENT_COST_PER_1K_OUTPUT=Decimal("4"))
    def test_record_llm_call_clamps_tokens_before_cost(self):
        call = record_llm_call(LlmResult("ok", -100, -50, "model"), purpose=LlmCall.Purpose.DRAFT)
        self.assertEqual(call.prompt_tokens, 0)
        self.assertEqual(call.completion_tokens, 0)
        self.assertEqual(call.cost, Decimal("0.000000"))
