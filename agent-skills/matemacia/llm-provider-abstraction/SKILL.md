---
name: llm-provider-abstraction
description: Use when adding, replacing, configuring, testing, or failing over Mathemation LLM hint providers and their network transports.
---

# Абстракция LLM-провайдера

Сохраняй провайдера за `HintProvider` ABC в `apps/ai_mentor/providers.py`.
Не меняй доменный сервис при смене LLM.

## Контракт

- Реализуй `generate_hint(assignment, question, hint_number, session=None)`.
- Возвращай текст сократической подсказки или `None` при безопасном отказе.
- Не возвращай HTTP response, provider-specific JSON или исключение наружу.
- Собирай provider payload внутри адаптера.
- Парси provider response внутри адаптера.
- Поддерживай OpenAI-compatible и YandexGPT форматы без ветвления в сервисе.

## Выбор и fallback

- Выбирай класс через `AI_MENTOR_PROVIDER` в `config/settings.py`.
- Загружай dotted path через `get_provider`.
- Используй `MockHintProvider` для разработки, тестов и безопасного fallback.
- При сетевом сбое возвращай `None`, затем fallback с пометкой неуверенности.
- Не показывай сырой текст provider error ученику.
- Не обходи гардрейлы для mock/fallback.

## Секреты и логи

- Читай API key только из env через settings.
- Не читай и не печатай `.env`.
- Не хардкодь ключ, folder id, endpoint или токен.
- Не логируй Authorization header, prompt, student text или сырой response.
- Логируй только тип исключения и безопасный provider name.
- Не включай секреты в exception message или event payload.

## Сеть

- Устанавливай явный timeout.
- Повторяй только временные `URLError`/`TimeoutError` с ограничением.
- Не повторяй HTTP auth/validation ошибки как временные.
- Подменяй transport callable в unit tests.
- Не добавляй тяжёлый orchestration framework без одобрения.

## Независимость сервиса

- Оставляй `request_hint` ответственным за availability, лимит, гардрейлы и события.
- Оставляй provider ответственным только за генерацию grounded hint.
- Не переносить `correct_answer` в provider config.
- Не менять API contract при смене модели.

## Проверка

- Прогони один и тот же service test с mock и LLM adapter.
- Проверь timeout, retry, malformed response и fallback.
- Проверь отсутствие секретов в логах.
- Проверь обязательные output guardrails для каждого провайдера.
