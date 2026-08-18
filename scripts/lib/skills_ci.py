"""Проверки целостности системы навыков (skills-ci-integrity) для этого репозитория.

Раскладка ствола: собственные скиллы — `agent-skills/matemacia/<skill>/`,
внешние — `agent-skills/vendor/<vendor>/<skill>/`, реестр источников —
`skills.lock.yaml` в корне, установка — `scripts/install-skills.ps1`.

Проверки детерминированы: агенты не запускаются, сеть не требуется. FAIL
блокирует merge и релиз.

Использование:
    python scripts/lib/skills_ci.py [--skip-install-checks]
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import minyaml  # noqa: E402
import routing_eval  # noqa: E402
import skilllib  # noqa: E402
import supply_chain_scan  # noqa: E402

ROOT = skilllib.repo_root()
SKILLS_ROOT = skilllib.agent_skills_root()
MIN_GOLDEN_TASKS = 18
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[int, str, str, list[str]]] = []

    def add(self, number: int, title: str, problems: list[str], skipped: str = "") -> None:
        status = "SKIP" if skipped else ("FAIL" if problems else "PASS")
        self.rows.append((number, title, status, problems or ([skipped] if skipped else [])))

    def failed(self) -> bool:
        return any(status == "FAIL" for _n, _t, status, _p in self.rows)

    def dump(self) -> None:
        for number, title, status, problems in self.rows:
            print("%-4s %2d. %s" % (status, number, title))
            for problem in problems:
                print("        - %s" % problem)
        print("")
        print("result: %s" % ("FAIL" if self.failed() else "PASS"))


def _git(*args: str):
    try:
        completed = subprocess.run(
            ("git",) + args, cwd=ROOT, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    if completed.returncode != 0:
        return None, completed.stderr.strip()
    return completed.stdout, ""


def _vendor_dirs() -> list[str]:
    vendor = os.path.join(SKILLS_ROOT, "vendor")
    if not os.path.isdir(vendor):
        return []
    return sorted(
        entry.path for entry in os.scandir(vendor) if entry.is_dir() and entry.name != ".git"
    )


def _vendor_skills() -> list[str]:
    found = []
    for vendor_dir in _vendor_dirs():
        for current, dirs, files in os.walk(vendor_dir):
            dirs[:] = [name for name in dirs if name not in (".git", "__pycache__")]
            if "SKILL.md" in files:
                found.append(current)
    return sorted(found)


def _lock_entries(lock: dict) -> list[dict]:
    return [entry for entry in (lock.get("skills") or []) if isinstance(entry, dict)]


def main(argv: list[str]) -> int:
    skip_install = "--skip-install-checks" in argv
    report = Report()
    lock = skilllib.load_lock()
    entries = _lock_entries(lock)

    # 1. Каждый vendor-каталог связан с записью в реестре и наоборот.
    problems = []
    declared = {
        str(entry.get("vendor_dir") or "").strip(): entry
        for entry in entries
        if entry.get("vendor_dir")
    }
    for entry in entries:
        if not entry.get("vendor_dir"):
            problems.append(
                "%s: не указан vendor_dir" % (entry.get("name") or entry.get("repository"))
            )
    on_disk = {os.path.basename(path) for path in _vendor_dirs()}
    for vendor in sorted(on_disk - set(declared)):
        problems.append("%s не описан в skills.lock.yaml" % vendor)
    for vendor in sorted(set(declared) - on_disk):
        problems.append("%s описан в реестре, но отсутствует в vendor" % vendor)
    report.add(1, "vendor-скиллы связаны с реестром источников", problems)

    # 2. Полный commit SHA и дата аудита у каждого источника.
    problems = []
    for entry in entries:
        name = entry.get("name") or entry.get("repository") or "<без имени>"
        if not SHA_RE.match(str(entry.get("commit") or "")):
            problems.append("%s: commit не полный 40-символьный SHA" % name)
        if not DATE_RE.match(str(entry.get("reviewed_at") or "")):
            problems.append("%s: reviewed_at не в формате YYYY-MM-DD" % name)
        if not str(entry.get("audit") or "").strip():
            problems.append("%s: не записан результат аудита" % name)
    report.add(2, "у каждого источника полный SHA, дата и результат аудита", problems)

    # 3. Реестр не пуст и не описывает несуществующее.
    report.add(
        3,
        "реестр источников заполнен",
        [] if entries else ["skills.lock.yaml не содержит ни одного источника"],
    )

    # 4. Повторный аудит не находит критики вне принятой базовой линии.
    #
    # Security-скиллы разбирают уязвимые паттерны, поэтому часть срабатываний
    # разобрана и записана в реестр. Всё, чего там нет, считается новым и
    # роняет проверку: так опасный паттерн из обновления не проходит молча.
    vendor_paths = _vendor_skills()
    if vendor_paths:
        accepted = {
            str(entry.get("vendor_dir") or ""): {
                str(rule) for rule in (entry.get("accepted_findings") or [])
            }
            for entry in entries
        }
        problems = []
        for item in supply_chain_scan.scan(os.path.join(SKILLS_ROOT, "vendor")):
            if item["severity"] != "critical":
                continue
            vendor = item["file"].split("/")[0]
            if item["id"] in accepted.get(vendor, set()):
                continue
            problems.append(
                "%s %s (%s) — правило вне базовой линии %s"
                % (item["id"], item["file"], item["description"], vendor)
            )
        report.add(4, "повторный аудит не даёт находок вне базовой линии", problems)
    else:
        report.add(4, "повторный аудит не даёт находок вне базовой линии", [],
                   skipped="vendor-скиллы не подключены")

    # 5-6. Установка: число и совпадение каталогов.
    claude_dir = os.path.join(ROOT, ".claude", "skills")
    agents_dir = os.path.join(ROOT, ".agents", "skills")
    claude_set = skilllib.installed_skills(claude_dir)
    agents_set = skilllib.installed_skills(agents_dir)
    expected = len(skilllib.iter_own_skills()) + len(vendor_paths)
    if skip_install or (not claude_set and not agents_set):
        note = (
            "проверка пропущена (--skip-install-checks)" if skip_install
            else "скиллы не установлены: запустите scripts/install-skills.ps1"
        )
        report.add(5, "число установленных навыков совпадает с исходниками", [], skipped=note)
        report.add(6, ".claude/skills и .agents/skills идентичны", [], skipped=note)
    else:
        count_problems = []
        if len(claude_set) != expected:
            count_problems.append(".claude/skills: %d вместо %d" % (len(claude_set), expected))
        if len(agents_set) != expected:
            count_problems.append(".agents/skills: %d вместо %d" % (len(agents_set), expected))
        report.add(5, "число установленных навыков совпадает с исходниками", count_problems)
        report.add(
            6,
            ".claude/skills и .agents/skills идентичны",
            [
                "%s есть только в %s/skills"
                % (name, ".claude" if name in claude_set else ".agents")
                for name in sorted(set(claude_set) ^ set(agents_set))
            ],
        )

    # 7. В vendor нет ручных незакоммиченных правок.
    output, error = _git("status", "--porcelain", "--", "agent-skills/vendor")
    if output is None:
        report.add(7, "в vendor нет незакоммиченных изменений", [],
                   skipped="git недоступен: %s" % error)
    else:
        report.add(
            7,
            "в vendor нет незакоммиченных изменений",
            [line.strip() for line in output.splitlines() if line.strip()],
        )

    # 8-9. Структура и метаданные собственных скиллов.
    structure_problems: list[str] = []
    metadata_problems: list[str] = []
    for path in skilllib.iter_own_skills():
        result = skilllib.validate_skill(path)
        for error in result["errors"]:
            target = (
                metadata_problems
                if ("metadata" in error or "description" in error or "frontmatter" in error)
                else structure_problems
            )
            target.append("%s: %s" % (result["skill"], error))
    report.add(8, "каждый собственный скилл имеет обязательную структуру", structure_problems)
    report.add(9, "метаданные проходят schema validation", metadata_problems)

    # 10. Изменения критических скиллов зафиксированы в changelog с ревьюерами.
    report.add(10, "изменения critical skills прошли усиленное ревью", _check_critical_review())

    # 11. Routing tests: покрытие критических скиллов.
    routing_dir = os.path.join(SKILLS_ROOT, "tests", "routing")
    if os.path.isdir(routing_dir):
        cases = routing_eval.load_cases(routing_dir)
        critical = tuple(
            os.path.basename(path)
            for path in skilllib.iter_own_skills()
            if ((minyaml.frontmatter(os.path.join(path, "SKILL.md"))[0] or {}).get("metadata") or {})
            .get("criticality") == "critical"
        )
        report.add(11, "routing tests пройдены", routing_eval.check_coverage(cases, critical))
    else:
        report.add(11, "routing tests пройдены", ["каталог agent-skills/tests/routing отсутствует"])

    # 12. Golden tasks описаны и без критических регрессий.
    report.add(12, "golden tasks без критических регрессий", _check_golden_tasks())

    report.dump()
    return 1 if report.failed() else 0


def _check_critical_review() -> list[str]:
    problems: list[str] = []
    changelog_path = os.path.join(SKILLS_ROOT, "CHANGELOG.md")
    if not os.path.isfile(changelog_path):
        return ["отсутствует agent-skills/CHANGELOG.md"]
    with open(changelog_path, "r", encoding="utf-8") as handle:
        changelog = handle.read()

    for path in skilllib.iter_own_skills():
        name = os.path.basename(path)
        meta, _body = minyaml.frontmatter(os.path.join(path, "SKILL.md"))
        block = (meta or {}).get("metadata") or {}
        if block.get("criticality") != "critical":
            continue
        version = str(block.get("version"))
        if not re.search(re.escape(name) + r"[^\n]*" + re.escape(version), changelog):
            problems.append("%s %s не зафиксирован в CHANGELOG.md" % (name, version))
        if not block.get("reviewers"):
            problems.append("%s: critical скилл без metadata.reviewers" % name)
    return problems


def _check_golden_tasks() -> list[str]:
    path = os.path.join(SKILLS_ROOT, "tests", "golden-tasks", "golden-tasks.yaml")
    if not os.path.isfile(path):
        return ["отсутствует tests/golden-tasks/golden-tasks.yaml"]
    data = minyaml.load(path) or {}
    tasks = data.get("tasks") or []
    problems: list[str] = []
    if len(tasks) < MIN_GOLDEN_TASKS:
        problems.append("описано %d задач, требуется минимум %d" % (len(tasks), MIN_GOLDEN_TASKS))
    seen: set = set()
    for task in tasks:
        if not isinstance(task, dict):
            problems.append("задача не является отображением")
            continue
        task_id = task.get("id")
        if not task_id or task_id in seen:
            problems.append("задача без уникального id: %r" % task_id)
        seen.add(task_id)
        for field in ("prompt", "expected_skills", "invariants", "acceptance"):
            if not task.get(field):
                problems.append("%s: не заполнено поле %s" % (task_id, field))
    return problems


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
