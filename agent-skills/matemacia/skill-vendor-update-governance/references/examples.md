# Примеры обновления внешних навыков

## 1. ADOPT

```yaml
repository: acme/postgres-best-practices
from_sha: 1d3f5a7c9e0b2d4f6a8c0e2b4d6f8a0c2e4b6d80
to_sha: 7c2e9b4a1f6d0c3e8b5a2d7f4c1e6b9a3d0f5c28
audit_verdict: PASS
changes:
  instructions:
    - SKILL.md: добавлен раздел про партиционирование
  scripts: []
  permissions: []
routing_delta:
  precision: +0.01
  false_positive_rate: 0.00
golden_tasks:
  regressions: []
decision: ADOPT
```

## 2. HOLD

```yaml
repository: acme/db-helpers
from_sha: 9b2e7d41a6c05f38e1d7b4a09c2f6e5d8a3b1c07
to_sha: 4a8f2c6e0b9d3f7a1c5e8b2d6f0a4c8e2b6d0f94
audit_verdict: REVIEW
changes:
  instructions:
    - SKILL.md: описание расширено до «любых операций с данными»
  scripts:
    - scripts/collect.py: добавлено чтение переменных окружения
  permissions:
    - allowed-tools: добавлен Bash
decision: HOLD
reason: "Расширение области применения ломает negative-кейсы; чтение окружения не обосновано"
```

Расширенное описание — не только вопрос безопасности: оно повышает false
positive rate всей системы.

## 3. ROLLBACK

```yaml
repository: acme/frontend-components
from_sha: 5e1a9c3f7b2d0e6a4c8f1b5d9e3a7c0f2b6d4a81
to_sha: 0f4b8d2a6c1e5b9d3f7a2c6e0b4d8f1a5c9e3b70
audit_verdict: PASS
golden_tasks:
  regressions:
    - task_id: GT-014
      severity: high
      description: "Mobile flow: компонент нарушает дизайн-систему Математики"
decision: ROLLBACK
reason: "Регрессия high; возврат к предыдущему SHA, задача на форк компонента"
```

## 4. Маркер установленной версии

`agent-skills/vendor/acme-postgres-best-practices/.source.yaml`:

```yaml
repository: acme/postgres-best-practices
commit_sha: 7c2e9b4a1f6d0c3e8b5a2d7f4c1e6b9a3d0f5c28
installed_at: 2026-07-30
audit_report: reports/audits/acme-postgres-best-practices-7c2e9b4.yaml
```

Проверка 3 в CI сравнивает этот файл с lock-файлом.

## 5. Восстановление после git clone

```powershell
powershell -File agent-skills\scripts\install-skills.ps1
powershell -File agent-skills\scripts\ci-integrity.ps1
```

Каталоги установки не коммитятся: их состав целиком определяется lock-файлом.

## 6. Обновление нескольких источников

Каждый источник обновляется отдельным коммитом с отдельным отчётом. Иначе при
регрессии невозможно определить, какое из обновлений её вызвало.
