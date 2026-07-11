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