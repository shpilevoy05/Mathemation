# Примеры валидации структуры

## 1. valid

```yaml
skill: skill-supply-chain-audit
status: valid
errors: []
warnings: []
```

## 2. invalid: нет негативных кейсов

```yaml
skill: adaptive-planner
status: invalid
errors:
  - нет обязательного раздела «когда не активируется»
  - tests/negative-cases.yaml: не содержит ни одного кейса
warnings: []
```

Скилл без negative-кейсов активируется на всё подряд и портит false positive
rate всей системы.

## 3. invalid: путь конкретной машины

```yaml
skill: exam-config-versioning
status: invalid
errors:
  - "абсолютный путь конкретной машины в SKILL.md: 'D:\\\\'"
  - "битая ссылка: references/migration-notes.md"
warnings: []
```

Пути в примерах команд пишутся относительно корня репозитория:
`agent-skills\scripts\validate-all.ps1`.

## 4. warning: слишком широкое описание

```yaml
skill: knowledge-graph-governance
status: warning
errors: []
warnings:
  - "description слишком широкий: содержит 'всегда'"
  - "SKILL.md слишком объёмный (612 строк) — вынесите детали в references/"
```

Правка описания: вместо «всегда применять при работе с графом» —
«использовать при добавлении узла, изменении рёбер-зависимостей и при
версионировании графа; не использовать для правки текста теории в узле».

## 5. invalid: расхождение имени

```yaml
skill: mastery-bkt
status: invalid
errors:
  - "frontmatter.name='mastery-bkt-irt-fsrs' не совпадает с именем каталога 'mastery-bkt'"
  - "metadata.version не semver: '1.0'"
```

## 6. Использование в CI

```powershell
powershell -File agent-skills\scripts\validate-all.ps1 -Strict
if ($LASTEXITCODE -ne 0) { throw 'Структура скиллов невалидна' }
```

В CI `-Strict` обязателен: warning означает, что описание уже деградирует и
скоро даст провал routing-теста.
