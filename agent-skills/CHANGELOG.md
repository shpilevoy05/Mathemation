# Changelog системы навыков

## 2026-08-01

Governance-подсистема перенесена в систему навыков платформы: 12 скиллов лежат
плоско в `agent-skills/matemacia/` рядом с доменными, инструментарий — в
`scripts/` рядом с `install-skills.ps1` и `audit-skills.ps1`, реестр источников
остался единым (`skills.lock.yaml` в корне).

- Валидатор скиллов стал двухуровневым: базовые требования (frontmatter, имя,
  описание с условием применения, рабочие ссылки) — ко всем 50 скиллам,
  расширенные (структура каталога, разделы, кейсы активации, метаданные) —
  только к тем, кто объявил блок `metadata`.
- `skills.lock.yaml` получил `vendor_dir` и `accepted_findings`: базовую линию
  автоматического аудита. Срабатывание правила вне списка роняет CI, поэтому
  новый опасный паттерн в обновлении vendor не проходит молча.
- `scripts/skills-ci.ps1` выполняет 12 проверок целостности под раскладку
  ствола; `scripts/validate-skills.ps1` — валидацию скиллов.

Формат записи: `<skill> <версия> (<разряд>): что изменилось. Ревью: <кто>.`
Разряды — по `skill-metadata-governance`: `patch` (редакционно), `minor`
(новое правило или сценарий), `major` (изменение инварианта).

## 2026-07-30

Первая версия подсистемы `skills-governance` — 12 скиллов, инструментарий и
приёмочные наборы.

- skill-supply-chain-audit 1.0.0 (minor): аудит стороннего скилла до подключения
  в vendor, verdict PASS/REVIEW/BLOCK, обязательный формат отчёта.
  Ревью: platform-engineering, security.
- skill-conflict-resolution 1.0.0 (minor): иерархия приоритетов из пяти уровней,
  правило равной узости, обязательная запись о конфликте.
  Ревью: platform-engineering, product.
- skills-ci-integrity 1.0.0 (minor): 12 проверок целостности, FAIL блокирует
  merge и release. Ревью: platform-engineering, security.
- skill-vendor-update-governance 1.0.0 (minor): алгоритм обновления внешних
  навыков, маркер `.source.yaml`, решения ADOPT/HOLD/ROLLBACK.
  Ревью: platform-engineering.
- skill-routing-evaluation 1.0.0 (minor): positive/negative/priority кейсы,
  метрики precision, recall, false positive rate и целевые значения.
  Ревью: platform-engineering.
- skill-acceptance-suite 1.0.0 (minor): состав и порядок приёмочного набора,
  рекомендации ACCEPT / ACCEPT_WITH_RESTRICTIONS / REJECT.
  Ревью: platform-engineering.
- skill-golden-task-runner 1.0.0 (minor): единый формат прогона контрольных
  задач и фиксации результатов. Ревью: platform-engineering.
- skill-structure-validator 1.0.0 (minor): проверка структуры и содержания
  SKILL.md, коды выхода и режим -Strict. Ревью: platform-engineering.
- skill-metadata-governance 1.0.0 (minor): обязательные поля, семантическое
  версионирование, перечень критических скиллов.
  Ревью: platform-engineering.
- skill-cross-agent-consistency 1.0.0 (minor): допустимые и недопустимые
  расхождения Claude Code и Codex. Ревью: platform-engineering.
- skill-observability-and-usage-analytics 1.0.0 (minor): метрики использования,
  принципы приватности, ежемесячный отчёт. Ревью: platform-engineering.
- skill-deprecation-and-cleanup 1.0.0 (minor): процесс вывода навыков из
  эксплуатации с переходным периодом. Ревью: platform-engineering.

Инструментарий: `install-skills.ps1`, `validate-skill.ps1`, `validate-all.ps1`,
`ci-integrity.ps1`, `lib/supply_chain_scan.py`, `lib/routing_eval.py`,
`lib/minyaml.py` (парсер YAML-подмножества без внешних зависимостей).

Наборы: `tests/routing` (26 кейсов), `tests/conflicts` (7), `tests/golden-tasks`
(18 обязательных задач), `tests/cross-agent` (8).
