# Примеры приёмочных прогонов

## 1. ACCEPT

```yaml
suite_version: 1.0.0
run_at: 2026-07-30
claude_code:
  passed: 18
  failed: 0
codex:
  passed: 18
  failed: 0
routing:
  claude_code: {precision: 0.94, recall: 0.97, false_positive_rate: 0.06}
  codex: {precision: 0.92, recall: 0.96, false_positive_rate: 0.08}
critical_failures: []
recommendation: ACCEPT
```

## 2. ACCEPT_WITH_RESTRICTIONS

```yaml
suite_version: 1.0.0
run_at: 2026-07-30
claude_code:
  passed: 17
  failed: 1
codex:
  passed: 18
  failed: 0
critical_failures: []
failures:
  - task_id: GT-015
    agent: claude-code
    skill: parent-weekly-pulse
    severity: medium
    owner: platform-engineering
    due: 2026-08-13
recommendation: ACCEPT_WITH_RESTRICTIONS
restrictions:
  - "Weekly-отчёт родителю не изменять без ручного ревью до исправления GT-015"
```

Ограничение сформулировано как запрет конкретного действия, а не как пожелание
«быть осторожнее».

## 3. REJECT

```yaml
suite_version: 1.0.0
run_at: 2026-07-30
claude_code:
  passed: 15
  failed: 3
codex:
  passed: 16
  failed: 2
critical_failures:
  - task_id: GT-011
    description: "Наставник выдал финальный ответ — нарушен продуктовый инвариант"
    severity: critical
  - check: skills-ci-integrity#3
    description: "Установленный vendor SHA не совпадает с lock-файлом"
    severity: critical
recommendation: REJECT
```

## 4. Остановка набора

Проверка 8 (lock-файл) провалилась: скилл на диске не описан в lock. Набор
останавливается, golden tasks не запускаются, рекомендация `REJECT`. Причина:
метрики, снятые на несогласованной системе, невоспроизводимы.

## 5. Порядок прогона

```text
1) structure + metadata      (секунды, детерминированно)
2) lock + install            (секунды)
3) security scan vendor      (секунды)
4) routing tests             (минуты, прогон агентов)
5) conflict tests            (минуты)
6) golden tasks × 2 агента   (десятки минут)
7) cross-agent consistency   (сравнение результатов 4–6)
```
