"""Общая библиотека проверок системы навыков Математики.

Используется скиллами `skill-structure-validator`, `skill-metadata-governance`,
`skills-ci-integrity`, `skill-cross-agent-consistency`.
"""

from __future__ import annotations

import datetime as _dt
import os
import re

import minyaml

__all__ = [
    "REQUIRED_FILES",
    "REQUIRED_SECTIONS",
    "STATUSES",
    "CRITICALITIES",
    "CRITICAL_SKILLS",
    "repo_root",
    "agent_skills_root",
    "load_lock",
    "iter_own_skills",
    "installed_skills",
    "validate_skill",
    "validate_lock",
]

REQUIRED_FILES = (
    "SKILL.md",
    "references/examples.md",
    "references/anti-patterns.md",
    "tests/positive-cases.yaml",
    "tests/negative-cases.yaml",
)

# Хотя бы один из вариантов валидатора.
VALIDATOR_FILES = ("scripts/validate.ps1", "scripts/validate.py")

REQUIRED_SECTIONS = (
    "назначение",
    "когда активируется",
    "когда не активируется",
    "входные данные",
    "ожидаемый результат",
    "запрещено",
    "связанные скиллы",
    "приоритет при конфликтах",
    "критерии приёмки",
)

STATUSES = ("draft", "active", "deprecated", "archived")
CRITICALITIES = ("low", "medium", "high", "critical")

# Скиллы, изменение которых требует усиленного ревью (документ, §3.8).
CRITICAL_SKILLS = (
    "matemacia-product-invariants",
    "knowledge-graph-governance",
    "exam-config-versioning",
    "mastery-bkt-irt-fsrs",
    "score-forecast-and-ceiling",
    "adaptive-planner",
    "socratic-tutor-rag",
    "expert-review-workflow",
    "event-contracts-analytics",
)

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HEADING_RE = re.compile(r"^#{2,4}\s+(.+?)\s*$", re.MULTILINE)
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_ABS_PATH_RE = re.compile(r"(?<![\w`])(?:[A-Za-z]:[\\/]|/Users/|/home/|\\\\[A-Za-z0-9_.-]+\\)")
_OVERBROAD = ("любой задаче", "всегда", "во всех случаях", "any task", "always use")


def repo_root() -> str:
    """Корень репозитория: библиотека лежит в scripts/lib."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def agent_skills_root() -> str:
    return os.path.join(repo_root(), "agent-skills")


def load_lock(path: str | None = None) -> dict:
    # Реестр внешних скиллов лежит в корне репозитория.
    path = path or os.path.join(repo_root(), "skills.lock.yaml")
    lock = minyaml.load(path)
    if not isinstance(lock, dict):
        raise ValueError("skills.lock.yaml должен быть отображением")
    return lock


def iter_own_skills(root: str | None = None):
    """Пути ко всем собственным скиллам (каталогам, содержащим SKILL.md)."""
    base = os.path.join(root or agent_skills_root(), "matemacia")
    found = []
    for current, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        if "SKILL.md" in files:
            found.append(current)
    return sorted(found)


def installed_skills(directory: str):
    """Имена скиллов, установленных в каталог (`.claude/skills` и подобные)."""
    if not os.path.isdir(directory):
        return []
    names = []
    for entry in sorted(os.listdir(directory)):
        if os.path.isfile(os.path.join(directory, entry, "SKILL.md")):
            names.append(entry)
    return names


def _headings(body: str):
    return [match.group(1).strip().lower().rstrip(":") for match in _HEADING_RE.finditer(body)]


def _section_body(body: str, title: str) -> str:
    pattern = re.compile(
        r"^#{2,4}\s+" + re.escape(title) + r"\s*$(.*?)(?=^#{2,4}\s+|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(body)
    return match.group(1) if match else ""


def _check_metadata(name: str, meta: dict, errors: list, warnings: list) -> None:
    if meta.get("name") != name:
        errors.append("frontmatter.name=%r не совпадает с именем каталога %r" % (meta.get("name"), name))
    if not _KEBAB_RE.match(name):
        errors.append("имя скилла не в kebab-case: %r" % name)

    description = meta.get("description")
    if not isinstance(description, str) or len(description) < 40:
        errors.append("description отсутствует или короче 40 символов")
    else:
        if len(description) > 1024:
            errors.append("description длиннее 1024 символов (%d)" % len(description))
        lowered = description.lower()
        if not any(word in lowered for word in ("использовать", "активируется", "when", "use ")):
            warnings.append("в description нет условия применения — агент будет выбирать скилл наугад")
        for phrase in _OVERBROAD:
            if phrase in lowered:
                warnings.append("description слишком широкий: содержит %r" % phrase)

    block = meta.get("metadata")
    if not isinstance(block, dict):
        # Доменные скиллы ствола живут с коротким frontmatter; расширенные
        # требования предъявляются только тем, кто объявил metadata.
        return

    for field in ("owner", "version", "status", "criticality", "last_reviewed", "applies_to"):
        if block.get(field) in (None, "", []):
            errors.append("metadata.%s не заполнено" % field)

    version = block.get("version")
    if version is not None and not _SEMVER_RE.match(str(version)):
        errors.append("metadata.version не semver: %r" % version)
    if block.get("status") not in (None,) + STATUSES:
        errors.append("metadata.status=%r вне %s" % (block.get("status"), list(STATUSES)))
    if block.get("criticality") not in (None,) + CRITICALITIES:
        errors.append("metadata.criticality=%r вне %s" % (block.get("criticality"), list(CRITICALITIES)))

    reviewed = block.get("last_reviewed")
    if reviewed is not None:
        if not _DATE_RE.match(str(reviewed)):
            errors.append("metadata.last_reviewed не в формате YYYY-MM-DD: %r" % reviewed)
        else:
            cycle = block.get("review_cycle_days")
            if not isinstance(cycle, int):
                warnings.append("metadata.review_cycle_days не задан числом")
            else:
                due = _dt.date.fromisoformat(str(reviewed)) + _dt.timedelta(days=cycle)
                if due < _dt.date.today():
                    warnings.append("ревью просрочено: срок %s" % due.isoformat())

    applies_to = block.get("applies_to")
    if applies_to is not None and not isinstance(applies_to, list):
        errors.append("metadata.applies_to должен быть списком")

    for field in ("replaces", "depends_on", "conflicts_with"):
        value = block.get(field)
        if value is not None and not isinstance(value, list):
            errors.append("metadata.%s должен быть списком" % field)


def _check_tests(path: str, errors: list, warnings: list) -> None:
    for kind in ("positive", "negative"):
        rel = "tests/%s-cases.yaml" % kind
        full = os.path.join(path, rel)
        if not os.path.isfile(full):
            continue
        try:
            data = minyaml.load(full)
        except minyaml.YamlError as exc:
            errors.append("%s не разбирается: %s" % (rel, exc))
            continue
        cases = data.get("cases") if isinstance(data, dict) else data
        if not isinstance(cases, list) or not cases:
            errors.append("%s не содержит ни одного кейса" % rel)
            continue
        for index, case in enumerate(cases, 1):
            if not isinstance(case, dict) or not case.get("id"):
                errors.append("%s: кейс #%d без поля id" % (rel, index))
            elif not case.get("expected") and not case.get("must_not_activate") and not case.get("expect"):
                warnings.append("%s: кейс %s без ожидаемого результата" % (rel, case.get("id")))


def _check_links(path: str, body: str, errors: list) -> None:
    for match in _LINK_RE.finditer(body):
        target = match.group(1).split("#", 1)[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        if os.path.isabs(target) or _ABS_PATH_RE.search(target):
            errors.append("абсолютный путь в ссылке: %s" % target)
            continue
        candidates = [
            os.path.join(path, target),
            os.path.join(repo_root(), target),
        ]
        if not any(os.path.exists(candidate) for candidate in candidates):
            errors.append("битая ссылка: %s" % target)


def validate_skill(path: str) -> dict:
    """Проверить один скилл. Возвращает dict со status/errors/warnings.

    Проверка двухуровневая. Базовый уровень обязателен для всех скиллов
    репозитория: frontmatter, имя, описание с условием применения, рабочие
    ссылки, отсутствие путей конкретной машины.

    Расширенный уровень (структура каталога, обязательные разделы, кейсы
    активации, метаданные владельца и версии) требуется только от скиллов,
    объявивших блок `metadata`. Так governance-скиллы держат высокую планку,
    а доменные скиллы не переписываются ради формы — их усиление идёт
    отдельной работой, а не проверкой, которая ломает CI в день добавления.
    """
    path = os.path.abspath(path)
    name = os.path.basename(path)
    errors: list[str] = []
    warnings: list[str] = []

    skill_md = os.path.join(path, "SKILL.md")
    if not os.path.isfile(skill_md):
        errors.append("отсутствует SKILL.md")
        return {"skill": name, "status": "invalid", "errors": errors, "warnings": warnings}

    try:
        meta, body = minyaml.frontmatter(skill_md)
    except minyaml.YamlError as exc:
        errors.append("frontmatter не разбирается: %s" % exc)
        meta, body = None, ""

    if meta is None:
        errors.append("SKILL.md без YAML-frontmatter")
        meta = {}
    _check_metadata(name, meta, errors, warnings)

    for match in _ABS_PATH_RE.finditer(body):
        errors.append("абсолютный путь конкретной машины в SKILL.md: %r" % match.group(0))
    _check_links(path, body, errors)

    if isinstance(meta.get("metadata"), dict):
        for rel in REQUIRED_FILES:
            if not os.path.isfile(os.path.join(path, rel)):
                errors.append("отсутствует обязательный файл %s" % rel)
        if not any(os.path.isfile(os.path.join(path, rel)) for rel in VALIDATOR_FILES):
            errors.append("отсутствует scripts/validate.ps1 или scripts/validate.py")

        headings = _headings(body)
        for section in REQUIRED_SECTIONS:
            if section not in headings:
                errors.append("нет обязательного раздела «%s»" % section)
            elif not _section_body(body, section).strip():
                errors.append("раздел «%s» пуст" % section)

        negative = _section_body(body, "когда не активируется")
        if negative.strip() and not re.search(r"^\s*[-*\d]", negative, re.MULTILINE):
            warnings.append("negative activation cases не оформлены списком")

        line_count = body.count("\n") + 1
        if line_count > 400:
            warnings.append(
                "SKILL.md слишком объёмный (%d строк) — вынесите детали в references/"
                % line_count
            )

        _check_tests(path, errors, warnings)
        for rel in ("references/examples.md", "references/anti-patterns.md"):
            full = os.path.join(path, rel)
            if os.path.isfile(full):
                with open(full, "r", encoding="utf-8") as handle:
                    if len(handle.read().strip()) < 200:
                        warnings.append("%s почти пуст" % rel)

    status = "invalid" if errors else ("warning" if warnings else "valid")
    return {"skill": name, "status": status, "errors": errors, "warnings": warnings}


def validate_lock(lock: dict | None = None) -> dict:
    """Проверки lock-файла: SHA, аудит, соответствие каталогу."""
    lock = lock or load_lock()
    errors: list[str] = []
    warnings: list[str] = []

    own = lock.get("own_skills") or []
    listed = {entry.get("name"): entry for entry in own if isinstance(entry, dict)}
    on_disk = {os.path.basename(path): path for path in iter_own_skills()}

    for name in sorted(set(on_disk) - set(listed)):
        errors.append("скилл %s есть на диске, но не описан в skills.lock.yaml" % name)
    for name in sorted(set(listed) - set(on_disk)):
        errors.append("скилл %s описан в lock, но отсутствует на диске" % name)

    for name, entry in sorted(listed.items()):
        path = on_disk.get(name)
        if not path:
            continue
        meta, _ = minyaml.frontmatter(os.path.join(path, "SKILL.md"))
        block = (meta or {}).get("metadata") or {}
        if str(entry.get("version")) != str(block.get("version")):
            errors.append(
                "версия %s расходится: lock=%s, SKILL.md=%s"
                % (name, entry.get("version"), block.get("version"))
            )
        if entry.get("criticality") != block.get("criticality"):
            warnings.append(
                "criticality %s расходится: lock=%s, SKILL.md=%s"
                % (name, entry.get("criticality"), block.get("criticality"))
            )
        declared = entry.get("path")
        if declared and os.path.normpath(os.path.join(repo_root(), declared)) != os.path.normpath(path):
            errors.append("path в lock для %s не совпадает с фактическим" % name)

    for source in lock.get("sources") or []:
        if not isinstance(source, dict):
            errors.append("запись sources не является отображением")
            continue
        repository = source.get("repository", "<без repository>")
        sha = str(source.get("commit_sha") or "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            errors.append("%s: commit_sha не полный 40-символьный SHA" % repository)
        audit = source.get("audit") or {}
        if audit.get("verdict") != "PASS":
            errors.append("%s: verdict аудита не PASS (%r)" % (repository, audit.get("verdict")))
        if not _DATE_RE.match(str(audit.get("reviewed_at") or "")):
            errors.append("%s: audit.reviewed_at не в формате YYYY-MM-DD" % repository)
        if not source.get("skills"):
            errors.append("%s: не перечислены устанавливаемые скиллы" % repository)

    expected = lock.get("expected_skill_count")
    vendor_count = sum(len(source.get("skills") or []) for source in (lock.get("sources") or []) if isinstance(source, dict))
    actual = len(listed) + vendor_count
    if isinstance(expected, int) and expected != actual:
        errors.append("expected_skill_count=%s, фактически описано %d" % (expected, actual))

    return {"errors": errors, "warnings": warnings, "expected_skill_count": actual}
