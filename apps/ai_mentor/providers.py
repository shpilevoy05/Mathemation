"""Hint provider abstraction.

Провайдер выбирается настройкой AI_MENTOR_PROVIDER (dotted path), поэтому
LLM-бэкенд (Claude API / YandexGPT / self-host) подключается без изменения
кода сервиса. Общие правила для любого провайдера: вести наводящими
вопросами, работать от проверенного разбора (reference_solution), никогда
не выдавать готовый ответ, помечать неуверенность.
"""
from abc import ABC, abstractmethod

from django.conf import settings
from django.utils.module_loading import import_string

UNCERTAINTY_NOTE = (
    "Я не уверен в этом шаге — если сомневаешься, отправь решение живому "
    "преподавателю на проверку."
)


class HintProvider(ABC):
    @abstractmethod
    def generate_hint(self, assignment, question: str, hint_number: int) -> str:
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

    def generate_hint(self, assignment, question: str, hint_number: int) -> str:
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


def get_provider() -> HintProvider:
    return import_string(settings.AI_MENTOR_PROVIDER)()
