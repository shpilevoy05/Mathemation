---
name: sympy-math-verifier
description: Use when parsing, normalizing, verifying, or displaying mathematical claims in tutor hints or when changing SymPy safety behavior.
---

# SymPy-проверка математики

Используй `apps/ai_mentor/guardrails.py` как единственную реализацию символьного гардрейла.
Проверяй подсказку до показа ученику.

## Контракт verdict

- Извлекай равенства и неравенства через `extract_math_claims`.
- Проверяй каждое утверждение через `verify_claim`.
- Интерпретируй `False` как ложное утверждение и блокируй весь текст.
- Интерпретируй `None` как `unverified`, а не как истину.
- Добавляй к видимому тексту пометку неуверенности при `unverified_claims`.
- Возвращай `GuardrailResult` из `check_hint`.
- Не показывай исходный текст при `passed=False`.

## Безопасность парсинга

- Используй `parse_expr`, но никогда не используй `eval`.
- Передавай безопасные `_SAFE_GLOBALS` с пустым `__builtins__`.
- Разрешай только белый список функций и односимвольные переменные.
- Отклоняй неизвестные многосимвольные идентификаторы.
- Отклоняй символы вне допустимого математического алфавита.
- Не добавляй функцию в whitelist без теста на выполнение произвольного кода.
- Нормализуй LaTeX-подобные конструкции до безопасного разбора.

## Отказоустойчивость

- Лови `Exception` вокруг SymPy-разбора и упрощения.
- Гардрейл никогда не должен падать от содержимого подсказки.
- Преобразуй неожиданное исключение в `None`/unverified.
- Не возвращай непроверенный текст без пометки.
- Не логируй сырой пользовательский текст в error monitoring.
- Ограничивай размер и сложность входа на API-границе.

## Интеграция

- Вызывай `check_hint` в `request_hint` до создания видимого mentor message.
- Сохраняй `failed_claims` и `unverified_claims` в `AiHintMessage`.
- При блоке сохраняй исходный текст как `is_blocked=True` только для аудита.
- Показывай ученику безопасный `GUARDRAIL_BLOCK_TEXT`.
- Пиши `hint_blocked_by_guardrail` через `apps/events/services.py`.

## Проверка

- Проверь true, false, unknown и malformed claims.
- Проверь отсутствие исключения на fuzz/произвольном Unicode.
- Проверь запрет опасных identifiers/functions.
- Проверь блок и пометку неуверенности end-to-end.
