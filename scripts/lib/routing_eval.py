"""Проверка routing-кейсов и подсчёт метрик выбора скиллов.

Две функции:

1. `--check-coverage` — статическая проверка набора кейсов: схема, уникальность
   id, покрытие каждого critical скилла positive- и negative-кейсом. Работает
   без запуска агентов, поэтому годится для CI.
2. `--run <файл>` — подсчёт precision / recall / false positive rate по
   записанному прогону агента и сравнение с целевыми значениями.

Использование:
    python routing_eval.py --cases <файл|каталог> --check-coverage
    python routing_eval.py --cases <файл|каталог> --run <прогон.yaml> [...]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import minyaml  # noqa: E402
import skilllib  # noqa: E402

TARGETS = {
    "precision_required_domain_skills": 0.90,
    "recall_critical_security_skills": 0.95,
    "false_positive_rate": 0.10,
}

KINDS = ("positive", "negative", "priority")


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def load_cases(target: str) -> list[dict]:
    files = []
    if os.path.isdir(target):
        for current, _dirs, names in os.walk(target):
            files.extend(os.path.join(current, name) for name in sorted(names)
                         if name.endswith((".yaml", ".yml")))
    else:
        files = [target]
    cases: list[dict] = []
    for path in files:
        data = minyaml.load(path)
        for case in _as_list((data or {}).get("cases") if isinstance(data, dict) else data):
            if isinstance(case, dict):
                case = dict(case)
                case.setdefault("source", os.path.relpath(path, skilllib.repo_root()).replace("\\", "/"))
                cases.append(case)
    return cases


def check_coverage(cases: list[dict], critical: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    positive: set[str] = set()
    negative: set[str] = set()

    for case in cases:
        case_id = case.get("id")
        if not case_id:
            errors.append("%s: кейс без id" % case.get("source"))
            continue
        if case_id in seen:
            errors.append("дублирующийся id кейса: %s" % case_id)
        seen.add(case_id)
        kind = case.get("kind")
        if kind not in KINDS:
            errors.append("%s: kind=%r вне %s" % (case_id, kind, list(KINDS)))
        if not case.get("prompt"):
            errors.append("%s: нет prompt" % case_id)
        if kind == "positive":
            expected = _as_list(case.get("expected"))
            if not expected:
                errors.append("%s: positive-кейс без expected" % case_id)
            positive.update(expected)
        elif kind == "negative":
            forbidden = _as_list(case.get("must_not_activate"))
            if not forbidden:
                errors.append("%s: negative-кейс без must_not_activate" % case_id)
            negative.update(forbidden)
        elif kind == "priority":
            order = _as_list(case.get("priority"))
            if len(order) < 2:
                errors.append("%s: priority-кейс должен перечислять минимум два скилла" % case_id)
            positive.update(order[:1])

    for name in critical:
        if name not in positive:
            errors.append("critical скилл %s не покрыт positive-кейсом" % name)
        if name not in negative:
            errors.append("critical скилл %s не покрыт negative-кейсом" % name)
    return errors


def evaluate(cases: list[dict], run_path: str) -> dict:
    run = minyaml.load(run_path) or {}
    by_id = {case["id"]: case for case in cases if case.get("id")}
    observations = {item.get("id"): item for item in _as_list(run.get("observations")) if isinstance(item, dict)}

    true_positive = false_positive = missed = 0
    negative_total = negative_violated = 0
    priority_ok = priority_total = 0
    conflicts = 0
    unresolved: list[str] = []

    for case_id, case in sorted(by_id.items()):
        observation = observations.get(case_id)
        if observation is None:
            unresolved.append(case_id)
            continue
        selected = set(_as_list(observation.get("selected")))
        if case.get("kind") == "positive":
            expected = set(_as_list(case.get("expected")))
            optional = set(_as_list(case.get("allowed_extra")))
            true_positive += len(expected & selected)
            missed += len(expected - selected)
            false_positive += len(selected - expected - optional)
        elif case.get("kind") == "negative":
            forbidden = set(_as_list(case.get("must_not_activate")))
            negative_total += 1
            if forbidden & selected:
                negative_violated += 1
                false_positive += len(forbidden & selected)
        elif case.get("kind") == "priority":
            priority_total += 1
            order = [name for name in _as_list(case.get("priority")) if name in selected]
            observed = [name for name in _as_list(observation.get("order")) or order if name in selected]
            if observed == [name for name in _as_list(case.get("priority")) if name in selected]:
                priority_ok += 1
            else:
                conflicts += 1

    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 0.0
    recall = true_positive / (true_positive + missed) if (true_positive + missed) else 0.0
    fpr = negative_violated / negative_total if negative_total else 0.0

    failures = []
    if precision < TARGETS["precision_required_domain_skills"]:
        failures.append("precision %.3f < %.2f" % (precision, TARGETS["precision_required_domain_skills"]))
    if recall < TARGETS["recall_critical_security_skills"]:
        failures.append("recall %.3f < %.2f" % (recall, TARGETS["recall_critical_security_skills"]))
    if fpr > TARGETS["false_positive_rate"]:
        failures.append("false positive rate %.3f > %.2f" % (fpr, TARGETS["false_positive_rate"]))
    if unresolved:
        failures.append("нет наблюдений для кейсов: %s" % ", ".join(unresolved))

    return {
        "agent": run.get("agent", "unknown"),
        "run": os.path.basename(run_path),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "false_positive_rate": round(fpr, 3),
        "priority_cases": "%d/%d" % (priority_ok, priority_total),
        "conflicts": conflicts,
        "manual_overrides": run.get("manual_overrides", 0),
        "failures": failures,
    }


def main(argv: list[str]) -> int:
    if "--cases" not in argv:
        print(__doc__)
        return 3
    target = argv[argv.index("--cases") + 1]
    cases = load_cases(target)
    print("cases_loaded: %d" % len(cases))
    exit_code = 0

    if "--check-coverage" in argv:
        critical = tuple(
            name for name in (
                os.path.basename(path) for path in skilllib.iter_own_skills()
            )
            if _is_critical(name)
        )
        errors = check_coverage(cases, critical)
        print("coverage_errors:%s" % (" []" if not errors else ""))
        for error in errors:
            print("  - %s" % error)
        if errors:
            exit_code = 1

    runs = [argv[index + 1] for index, arg in enumerate(argv) if arg == "--run"]
    for run_path in runs:
        result = evaluate(cases, run_path)
        print("---")
        for key in ("run", "agent", "precision", "recall", "false_positive_rate",
                    "priority_cases", "conflicts", "manual_overrides"):
            print("%s: %s" % (key, result[key]))
        print("failures:%s" % (" []" if not result["failures"] else ""))
        for failure in result["failures"]:
            print("  - %s" % failure)
        if result["failures"]:
            exit_code = 1
    return exit_code


def _is_critical(name: str) -> bool:
    for path in skilllib.iter_own_skills():
        if os.path.basename(path) != name:
            continue
        meta, _ = minyaml.frontmatter(os.path.join(path, "SKILL.md"))
        return ((meta or {}).get("metadata") or {}).get("criticality") == "critical"
    return name in skilllib.CRITICAL_SKILLS


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
