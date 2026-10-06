"""Статический скан стороннего скилла перед подключением в vendor.

Скан — вход для `skill-supply-chain-audit`, а не замена ревью: отсутствие
срабатываний НЕ даёт verdict PASS. Скрипт формирует findings и предварительный
verdict; окончательный verdict ставит человек или агент по SKILL.md.

Использование:
    python supply_chain_scan.py <каталог> [--repository owner/repo] [--sha <40hex>]
"""

from __future__ import annotations

import os
import re
import sys
import datetime

TEXT_SUFFIXES = {
    ".md", ".markdown", ".txt", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg",
    ".ps1", ".psm1", ".sh", ".bash", ".zsh", ".py", ".js", ".ts", ".rb", ".pl",
}
BINARY_SUFFIXES = {".exe", ".dll", ".so", ".dylib", ".bin", ".msi", ".scr", ".com", ".pyd", ".jar"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}

# (id, severity, регулярное выражение, описание)
RULES = [
    ("AUD-001", "critical", r"(?i)ignore\s+(all\s+)?(the\s+)?(previous|above|prior|preceding)?\s*(instructions|rules|prompts|guidance)", "prompt injection: перекрытие инструкций"),
    ("AUD-002", "critical", r"(?i)(disregard|override) (the )?(system|previous) prompt", "prompt injection: подмена системного промпта"),
    ("AUD-003", "high", r"(?i)<!--.*?(instruction|prompt|system).*?-->", "скрытая инструкция в HTML-комментарии"),
    ("AUD-010", "critical", r"(?i)(\.env\b|id_rsa|id_ed25519|\.ssh/|credentials\.json|\.aws/|\.npmrc|\.git-credentials)", "доступ к секретам и credential-файлам"),
    ("AUD-011", "high", r"(?i)(ANTHROPIC_API_KEY|OPENAI_API_KEY|AWS_SECRET|DJANGO_SECRET_KEY|SECRET_KEY\s*=)", "чтение или запись ключей"),
    ("AUD-020", "high", r"(?i)\b(curl|wget|Invoke-WebRequest|Invoke-RestMethod|iwr|urllib\.request|requests\.(get|post)|httpx|fetch\()", "сетевое обращение"),
    ("AUD-021", "critical", r"(?i)(curl|wget|iwr|Invoke-WebRequest)[^\n|]*\|\s*(ba)?sh", "загрузка и исполнение внешнего кода"),
    ("AUD-030", "critical", r"(?i)\b(Invoke-Expression|\biex\b|eval\(|exec\(|compile\(|importlib\.import_module|__import__|Add-Type)\b", "динамическое исполнение кода"),
    ("AUD-031", "high", r"(?i)(base64|FromBase64String|b64decode|atob|-EncodedCommand|codecs\.decode)", "кодирование или обфускация полезной нагрузки"),
    ("AUD-032", "medium", r"(?i)(\$\w+\s*\+\s*['\"][a-z\-]{1,4}['\"]|join\(\[?['\"]{2}\]?\))", "сборка команды из фрагментов"),
    ("AUD-040", "critical", r"(?i)git\s+(push\s+--force|reset\s+--hard|clean\s+-[a-z]*f|filter-branch|update-ref\s+-d)", "опасная git-команда"),
    ("AUD-041", "critical", r"(?i)(rm\s+-rf|Remove-Item[^\n]*-Recurse[^\n]*-Force|del\s+/s\s+/q|rmdir\s+/s)", "рекурсивное удаление файлов"),
    ("AUD-042", "high", r"(?i)(Set-Content|Out-File|>\s*)[^\n]*(\.\./\.\./|~[\\/]|%USERPROFILE%|\$HOME)", "запись за пределы корня репозитория"),
    ("AUD-050", "critical", r"(?i)(\.claude/settings|\.claude/hooks|settings\.local\.json|mcp[_-]?config|\.mcp\.json|claude_desktop_config)", "изменение hooks, MCP или настроек агента"),
    ("AUD-051", "high", r"(?i)(allowed-tools|allowedTools|permissions)\s*:\s*(\*|\[?\s*['\"]?Bash\(\*\)|all)", "чрезмерные разрешения"),
    ("AUD-060", "critical", r"(?i)(--insecure\b|-k\b\s+https|verify\s*=\s*False|SkipCertificateCheck|ServerCertificateValidationCallback|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*0)", "отключение TLS-проверки"),
    ("AUD-070", "medium", r"(?i)(crontab|schtasks|Register-ScheduledTask|systemd|launchctl)", "установка постоянного планировщика"),
    ("AUD-071", "high", r"(?i)(nc\s+-l|ncat|reverse shell|/dev/tcp/|Start-Process[^\n]*-WindowStyle\s+Hidden)", "скрытое или обратное соединение"),
]

COMPILED = [(rule_id, severity, re.compile(pattern, re.DOTALL), description)
            for rule_id, severity, pattern, description in RULES]

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _iter_files(root: str):
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        for name in sorted(files):
            yield os.path.join(current, name)


def scan(root: str) -> list[dict]:
    findings: list[dict] = []
    for path in _iter_files(root):
        rel = os.path.relpath(path, root).replace("\\", "/")
        suffix = os.path.splitext(path)[1].lower()
        if suffix in BINARY_SUFFIXES:
            findings.append({"id": "AUD-080", "severity": "critical", "file": rel,
                             "description": "исполняемый бинарный файл в скилле"})
            continue
        if suffix not in TEXT_SUFFIXES:
            try:
                with open(path, "rb") as handle:
                    if b"\x00" in handle.read(4096):
                        findings.append({"id": "AUD-081", "severity": "high", "file": rel,
                                         "description": "бинарное содержимое в файле неизвестного типа"})
                        continue
            except OSError:
                continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError as exc:
            findings.append({"id": "AUD-090", "severity": "medium", "file": rel,
                             "description": "файл не читается: %s" % exc})
            continue
        for rule_id, severity, pattern, description in COMPILED:
            match = pattern.search(text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                findings.append({"id": rule_id, "severity": severity, "file": "%s:%d" % (rel, line),
                                 "description": description})
    return findings


def verdict_for(findings: list[dict]) -> str:
    worst = max((SEVERITY_ORDER[item["severity"]] for item in findings), default=-1)
    if worst >= SEVERITY_ORDER["critical"]:
        return "BLOCK"
    if worst >= SEVERITY_ORDER["medium"]:
        return "REVIEW"
    # Чистый скан не означает PASS: требуется ручное подтверждение.
    return "REVIEW"


def main(argv: list[str]) -> int:
    paths = [arg for arg in argv if not arg.startswith("--")]
    if not paths:
        print(__doc__)
        return 3
    root = os.path.abspath(paths[0])
    repository = "unknown/unknown"
    sha = "0" * 40
    if "--repository" in argv:
        repository = argv[argv.index("--repository") + 1]
    if "--sha" in argv:
        sha = argv[argv.index("--sha") + 1]

    findings = scan(root)
    findings.sort(key=lambda item: (-SEVERITY_ORDER[item["severity"]], item["file"]))
    verdict = verdict_for(findings)

    print("repository: %s" % repository)
    print("commit_sha: %s" % sha)
    print("verdict: %s   # предварительный, требует подтверждения ревьюером" % verdict)
    if findings:
        print("findings:")
        for item in findings:
            print("  - id: %s" % item["id"])
            print("    severity: %s" % item["severity"])
            print("    file: %s" % item["file"])
            print("    description: %s" % item["description"])
    else:
        print("findings: []")
    print("scanned_files: %d" % sum(1 for _ in _iter_files(root)))
    print("reviewed_at: %s" % datetime.date.today().isoformat())
    return 1 if verdict == "BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
