"""CLI валидации структуры и метаданных скиллов.

Использование:
    python validate_skill.py <путь-к-скиллу> [...] [--strict]
    python validate_skill.py --all [--strict]

Коды выхода: 0 — все valid (или valid/warning без --strict), 1 — есть invalid,
2 — есть warning при --strict, 3 — ошибка вызова.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import skilllib  # noqa: E402


def _print(result: dict) -> None:
    print("skill: %s" % result["skill"])
    print("status: %s" % result["status"])
    for key in ("errors", "warnings"):
        items = result[key]
        if not items:
            print("%s: []" % key)
            continue
        print("%s:" % key)
        for item in items:
            print("  - %s" % item)
    print("")


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    paths = [arg for arg in argv if not arg.startswith("--")]
    if "--all" in argv:
        paths = skilllib.iter_own_skills()
    if not paths:
        print(__doc__)
        return 3

    results = []
    for path in paths:
        if not os.path.isdir(path):
            print("skill: %s\nstatus: invalid\nerrors:\n  - каталог не найден\n" % path)
            results.append({"status": "invalid"})
            continue
        result = skilllib.validate_skill(path)
        _print(result)
        results.append(result)

    invalid = sum(1 for item in results if item["status"] == "invalid")
    warned = sum(1 for item in results if item["status"] == "warning")
    print("summary: checked=%d valid=%d warning=%d invalid=%d"
          % (len(results), len(results) - invalid - warned, warned, invalid))
    if invalid:
        return 1
    if warned and strict:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
