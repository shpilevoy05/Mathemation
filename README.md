# Матемация — MVP

Сервис управляемой подготовки к ЕГЭ по профильной математике: диагностика → карта
знаний → персональный план → уроки и задачи → отработка ошибок → пробники →
экспертная проверка второй части → прогресс и weekly-отчёт родителю.

## Стек
Django + DRF (модульный монолит), PostgreSQL (dev/tests — SQLite), Celery + Redis.

## Запуск
```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
# фоновые задачи (weekly-отчёты, просроченные повторы):
celery -A config worker -B
```
PostgreSQL включается переменными `POSTGRES_DB/USER/PASSWORD/HOST/PORT`.

## Структура
- `apps/accounts` — User, StudentProfile, ParentProfile
- `apps/knowledge` — карта знаний: TopicCluster, KnowledgeNode, KnowledgeDependency, SkillMastery (mastery 0–100)
- `apps/content` — Lesson, TheoryBlock, Assignment, AssignmentSkillTag
- `apps/diagnostics` — DiagnosticTest/Result, посев mastery, построение плана
- `apps/planning` — StudyPlan/Item, PlanChangeLog, plan builder (топология зависимостей + веса)
- `apps/practice` — Attempt, MistakeBacklogItem, ReviewSchedule (повторы 1/3/7/30 дней)
- `apps/mocks` — MockExam/Result, автопроверка 1-й части, адаптация плана
- `apps/expert_review` — ExpertReviewRequest: загрузка решения 2-й части, статусы, критерии
- `apps/progress` — ProgressSnapshot (прогноз), ParentReport (weekly pulse)
- `apps/ai_mentor` — HintProvider (mock, LLM позже), максимум 2 наводящие подсказки, лог
- `apps/web` — минимальный кабинет ученика

API: `/api/...` (session auth), кабинет: `/`, admin: `/admin/`.

## Тесты
```bash
python manage.py test apps
```
