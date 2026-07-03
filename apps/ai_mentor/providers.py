"""Hint provider abstraction. No real LLM in MVP — mock only.

TODO: add an LLM-backed provider (Claude API) behind the same interface once
keys/infrastructure are available; select via settings.
"""
from abc import ABC, abstractmethod


class HintProvider(ABC):
    @abstractmethod
    def generate_hint(self, assignment, question: str, hint_number: int) -> str:
        """Return a leading hint. Must never reveal the final answer."""


class MockHintProvider(HintProvider):
    """Deterministic canned hints for development and tests."""

    TEMPLATES = {
        1: "Подсказка 1: перечитай условие задачи «{title}» и выпиши, что дано "
           "и что нужно найти. С какой формулы или свойства можно начать?",
        2: "Подсказка 2: раздели задачу «{title}» на шаги. Сделай первый шаг "
           "самостоятельно и проверь размерность/область допустимых значений.",
    }

    def generate_hint(self, assignment, question: str, hint_number: int) -> str:
        template = self.TEMPLATES.get(hint_number, self.TEMPLATES[2])
        return template.format(title=assignment.title)


def get_provider() -> HintProvider:
    return MockHintProvider()
