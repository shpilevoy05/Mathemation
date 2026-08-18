# Примеры вывода навыков из эксплуатации

## 1. Объединение двух собственных скиллов

Метрики: 78% активаций совместные, области пересекаются.

```yaml
skill: skill-metadata-governance
action: merge
merged_into: skill-structure-validator
rules_migrated:
  - "схема обязательных полей"
  - "правила семантического версионирования"
  - "перечень критических skills и требование reviewers"
transition_until: 2026-10-28
routing_tests: pass
golden_tasks: pass
```

Объединение допустимо только если ни одно правило не потеряно. Список
перенесённых правил — обязательная часть отчёта.

## 2. Замена vendor-скилла собственным

```yaml
skill: vendor-generic-refactoring
action: replace
replacement: matemacia-architecture-guidelines
reason: "рекомендации противоречат модульному монолиту Математики"
transition_until: 2026-10-28
lock_updated: true
expected_skill_count: 12
```

Vendor-скилл удаляется одновременно из `skills.lock.yaml` и из установленных
каталогов. Удаление только из каталога даёт `FAIL` проверки 1 в CI.

## 3. Высокий false positive rate

```yaml
skill: vendor-llm-prompting
action: deprecate
false_positive_rate: 0.22
first_step: "сузить описание в форке"
outcome: "после сужения fpr 0.06 — deprecation отменена"
```

Deprecation — не единственный ответ на шум: сначала пробуется сужение области.

## 4. Редкий, но критичный скилл

```yaml
skill: release-rollback-plan
activations_last_quarter: 1
decision: keep
reason: "покрывает сценарий отката релиза; редкость не равна бесполезности"
```

## 5. Переходный период

```text
2026-07-30  status: deprecated, указана замена, ссылки обновлены
2026-08..10 обе версии доступны, замена выбирается в routing-тестах
2026-10-28  удаление, запись в CHANGELOG.md
```

Удаление в день deprecation ломает задачи, начатые до изменения.

## 6. Запись в changelog

```text
## 2026-10-28
- vendor-generic-refactoring удалён (deprecated с 2026-07-30). Замена:
  matemacia-architecture-guidelines. Перенесённые правила: запрет рефакторинга
  без тестов, требование ADR при смене границ модуля.
```
