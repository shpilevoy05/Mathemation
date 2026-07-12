"""Hint provider abstraction and stdlib HTTP LLM implementation.

Провайдер выбирается настройкой AI_MENTOR_PROVIDER (dotted path), поэтому
LLM-бэкенд (Claude API / YandexGPT / self-host) подключается без изменения
кода сервиса. Общие правила для любого провайдера: вести наводящими
вопросами, работать от проверенного разбора (reference_solution), никогда
не выдавать готовый ответ, помечать неуверенность.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

Transport = Callable[[str, dict[str, str], dict], dict]

UNCERTAINTY_NOTE = (
    "Я не уверен в этом шаге — если сомневаешься, отправь решение живому "
    "преподавателю на проверку."
)


class HintProvider(ABC):
    @abstractmethod
    def generate_hint(
        self, assignment, question: str, hint_number: int, *, session=None
    ) -> str | None:
        """Return a leading hint. Must never reveal the final answer."""


class MockHintProvider(HintProvider):
    """Deterministic canned hints for development and tests.

    Ведёт по шагам проверенного разбора, если он есть у задачи, — так же,
    как это будет делать LLM-провайдер через RAG.
    """

    TEMPLATES = {
        1: "Подсказка 1: перечитай условие задачи «{title}» и выпиши, что дано "
           "и что нужно найти. С какой формулы или свойства можно начать?",
        2: "Подсказка 2: раздели задачу «{title}» на шаги. Сделай первый шаг "
           "самостоятельно и проверь размерность/область допустимых значений.",
    }

    def generate_hint(
        self, assignment, question: str, hint_number: int, *, session=None
    ) -> str:
        steps = [
            s.strip() for s in (assignment.reference_solution or "").splitlines() if s.strip()
        ]
        if steps and hint_number <= len(steps):
            step = steps[hint_number - 1]
            return (
                f"Подсказка {hint_number}: подумай вот над чем — {step} "
                "Какой вывод из этого следует?"
            )
        template = self.TEMPLATES.get(hint_number, self.TEMPLATES[2])
        text = template.format(title=assignment.title)
        if not steps:
            # Нет проверенного разбора — наставник обязан пометить неуверенность.
            text = f"{text}\n\n{UNCERTAINTY_NOTE}"
        return text


class LLMHintProvider(HintProvider):
    """Generate grounded hints through an OpenAI-compatible or YandexGPT API."""

    SYSTEM_PROMPT = (
        "Ты — сократический наставник по профильной математике ЕГЭ. Веди ученика "
        "ТОЛЬКО наводящими вопросами: не более двух вопросов за ответ. НИКОГДА не "
        "называй финальный ответ и не решай задачу целиком. Опираться можно СТРОГО "
        "на приложенный эталонный разбор и теорию. Если эталонного разбора нет или "
        "ты не уверен, явно напиши «Я не уверен в этом шаге» и предложи спросить "
        "живого преподавателя. Отвечай кратко, 2–4 предложениями, по-русски. Любые "
        "вычисления показывай в виде равенств: их проверит символьный контроль."
    )

    def __init__(self, transport: Transport | None = None):
        self._transport = transport or self._urllib_transport

    def generate_hint(
        self, assignment, question: str, hint_number: int, *, session=None
    ) -> str | None:
        if not settings.AI_MENTOR_LLM_API_KEY:
            logger.warning("AI mentor LLM request skipped: API key is not configured")
            return None

        try:
            messages = self._build_messages(assignment, question, hint_number, session)
            headers, payload = self._build_request(messages)
            response = self._send_with_retry(headers, payload)
            text = self._parse_response(response)
            if not text:
                raise ValueError("empty LLM response")
            return text
        except Exception as exc:
            logger.warning(
                "AI mentor LLM request failed (%s)", type(exc).__name__
            )
            return None

    def _build_messages(self, assignment, question, hint_number: int, session) -> list[dict]:
        history = []
        if session is not None:
            recent = list(
                session.messages.filter(is_blocked=False).order_by("-created_at", "-id")[:6]
            )
            history = [
                {"role": message.role, "text": self._redact_answer(message.text, assignment)}
                for message in reversed(recent)
            ]

        reference_solution = self._redact_answer(
            assignment.reference_solution or "[эталонный разбор отсутствует]", assignment
        )
        statement = self._redact_answer(assignment.statement, assignment)
        student_question = self._redact_answer(question, assignment)
        hint_instruction = (
            "Первая подсказка должна быть мягче."
            if hint_number == 1
            else "Вторая подсказка должна быть конкретнее, но всё ещё без ответа."
        )
        history_text = "\n".join(
            f"- {item['role']}: {item['text']}" for item in history
        ) or "[история отсутствует]"
        user_context = (
            f"Условие задачи:\n{statement}\n\n"
            f"Эталонный разбор и теория:\n{reference_solution}\n\n"
            f"Номер подсказки: {hint_number}. {hint_instruction}\n\n"
            f"Вопрос ученика:\n{student_question}\n\n"
            f"Последние сообщения сессии:\n{history_text}"
        )
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_context},
        ]

    @staticmethod
    def _redact_answer(text: str, assignment) -> str:
        answer = assignment.correct_answer
        if not answer:
            return text
        return text.replace(answer, "[финальный ответ скрыт]")

    def _build_request(self, messages: list[dict]) -> tuple[dict[str, str], dict]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": self._authorization_header(),
        }
        if settings.AI_MENTOR_LLM_FORMAT == "openai":
            return headers, {
                "model": settings.AI_MENTOR_LLM_MODEL,
                "messages": messages,
                "max_tokens": settings.AI_MENTOR_LLM_MAX_TOKENS,
                "temperature": settings.AI_MENTOR_LLM_TEMPERATURE,
            }
        if settings.AI_MENTOR_LLM_FORMAT == "yandexgpt":
            model = settings.AI_MENTOR_LLM_MODEL
            model_uri = (
                model
                if model.startswith("gpt://")
                else f"gpt://{settings.AI_MENTOR_LLM_FOLDER_ID}/{model}"
            )
            return headers, {
                "modelUri": model_uri,
                "completionOptions": {
                    "stream": False,
                    "temperature": settings.AI_MENTOR_LLM_TEMPERATURE,
                    "maxTokens": settings.AI_MENTOR_LLM_MAX_TOKENS,
                },
                "messages": [
                    {"role": message["role"], "text": message["content"]}
                    for message in messages
                ],
            }
        raise ValueError("unsupported AI_MENTOR_LLM_FORMAT")

    def _authorization_header(self) -> str:
        prefix = "Bearer" if settings.AI_MENTOR_LLM_FORMAT == "openai" else "Api-Key"
        return f"{prefix} {settings.AI_MENTOR_LLM_API_KEY}"

    def _send_with_retry(self, headers: dict[str, str], payload: dict) -> dict:
        for attempt in range(2):
            try:
                return self._transport(settings.AI_MENTOR_LLM_BASE_URL, headers, payload)
            except HTTPError:
                raise
            except (URLError, TimeoutError):
                if attempt == 1:
                    raise
        raise RuntimeError("unreachable")

    def _urllib_transport(
        self, url: str, headers: dict[str, str], payload: dict
    ) -> dict:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=settings.AI_MENTOR_LLM_TIMEOUT_SECONDS) as response:
            if not 200 <= response.status < 300:
                raise ValueError(f"unexpected HTTP status {response.status}")
            return json.loads(response.read().decode("utf-8"))

    def _parse_response(self, response: dict) -> str:
        if settings.AI_MENTOR_LLM_FORMAT == "openai":
            return response["choices"][0]["message"]["content"].strip()
        return response["result"]["alternatives"][0]["message"]["text"].strip()


def get_provider() -> HintProvider:
    return import_string(settings.AI_MENTOR_PROVIDER)()
