---
name: critical-user-journeys
description: Use when adding features, release tests, integration tests, or regression coverage across student, parent, expert, and methodist end-to-end journeys.
---

# Критические пользовательские пути

Храни серверные эталонные сценарии в `apps/web/tests.py`.
Поддерживай внешние E2E-сценарии как дополнение, а не замену доменным тестам.

## Ученик

- Пройди цепочку: диагностика → карта знаний → урок → подсказка → пробник → часть 2.
- После диагностики проверь mastery, named trajectory, plan, snapshot и события.
- На карте проверь locked/available и индивидуальные `min_mastery`.
- В уроке проверь одну задачу, attempt event, mastery и backlog ошибки.
- Проверь подсказку без ответа, максимум два вопроса и SymPy-гардрейл.
- Проверь недоступность наставника на diagnostic/mock/review.
- После пробника проверь экспертный verdict части 2, calibration и адаптацию плана.

## Родитель

- Открой недельный `ParentReport` только для собственного ребёнка.
- Проверь факт недели, динамику, риски, слабые темы и следующий шаг.
- Проверь обязательное «при текущем темпе».
- Проверь только счётчик подсказок в summary.
- Открой переписку отдельным действием и исключи blocked messages.
- Проверь IDOR с ребёнком другой семьи.

## Эксперт

- Открой `/expert/`, очередь и SLA.
- Возьми submitted заявку части 2.
- Выставь criteria scores, comment, nodes и error tags через `finish_review`.
- Проверь reviewed и needs_resubmission ветви.
- Проверь попытку, mastery, backlog, mock completion и событие.
- Проверь доступ только роли эксперта.

## Методист

- Открой контентный dashboard и Django Admin.
- Создай/измени узел, ребро, урок, задачу, skill tags и reference solution.
- Проверь обнаружение дыр: нет решения, нет контента, нет задач у узла.
- Проверь запрет публикации непроверенного correct answer/criteria.
- Проверь граф на циклы и orphan nodes.
- Проверь доступ только роли методиста.

## Организация тестов

- Оставляй чистую математику в `apps/engine/tests/`.
- Оставляй доменные ветви в существующих `apps/practice/tests.py` и `apps/planning/tests.py`.
- Используй `apps/web/tests.py` для сквозных server-rendered путей и permissions.
- Не делай E2E единственным тестом бизнес-инварианта.

## Проверка

- Прогони четыре пути на чистой БД.
- Проверь события и object permissions на каждом переходе.
- Добавь регрессионный сценарий для каждого критического бага.
