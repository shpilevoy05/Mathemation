@'
# Mathemation development instructions

## Environment

- Native Windows only.
- Use PowerShell-compatible commands.
- Do not require WSL or Ubuntu.
- Do not use Linux-only paths or commands.
- Python virtual environment: `.venv`.
- Python executable: `.venv\Scripts\python.exe`.
- Use `pathlib` for filesystem paths.

## Product

Mathemation is a web platform for managed preparation for the Russian
profile mathematics Unified State Exam.

Core areas:

- diagnostic tests;
- knowledge map;
- personal study plans;
- daily and weekly plans;
- courses, tracks, lessons and assignments;
- attempts and automatic checking;
- mistake backlog and scheduled reviews;
- mock exams;
- score forecasts;
- parent reports;
- expert review;
- administrator interface.

## Architecture

- Preserve the existing modular monolith.
- Use Django and Django REST Framework.
- Django Admin is a required product interface.
- SQLite must remain available for local development and tests.
- PostgreSQL is the full local database.
- Do not create microservices.
- Do not introduce new dependencies without approval.
- Do not create duplicate models.
- Put business logic in service or domain modules.
- Keep business logic out of templates, views, serializers and admin classes.

## Security

- Never read, print or commit `.env`.
- Never commit tokens, credentials or real student data.
- Never run destructive database commands.
- Never force-push.
- Never commit or push unless explicitly requested.

## Required checks

Before completing implementation, run:

```powershell
.\scripts\test.ps1
## Система навыков агентов

- Собственные скиллы: `agent-skills/matemacia/<skill>/SKILL.md`; 12 governance-скиллов
  дополнительно несут `references/`, `scripts/validate.ps1` и `tests/`.
- Внешние скиллы: `agent-skills/vendor/<vendor>/<skill>/`, источники и их
  commit SHA — в `skills.lock.yaml` в корне.
- Установка и проверки:

```powershell
.\scripts\install-skills.ps1        # синхронизация в .claude\skills и .agents\skills
.\scripts\validate-skills.ps1 -Strict
.\scripts\skills-ci.ps1             # 12 проверок целостности; FAIL блокирует merge
```

- Базовая линия аудита vendor-скиллов живёт в `accepted_findings` реестра.
  Новое срабатывание правила роняет `skills-ci.ps1` — разберите находку и либо
  почините источник, либо добавьте правило в базовую линию с обоснованием.
- При конфликте инструкций действует приоритет: продуктовые инварианты
  Математики → собственный доменный скилл → собственный архитектурный скилл →
  vendor-скилл технологии → общая инженерная рекомендация.
