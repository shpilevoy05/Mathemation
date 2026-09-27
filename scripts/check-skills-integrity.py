"""Check integrity of vendored and Mathemation agent skills using stdlib only."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_SKILLS = ROOT / "agent-skills"
VENDOR_ROOT = AGENT_SKILLS / "vendor"
MATEMACIA_ROOT = AGENT_SKILLS / "matemacia"
LOCK_PATH = ROOT / "skills.lock.yaml"

VENDOR_REPOSITORIES = {
    "anthropic": "anthropics/skills",
    "trailofbits": "trailofbits/skills",
    "openai": "openai/plugins",
    "sentry": "getsentry/skills",
    "supabase": "supabase/agent-skills",
    "huggingface": "huggingface/skills",
    "duckdb": "duckdb/duckdb-skills",
    "clickhouse": "ClickHouse/agent-skills",
    "vercel": "vercel-labs/agent-skills",
}

FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
BINARY_SUFFIXES = {".exe", ".dll", ".so", ".msi"}


@dataclass
class LockEntry:
    name: str = ""
    repository: str = ""
    commit: str = ""
    reviewed_at: str = ""


def scalar(value: str) -> str:
    value = value.split("#", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def parse_lock(path: Path) -> list[LockEntry]:
    entries: list[LockEntry] = []
    current: LockEntry | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        name_match = re.match(r"^\s*-\s+name:\s*(.+?)\s*$", raw_line)
        if name_match:
            if current is not None:
                entries.append(current)
            current = LockEntry(name=scalar(name_match.group(1)))
            continue
        if current is None:
            continue
        field_match = re.match(
            r"^\s+(repository|commit|reviewed_at):\s*(.*?)\s*$", raw_line
        )
        if field_match:
            setattr(current, field_match.group(1), scalar(field_match.group(2)))
    if current is not None:
        entries.append(current)
    return entries


def skill_directories() -> tuple[list[Path], list[Path]]:
    vendor_dirs = [
        skill
        for vendor in sorted(VENDOR_ROOT.iterdir())
        if vendor.is_dir()
        for skill in sorted(vendor.iterdir())
        if skill.is_dir()
    ]
    matemacia_dirs = sorted(path for path in MATEMACIA_ROOT.iterdir() if path.is_dir())
    return vendor_dirs, matemacia_dirs


def frontmatter(path: Path) -> list[str] | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return None
    return lines[1:end]


def top_value(lines: list[str], key: str) -> str | None:
    pattern = re.compile(rf"^{re.escape(key)}:\s*(.*?)\s*$")
    for line in lines:
        if line.startswith((" ", "\t")):
            continue
        match = pattern.match(line)
        if match:
            return scalar(match.group(1))
    return None


def has_nested_value(lines: list[str], section: str, key: str) -> bool:
    in_section = False
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            in_section = line.strip() == f"{section}:"
            continue
        if in_section and indent == 2:
            match = re.match(rf"^  {re.escape(key)}:\s*(.*?)\s*$", line)
            if match and scalar(match.group(1)):
                return True
    return False


def source_names(vendor_dirs: list[Path], own_dirs: list[Path]) -> set[str]:
    return {path.name for path in [*vendor_dirs, *own_dirs]}


def installed_names(path: Path) -> set[str]:
    return {entry.name for entry in path.iterdir() if entry.is_dir()}


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

    def report(check: str, ok: bool, detail: str) -> None:
        label = "PASS" if ok else "FAIL"
        print(f"{label} {check}: {detail}")
        if not ok:
            failures.append(f"{check}: {detail}")

    try:
        entries = parse_lock(LOCK_PATH)
    except (OSError, UnicodeError) as exc:
        print(f"FAIL lock: cannot read {LOCK_PATH}: {exc}")
        return 1

    repositories = {entry.repository for entry in entries if entry.repository}
    vendor_names = {path.name for path in VENDOR_ROOT.iterdir() if path.is_dir()}
    unknown_vendors = sorted(vendor_names - VENDOR_REPOSITORIES.keys())
    uncovered = sorted(
        vendor
        for vendor in vendor_names & VENDOR_REPOSITORIES.keys()
        if VENDOR_REPOSITORIES[vendor] not in repositories
    )
    report(
        "1 vendor lock coverage",
        not unknown_vendors and not uncovered,
        f"vendors={len(vendor_names)}, unknown={unknown_vendors}, uncovered={uncovered}",
    )

    bad_shas = [entry.name or entry.repository for entry in entries if not FULL_SHA.fullmatch(entry.commit)]
    report("2 full commit SHA", bool(entries) and not bad_shas, f"entries={len(entries)}, invalid={bad_shas}")

    missing_reviews = [entry.name or entry.repository for entry in entries if not entry.reviewed_at]
    report("3 reviewed_at", bool(entries) and not missing_reviews, f"missing={missing_reviews}")

    try:
        vendor_dirs, own_dirs = skill_directories()
    except OSError as exc:
        print(f"FAIL skill directories: {exc}")
        return 1
    missing_skill_files = [
        str(path.relative_to(ROOT))
        for path in [*vendor_dirs, *own_dirs]
        if not (path / "SKILL.md").is_file()
    ]
    report(
        "4 SKILL.md presence",
        not missing_skill_files,
        f"skill_dirs={len(vendor_dirs) + len(own_dirs)}, missing={missing_skill_files}",
    )

    total = len(vendor_dirs) + len(own_dirs)
    report("5 minimum skill count", total >= 100, f"vendor={len(vendor_dirs)}, matemacia={len(own_dirs)}, total={total}")

    claude_path = ROOT / ".claude" / "skills"
    agents_path = ROOT / ".agents" / "skills"
    if claude_path.is_dir() and agents_path.is_dir():
        claude_names = installed_names(claude_path)
        agents_names = installed_names(agents_path)
        installed_equal = claude_names == agents_names
        report(
            "6 installed name parity",
            installed_equal,
            f"claude={len(claude_names)}, agents={len(agents_names)}",
        )
        expected_names = source_names(vendor_dirs, own_dirs)
        if installed_equal and claude_names != expected_names:
            warning = "installed skill names differ from agent-skills; run install-skills.ps1"
            warnings.append(warning)
            print(f"WARN 6 source parity: {warning}")
        elif installed_equal:
            print("PASS 6 source parity: installed names match agent-skills")
    else:
        report("6 installed name parity", True, "both install directories do not exist; comparison skipped")

    required_errors: list[str] = []
    name_errors: list[str] = []
    for directory in own_dirs:
        path = directory / "SKILL.md"
        if not path.is_file():
            continue
        fm = frontmatter(path)
        if fm is None:
            required_errors.append(f"{directory.name}: missing frontmatter")
            continue
        name = top_value(fm, "name")
        description = top_value(fm, "description")
        missing: list[str] = []
        if not name:
            missing.append("name")
        if not description:
            missing.append("description")
        if not has_nested_value(fm, "metadata", "version"):
            missing.append("metadata.version")
        if top_value(fm, "activation_examples") is None:
            missing.append("activation_examples")
        if top_value(fm, "precedence") is None:
            missing.append("precedence")
        if missing:
            required_errors.append(f"{directory.name}: {', '.join(missing)}")
        if name and name != directory.name:
            name_errors.append(f"{directory.name}: name={name}")
    report(
        "7 Mathemation frontmatter",
        len(own_dirs) == 38 and not required_errors,
        f"count={len(own_dirs)}, errors={required_errors}",
    )
    report("8 directory and frontmatter names", not name_errors, f"mismatches={name_errors}")

    binaries = sorted(
        str(path.relative_to(ROOT))
        for path in AGENT_SKILLS.rglob("*")
        if path.is_file() and path.suffix.lower() in BINARY_SUFFIXES
    )
    report("9 forbidden binaries", not binaries, f"found={binaries}")

    if warnings:
        print(f"WARN summary: {len(warnings)} warning(s); integrity exit code is unaffected")
    if failures:
        print(f"FAIL summary: {len(failures)} check(s) failed")
        return 1
    print("PASS summary: all integrity checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
