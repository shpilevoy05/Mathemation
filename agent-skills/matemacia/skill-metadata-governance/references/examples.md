# Примеры работы с метаданными

## 1. patch

Уточнена формулировка примера, поведение не изменилось.

```yaml
version: 1.0.1
last_reviewed: 2026-08-05
```

CHANGELOG:

```text
- skill-structure-validator 1.0.1 (patch): уточнён пример негативного кейса.
```

## 2. minor

Добавлено новое правило: при равном уровне иерархии выигрывает более узкий
скилл.

```yaml
version: 1.1.0
last_reviewed: 2026-08-05
```

Требуется прогон routing- и conflict-тестов: новое правило меняет ожидания
priority-кейсов.

## 3. major

Изменён алгоритмический инвариант: mastery обновляется не BKT, а гибридной
схемой BKT + FSRS.

```yaml
version: 2.0.0
status: active
criticality: critical
last_reviewed: 2026-08-05
reviewers:
  - ml
  - product
replaces:
  - mastery-bkt
```

Обязательно: запись в `CHANGELOG.md`, прогон `skill-acceptance-suite`,
обновление golden tasks, зависящих от инварианта.

## 4. Просроченное ревью

```yaml
last_reviewed: 2026-01-10
review_cycle_days: 90
```

Валидатор выдаёт warning «ревью просрочено: срок 2026-04-10». Действие: либо
подтвердить актуальность и обновить дату, либо перевести в `deprecated`.
Оставлять `active` с просрочкой более одного цикла нельзя.

## 5. Владелец

Плохо: `owner: team`. Хорошо: `owner: platform-engineering` или
`owner: ml-lead`. Владелец — тот, кто отвечает на вопрос «почему это правило
такое» и принимает решение о его изменении.

## 6. Зависимости и конфликты

```yaml
depends_on:
  - skill-structure-validator
  - skill-routing-evaluation
conflicts_with:
  - vendor-llm-prompting
```

`conflicts_with` заполняется после первого разобранного конфликта: это ссылка
на известную пару, а не предсказание.

## 7. Соответствие lock-файлу

```yaml
# skills.lock.yaml
- name: skill-conflict-resolution
  version: 1.1.0
  criticality: critical
```

Расхождение версии в lock и в `SKILL.md` — `FAIL` проверки 3 в CI.
