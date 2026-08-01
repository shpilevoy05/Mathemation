---
name: skill-metadata-governance
description: Единые метаданные, владельцы, версии и статусы для собственных навыков Математики, включая семантическое версионирование и усиленное ревью критических скиллов. Использовать при создании скилла, изменении его правил или области применения, смене владельца и статуса, а также при просроченном ревью.
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
    - ci
  reviewers:
    - platform-engineering
  replaces: []
  depends_on: []
  conflicts_with: []
---

# skill-metadata-governance

## Назначение

Сделать так, чтобы у каждого скилла был владелец, понятная версия, статус
жизненного цикла и дата ревью. Без этого невозможно ни отследить регрессию, ни
понять, кто отвечает за правило, ни вывести скилл из эксплуатации.

## Когда активируется

- создаётся новый скилл и заполняются метаданные;
- меняется правило, сценарий или инвариант внутри скилла — нужно решить,
  какой разряд версии поднять;
- меняется владелец, `status` или `criticality`;
- истёк `review_cycle_days`;
- добавляется зависимость или известный конфликт между скиллами;
- CI сообщает о провале проверки 9 или 10.

## Когда не активируется

- проверяется наличие разделов и файлов — это `skill-structure-validator`;
- нужно решить конфликт инструкций — это `skill-conflict-resolution`;
- выводится скилл из эксплуатации — это `skill-deprecation-and-cleanup`
  (этот скилл только фиксирует `status: deprecated`);
- метаданные vendor-скилла: они не редактируются, а фиксируются в lock-файле;
- прикладные изменения в `apps/`.

## Входные данные

- текущий frontmatter скилла;
- суть изменения (редакционное, новое правило, изменение инварианта);
- список ревьюеров для критических скиллов;
- дата изменения.

## Обязательные поля

```yaml
name: skill-name
owner: team-or-role
version: 1.0.0
status: draft | active | deprecated | archived
criticality: low | medium | high | critical
last_reviewed: YYYY-MM-DD
review_cycle_days: 90
applies_to:
  - backend
  - frontend
replaces: []
depends_on: []
conflicts_with: []
```

В скиллах Математики `name` и `description` живут на верхнем уровне
frontmatter (их читает агент), остальные поля — в блоке `metadata`.
Критические скиллы дополнительно заполняют `reviewers`.

## Семантическое версионирование

- `patch` — редакционное уточнение без изменения поведения;
- `minor` — новое правило или новый сценарий;
- `major` — изменение продуктового, архитектурного или алгоритмического
  инварианта.

`major` требует записи в `agent-skills/CHANGELOG.md` и прогона
`skill-acceptance-suite`: изменение инварианта меняет ожидания golden tasks.

## Критические skills

Усиленное ревью обязательно для:

- `matemacia-product-invariants`;
- `knowledge-graph-governance`;
- `exam-config-versioning`;
- `mastery-bkt-irt-fsrs`;
- `score-forecast-and-ceiling`;
- `adaptive-planner`;
- `socratic-tutor-rag`;
- `expert-review-workflow`;
- `event-contracts-analytics`;
- security- и privacy-skills.

Для них требуется минимум два ревьюера, запись в `CHANGELOG.md` и
непустое `metadata.reviewers`. Разбор случаев — в
[references/examples.md](references/examples.md).

## Ожидаемый результат

Обновлённый frontmatter, соответствующий схеме, плюс строка в
`CHANGELOG.md` вида:

```text
## 2026-07-30
- skill-conflict-resolution 1.1.0 (minor): добавлено правило равной узости. Ревью: platform-engineering, product.
```

## Запрещено

- поднимать `patch` при изменении инварианта;
- менять правила критического скилла без ревьюеров и записи в `CHANGELOG.md`;
- держать `status: active` у скилла с просроченным ревью дольше одного цикла;
- дублировать одну область двумя активными скиллами без явного приоритета;
- заполнять `owner` значением «team» без конкретной роли или команды;
- редактировать метаданные vendor-скиллов вместо записи в lock-файле.

## Связанные скиллы

- `skill-structure-validator` — проверяет схему метаданных технически;
- `skills-ci-integrity` — блокирует merge при провале проверок 9 и 10;
- `skill-deprecation-and-cleanup` — использует `status` и `replaces`;
- `skill-conflict-resolution` — использует `conflicts_with`;
- `skill-acceptance-suite` — обязателен после `major`.

## Приоритет при конфликтах

1. Продуктовые и security-инварианты Математики.
2. `skill-conflict-resolution`.
3. Этот скилл в части полей, версий и статусов.
4. `skill-structure-validator` в части оформления.
5. Vendor-соглашения о версионировании.

## Критерии приёмки

- все обязательные поля заполнены и проходят схему;
- версия изменена согласно разряду изменения;
- `last_reviewed` обновлён при каждом содержательном изменении;
- критические скиллы имеют `reviewers` и запись в `CHANGELOG.md`;
- `depends_on` и `conflicts_with` ссылаются на существующие скиллы;
- версия в `skills.lock.yaml` совпадает с версией в `SKILL.md`.

## Проверка

```powershell
powershell -File agent-skills\scripts\validate-all.ps1 -Strict
powershell -File agent-skills\scripts\ci-integrity.ps1
```
