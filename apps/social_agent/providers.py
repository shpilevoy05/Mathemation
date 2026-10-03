from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils.module_loading import import_string

from .models import LlmCall

logger = logging.getLogger(__name__)
Transport = Callable[[str, dict[str, str], dict], dict]


@dataclass(frozen=True)
class LlmResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""


class Provider(ABC):
    @abstractmethod
    def generate(self, messages: list[dict], *, purpose: str, post=None) -> LlmResult:
        raise NotImplementedError


class MockProvider(Provider):
    def generate(self, messages: list[dict], *, purpose: str, post=None) -> LlmResult:
        return LlmResult(text=f"mock:{purpose}", model="mock")


class LLMProvider(Provider):
    def __init__(self, transport: Transport | None = None):
        self._transport = transport or self._urllib_transport

    def generate(self, messages: list[dict], *, purpose: str, post=None) -> LlmResult:
        headers, payload = self._build_request(messages)
        try:
            response = self._transport(settings.SOCIAL_AGENT_LLM_BASE_URL, headers, payload)
            text, prompt_tokens, completion_tokens = self._parse_response(response)
            logger.debug("Social agent LLM request completed (%s)", settings.SOCIAL_AGENT_LLM_FORMAT)
            return LlmResult(text=text, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, model=settings.SOCIAL_AGENT_LLM_MODEL)
        except Exception as exc:
            logger.warning("Social agent LLM request failed (%s)", type(exc).__name__)
            raise

    def _build_request(self, messages: list[dict]) -> tuple[dict[str, str], dict]:
        llm_format = settings.SOCIAL_AGENT_LLM_FORMAT
        prefix = "Bearer" if llm_format == "openai" else "Api-Key"
        headers = {"Content-Type": "application/json", "Authorization": f"{prefix} {settings.SOCIAL_AGENT_LLM_API_KEY}"}
        if llm_format == "openai":
            return headers, {"model": settings.SOCIAL_AGENT_LLM_MODEL, "messages": messages, "max_tokens": settings.SOCIAL_AGENT_LLM_MAX_TOKENS, "temperature": settings.SOCIAL_AGENT_LLM_TEMPERATURE}
        if llm_format == "yandexgpt":
            model = settings.SOCIAL_AGENT_LLM_MODEL
            model_uri = model if model.startswith("gpt://") else f"gpt://{settings.SOCIAL_AGENT_LLM_FOLDER_ID}/{model}"
            return headers, {"modelUri": model_uri, "completionOptions": {"stream": False, "temperature": settings.SOCIAL_AGENT_LLM_TEMPERATURE, "maxTokens": settings.SOCIAL_AGENT_LLM_MAX_TOKENS}, "messages": [{"role": item["role"], "text": item["content"]} for item in messages]}
        raise ValueError("unsupported SOCIAL_AGENT_LLM_FORMAT")

    @staticmethod
    def _parse_response(response: dict) -> tuple[str, int, int]:
        if settings.SOCIAL_AGENT_LLM_FORMAT == "openai":
            usage = response.get("usage") or {}
            return response["choices"][0]["message"]["content"].strip(), int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        result = response["result"]
        usage = result.get("usage") or {}
        return result["alternatives"][0]["message"]["text"].strip(), int(usage.get("inputTextTokens", 0)), int(usage.get("completionTokens", 0))

    @staticmethod
    def _urllib_transport(url: str, headers: dict[str, str], payload: dict) -> dict:
        request = Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
        with urlopen(request, timeout=settings.SOCIAL_AGENT_LLM_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))


def get_provider() -> Provider:
    return import_string(settings.SOCIAL_AGENT_PROVIDER)()


def record_llm_call(result: LlmResult, *, purpose: str, post=None) -> LlmCall:
    prompt_tokens = max(result.prompt_tokens, 0)
    completion_tokens = max(result.completion_tokens, 0)
    input_cost = Decimal(prompt_tokens) * settings.SOCIAL_AGENT_COST_PER_1K_INPUT / Decimal(1000)
    output_cost = Decimal(completion_tokens) * settings.SOCIAL_AGENT_COST_PER_1K_OUTPUT / Decimal(1000)
    return LlmCall.objects.create(purpose=purpose, model=result.model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, cost=input_cost + output_cost, post=post)
