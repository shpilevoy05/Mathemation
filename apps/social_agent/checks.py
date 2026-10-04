from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.content.models import Assignment

from .models import BrandProfile, Post, PostCheck, Rubric
from .formulas import FormulaRenderError, to_telegram_text
from .sources import SourceMaterial


@dataclass(frozen=True)
class CheckResult:
    kind: str
    passed: bool
    detail: str = ""


RECOMMENDED_LENGTHS = {
    Rubric.SourceKind.ASSIGNMENT_OF_DAY: 1800,
    Rubric.SourceKind.LESSON_TIP: 1200,
    Rubric.SourceKind.EXAM_COUNTDOWN: 700,
    Rubric.SourceKind.STAFF_IDEA: 1600,
    Rubric.SourceKind.EVERGREEN: 1200,
}
_BUILT_IN_BANNED = (
    r"\bгарант(?:ируем|ия|ирован\w*)\b",
    r"\b100\s*балл\w*\b",
    r"\bсда(?:шь|дите)\s+на\b",
    r"\bточно\s+сда(?:шь|дите)\b",
    r"(?:₽|\bруб(?:\.|л(?:ей|я|ь)?)?\b)",
    r"\bскидк\w*\b",
    r"\bбесплатн\w*\b",
    r"\b(?:вылечим|лечит|исцелит|избавим|устраним)\b",
    r"\b(?:снимем|уберем)\s+(?:стресс|тревогу|тревожность)\b",
    r"\b(?:депресси\w*|тревожност\w*|психологическ\w*)\s+(?:исчезнет|пройдет|вылечим|устраним)\b",
)
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+7|8)[\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)")
_TOKEN_LINK = re.compile(r"(?i)https?://\S+\?\S+")
_NUMBER = re.compile(r"(?<![\w])[-+]?\d+(?:[.,]\d+)?(?![\w])")


def _normalise_text(text: str) -> str:
    return text.casefold().replace("ё", "е")


def banned_phrase(text: str, profile: BrandProfile | None = None) -> CheckResult:
    normalised = _normalise_text(text)
    matches = [pattern for pattern in _BUILT_IN_BANNED if re.search(pattern, normalised, re.IGNORECASE)]
    custom = []
    if profile and isinstance(profile.forbidden_phrases, list):
        custom = [phrase for phrase in profile.forbidden_phrases if isinstance(phrase, str) and _normalise_text(phrase) in normalised]
    passed = not matches and not custom
    detail = "" if passed else "Запрещённая формулировка: " + ", ".join(custom or matches)
    return CheckResult(PostCheck.Kind.BANNED_PHRASE, passed, detail)


def competitor(text: str, profile: BrandProfile | None = None) -> CheckResult:
    normalised = _normalise_text(text)
    found = []
    names = profile.competitors if profile and isinstance(profile.competitors, list) else []
    for name in names:
        if not isinstance(name, str) or not name.strip():
            continue
        candidate = _normalise_text(name.strip())
        if re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", normalised):
            found.append(name)
    passed = not found
    return CheckResult(PostCheck.Kind.COMPETITOR, passed, "" if passed else "Конкурент: " + ", ".join(found))


def _numbers_in(value: Any) -> set[Decimal]:
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, dict):
        return set().union(*(_numbers_in(item) for item in value.values()), set())
    if isinstance(value, (list, tuple, set)):
        return set().union(*(_numbers_in(item) for item in value), set())
    found = set()
    for raw in _NUMBER.findall(str(value)):
        try:
            found.add(Decimal(raw.replace(",", ".")))
        except InvalidOperation:
            continue
    return found


def _remove_publication_datetime(text: str, publication_at: date | datetime | None) -> str:
    if publication_at is None:
        return text
    variants = {
        publication_at.strftime("%d.%m.%Y"),
        publication_at.strftime("%d.%m.%y"),
        publication_at.strftime("%Y-%m-%d"),
    }
    if isinstance(publication_at, datetime):
        variants.update({publication_at.strftime("%H:%M"), publication_at.strftime("%d.%m.%Y %H:%M")})
    for variant in sorted(variants, key=len, reverse=True):
        text = text.replace(variant, "")
    return text


def number_whitelist(text: str, material: SourceMaterial, publication_at: date | datetime | None = None) -> CheckResult:
    cleaned = _remove_publication_datetime(text, publication_at)
    cleaned = re.sub(r"(?m)^\s*\d+[.)](?=\s)", "", cleaned)
    allowed = _numbers_in(material.facts)
    actual = _numbers_in(cleaned)
    invented = sorted(actual - allowed)
    passed = not invented
    detail = "" if passed else "Числа не подтверждены источником: " + ", ".join(format(item, "f") for item in invented)
    return CheckResult(PostCheck.Kind.NUMBER_WHITELIST, passed, detail)


def answer_integrity(text: str, material: SourceMaterial) -> CheckResult:
    if material.assignment_id is None:
        return CheckResult(PostCheck.Kind.ANSWER_INTEGRITY, True, "Не задача дня")
    assignment = Assignment.objects.get(pk=material.assignment_id)
    answer_match = re.search(r"(?im)\bответ\s*[:—-]\s*([^\n]+)", text)
    if material.reveal_answer:
        if answer_match is None:
            return CheckResult(PostCheck.Kind.ANSWER_INTEGRITY, False, "Раскрываемый ответ не найден")
        candidate = answer_match.group(1).strip().rstrip(".;")
        passed = assignment.check_answer(candidate) is True
        return CheckResult(PostCheck.Kind.ANSWER_INTEGRITY, passed, "" if passed else "Ответ не совпадает с эталоном")

    canonical = assignment.correct_answer.strip()
    if not canonical:
        return CheckResult(PostCheck.Kind.ANSWER_INTEGRITY, True, "")
    leaked = answer_match is not None and assignment.check_answer(
        answer_match.group(1).strip().rstrip(".;")
    ) is True
    scan_text = text
    statement = material.facts.get("statement")
    if isinstance(statement, str) and statement:
        statement_versions = {statement}
        try:
            statement_versions.add(to_telegram_text(statement))
        except FormulaRenderError:
            pass
        for version in sorted(statement_versions, key=len, reverse=True):
            scan_text = scan_text.replace(version, "")
    if not leaked:
        candidates = _NUMBER.findall(scan_text)
        candidates.extend(re.findall(r"(?<!\w)[A-Za-zА-Яа-яЁё]+(?!\w)", scan_text))
        leaked = any(assignment.check_answer(candidate) is True for candidate in candidates)
    if not leaked:
        leaked = re.search(rf"(?<!\w){re.escape(canonical)}(?!\w)", scan_text, re.IGNORECASE) is not None
    return CheckResult(PostCheck.Kind.ANSWER_INTEGRITY, not leaked, "" if not leaked else "Ответ раскрыт в версии без ответа")


def length(text: str, source_kind: str) -> CheckResult:
    size = len(text)
    recommended = RECOMMENDED_LENGTHS.get(source_kind, 1200)
    passed = size <= 4096
    if not passed:
        detail = f"{size} символов: превышен лимит 4096"
    elif size > recommended:
        detail = f"{size} символов: рекомендовано до {recommended}"
    else:
        detail = f"{size} символов; рекомендовано до {recommended}"
    return CheckResult(PostCheck.Kind.LENGTH, passed, detail)


def personal_data(text: str) -> CheckResult:
    kinds = []
    if _EMAIL.search(text):
        kinds.append("email")
    if _PHONE.search(text):
        kinds.append("телефон")
    if _TOKEN_LINK.search(text):
        kinds.append("ссылка с параметрами")
    passed = not kinds
    return CheckResult(PostCheck.Kind.PERSONAL_DATA, passed, "" if passed else "Обнаружено: " + ", ".join(kinds))


def run_checks(post: Post, material: SourceMaterial) -> list[PostCheck]:
    profile = BrandProfile.objects.first()
    results = [
        banned_phrase(post.text, profile),
        competitor(post.text, profile),
        number_whitelist(post.text, material, post.scheduled_for),
        answer_integrity(post.text, material),
        length(post.text, post.rubric.source_kind),
        personal_data(post.text),
    ]
    post.checks.all().delete()
    return PostCheck.objects.bulk_create(
        [PostCheck(post=post, kind=result.kind, passed=result.passed, detail=result.detail) for result in results]
    )


def all_passed(checks) -> bool:
    return all(check.passed for check in checks)


check_banned_phrase = banned_phrase
check_competitor = competitor
check_number_whitelist = number_whitelist
check_answer_integrity = answer_integrity
check_length = length
check_personal_data = personal_data
