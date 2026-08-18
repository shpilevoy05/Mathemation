---
name: expert-review-workflow
description: Use when implementing or reviewing part-2 submission, expert queue, SLA, verdict, resubmission, scoring criteria, or error-tag workflows.
---

# Экспертная проверка части 2

Работай в границах `apps/expert_review/`.
Считай `finish_review` в `apps/expert_review/services.py` единственной точкой финального вердикта.
Считай эксперта финальным арбитром; ИИ может только предразмечать.

## Приём работы

- Создавай заявку через `submit_solution`, связывая ученика, задачу и файл.
- Связывай заявку с `Attempt` и `MockExamResult`, когда они существуют.
- Храни скан в РФ-периметре; не отправляй ПДн в нероссийское хранилище.
- Проверяй, что задача относится к части 2.
- Не выставляй окончательный балл при загрузке файла.

## Очередь и SLA

- Используй `sla_hours` из `apps/expert_review/models.py`.
- По умолчанию бери `EXPERT_REVIEW_SLA_HOURS` из `config/settings.py`.
- Показывай дедлайн, просрочку и приоритет в `/expert/` через `apps/web/services.py`.
- Не скрывай просроченные заявки сортировкой или фильтром.
- Не подменяй SLA временем выполнения ИИ-пайплайна.

## Вердикт

- Завершай проверку только вызовом `finish_review`.
- Передавай баллы по критериям, комментарий, связанные узлы и `error_tags`.
- Рассчитывай итог и потерянные баллы из экспертных критериев.
- Проставляй reviewer и `reviewed_at`.
- Используй `needs_resubmission=True` для повторной проверки.
- Не считай заявку окончательно закрытой при статусе `needs_resubmission`.
- После вердикта обновляй связанную попытку, mastery, backlog и итог пробника через сервисы.

## Типизация ошибок

- Преобразуй `error_tags` в типы `MistakeBacklogItem.ErrorType`.
- Привязывай тег к конкретному узлу, когда эксперт указал `node_id`.
- Используй `apply_error_tags`; не оставляй экспертную разметку только в JSON.
- Возвращай ошибку в интервальные повторы через `apps/practice/services.py`.
- Логируй `expert_review_completed` через `apps/events/services.py`.

## Проверка

- Проверь запрет финального ИИ-вердикта.
- Проверь расчёт SLA и обработку просрочки.
- Проверь оба исхода: reviewed и needs_resubmission.
- Проверь перенос criteria scores и error tags в попытку/backlog.
- Проверь права эксперта и IDOR для `/expert/` и API.
