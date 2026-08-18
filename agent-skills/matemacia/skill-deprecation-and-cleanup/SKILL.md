---
name: skill-deprecation-and-cleanup
description: Контролируемое удаление, объединение или замена устаревших навыков с переходным периодом, обновлением зависимостей и записью в changelog. Использовать когда скилл не используется, полностью дублируется другим, его источник не поддерживается, рекомендации противоречат архитектуре или он даёт много ложных активаций.
metadata:
  owner: platform-engineering
  version: 1.0.0
  status: active
  criticality: medium
  last_reviewed: 2026-07-30
  review_cycle_days: 90
  applies_to:
    - claude-code
    - codex
  reviewers:
    - platform-engineering
  replaces: []
  depends_on:
    - skill-metadata-governance
    - skill-routing-evaluation
  conflicts_with: []
---

# skill-deprecation-and-cleanup

## Назначение

Убирать лишние навыки так, чтобы не потерять правило, которое в них жило.
Система из 115 навыков деградирует не от нехватки скиллов, а от дубликатов и
шумных активаций — но резкое удаление ломает задачи, которые на скилл
опирались.

## Когда активируется

- скилл не используется (по данным
  `skill-observability-and-usage-analytics`);
- скилл полностью дублируется другим;
- источник больше не поддерживается;
- рекомендации скилла противоречат текущей архитектуре;
- скилл создаёт высокий уровень false positives;
- несколько скиллов объединяются в один.

## Когда не активируется

- скилл нужно поправить, а не убрать — это `skill-structure-validator` и
  `skill-metadata-governance`;
- нужно разово разрешить конфликт двух скиллов — это
  `skill-conflict-resolution`;
- обновляется версия внешнего скилла — это
  `skill-vendor-update-governance`;
- скилл редко используется, но покрывает критичный сценарий (откат релиза,
  инцидент) — редкость не равна бесполезности;
- нужен только отчёт об использовании.

## Входные данные

- имя скилла и его метаданные (`status`, `criticality`, `depends_on`);
- метрики использования за период;
- список скиллов, ссылающихся на него (`depends_on`, `replaces`,
  `conflicts_with` и тексты `SKILL.md`);
- скилл-замена, если он есть.

## Процесс

1. Перевести скилл в `deprecated` (`skill-metadata-governance`).
2. Указать замену в `replaces` у нового скилла и в тексте устаревшего.
3. Обновить зависимости и ссылки во всех скиллах, которые на него ссылаются.
4. Запустить routing tests: замена должна выбираться там, где раньше
   выбирался устаревший скилл.
5. Проверить golden tasks: правила устаревшего скилла не должны пропасть.
6. Удалить скилл только после переходного периода (не менее одного цикла
   ревью, по умолчанию 90 дней).
7. Зафиксировать изменение в `agent-skills/CHANGELOG.md`.

Разбор случаев — в [references/examples.md](references/examples.md).

## Ожидаемый результат

```yaml
skill: vendor-generic-refactoring
action: deprecate | merge | replace | remove
replacement: matemacia-architecture-guidelines
transition_until: 2026-10-28
dependencies_updated:
  - skill-acceptance-suite
routing_tests: pass
golden_tasks: pass
rules_migrated:
  - "запрет рефакторинга без тестов перенесён в архитектурный скилл"
changelog_entry: "2026-07-30 vendor-generic-refactoring deprecated → matemacia-architecture-guidelines"
```

## Запрещено

- удалять критический skill без анализа зависимостей;
- удалять vendor-skill только из установленного каталога, оставляя его в lock;
- сохранять две активные версии с одинаковой областью без явного приоритета;
- удалять скилл в тот же день, когда он переведён в `deprecated`;
- терять правила устаревшего скилла при объединении;
- удалять скилл, чьи ссылки остались в других `SKILL.md`.

## Связанные скиллы

- `skill-observability-and-usage-analytics` — поставляет кандидатов;
- `skill-metadata-governance` — меняет `status` и `replaces`;
- `skill-routing-evaluation` — подтверждает, что замена выбирается;
- `skill-vendor-update-governance` — синхронно правит `skills.lock.yaml`;
- `skills-ci-integrity` — ловит рассинхрон lock и установленного набора.

## Приоритет при конфликтах

1. Продуктовые, security- и юридические инварианты Математики (правило не
   исчезает вместе со скиллом).
2. `skill-conflict-resolution`.
3. Этот скилл (порядок вывода из эксплуатации).
4. `skill-observability-and-usage-analytics` (метрика предлагает, но не решает).
5. Vendor-рекомендации.

## Критерии приёмки

- скилл прошёл через `deprecated` с указанной датой окончания перехода;
- замена указана явно либо обосновано её отсутствие;
- все ссылки и зависимости обновлены;
- routing tests показывают выбор замены;
- golden tasks не потеряли ни одного правила;
- запись в `CHANGELOG.md` создана;
- для vendor-скилла lock-файл и установленный набор изменены одновременно.

## Проверка

```powershell
powershell -File agent-skills\scripts\validate-all.ps1
powershell -File agent-skills\scripts\ci-integrity.ps1
python agent-skills\scripts\lib\routing_eval.py --cases agent-skills\tests\routing --check-coverage
```
