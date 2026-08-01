# Примеры прогонов CI

## 1. PASS без vendor-скиллов

```text
PASS  1. vendor-скиллы связаны с lock-файлом
PASS  2. у каждого источника полный commit SHA и аудит PASS
PASS  3. фактическая версия соответствует lock-файлу
SKIP  4. повторный supply-chain аудит не даёт BLOCK
        - vendor-скиллы не подключены
PASS  5. число установленных навыков = expected_skill_count
PASS  6. .claude/skills и .agents/skills идентичны
PASS  7. в vendor нет незакоммиченных изменений
PASS  8. каждый собственный скилл имеет обязательную структуру
PASS  9. метаданные проходят schema validation
PASS 10. изменения critical skills прошли усиленное ревью
PASS 11. routing tests пройдены
PASS 12. golden tasks без критических регрессий

result: PASS
```

## 2. FAIL: короткий SHA

```text
FAIL  2. у каждого источника полный commit SHA и аудит PASS
        - acme/db-helpers: commit_sha не полный 40-символьный SHA
```

Исправление: получить полный SHA, переустановить, обновить lock. Ветка в поле
`ref` остаётся справочной.

## 3. FAIL: расхождение каталогов установки

```text
FAIL  6. .claude/skills и .agents/skills идентичны
        - skill-deprecation-and-cleanup есть только в .claude/skills
```

Причина почти всегда одна: скилл добавили руками в один каталог. Исправление —
`install-skills.ps1`, а не копирование второй руки.

## 4. FAIL: ручная правка vendor

```text
FAIL  7. в vendor нет незакоммиченных изменений
        - M agent-skills/vendor/acme-db-helpers/skills/db-helpers/SKILL.md
```

Исправление: откатить правку и вести её через форк или patch-файл
(`skill-vendor-update-governance`).

## 5. FAIL: критический скилл без ревью

```text
FAIL 10. изменения critical skills прошли усиленное ревью
        - skill-conflict-resolution 1.1.0 не зафиксирован в CHANGELOG.md
```

## 6. Интеграция в pull request

```yaml
# .github/workflows/skills.yml (фрагмент)
- name: install skills
  run: powershell -ExecutionPolicy Bypass -File agent-skills/scripts/install-skills.ps1
- name: integrity
  run: powershell -ExecutionPolicy Bypass -File agent-skills/scripts/ci-integrity.ps1
```

Вывод скрипта вставляется в комментарий PR целиком: он короткий и содержит
причины провала.
