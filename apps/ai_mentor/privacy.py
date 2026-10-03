"""Privacy boundary for every outbound LLM request.

Only learning content may cross this boundary. Student identity and the local
audit trail stay inside Mathemation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

_DERIVATION_LABEL = b"mathemation:ai-privacy-pseudonym:v1"
_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])", re.I)
_QUERY_URL_RE = re.compile(r"\bhttps?://[^\s<>?]+\?[^\s<>]+", re.I)
_INTL_PHONE_RE = re.compile(
    r"(?<!\d)\+\d{1,3}[\s-]?\(?\d{2,4}\)?(?:[\s-]?\d{2,4}){2,3}(?!\d)"
)
_RU_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+7|8)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)"
)
_SNILS_RE = re.compile(r"(?<!\d)\d{3}[- ]\d{3}[- ]\d{3}[- ]\d{2}(?!\d)")
_PASSPORT_RE = re.compile(r"(?<!\d)\d{2}\s?\d{2}\s+\d{6}(?!\d)")
_LONG_GROUP_RE = re.compile(r"(?<!\d)\d{4}(?:[ -]\d{4}){3}(?!\d)")
_NAME_WORD = r"[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z'-]*"
_INTRO_PATTERNS = (
    re.compile(rf"\b(?i:меня\s+зовут)\s+{_NAME_WORD}(?:\s+{_NAME_WORD})?"),
    re.compile(rf"\b(?i:я)\s*(?:—|–|-)\s*{_NAME_WORD}(?:\s+{_NAME_WORD})?"),
)


@dataclass(frozen=True)
class ScrubResult:
    text: str
    counts: dict[str, int]


def _pseudonym_key() -> bytes:
    configured = settings.AI_PRIVACY_PSEUDONYM_KEY
    if configured:
        return configured.encode("utf-8")
    # The application secret is input to a separate HMAC KDF; it is never used
    # raw as the pseudonym key.
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), _DERIVATION_LABEL, hashlib.sha256
    ).digest()


def pseudonym_for(student) -> str:
    if student.pk is None:
        raise ValueError("student must be saved before pseudonymization")
    digest = hmac.new(
        _pseudonym_key(), str(student.pk).encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"stu_{digest[:24]}"


def _identity_values(student) -> list[tuple[str, str]]:
    users = [student.user]
    users.extend(
        parent.user
        for parent in student.parents.select_related("user").all()
    )
    values: list[tuple[str, str]] = []
    for user in users:
        full_name = user.get_full_name().strip()
        for kind, value in (
            ("name", full_name),
            ("name", user.first_name),
            ("name", user.last_name),
            ("username", user.username),
            ("email", user.email),
        ):
            value = (value or "").strip()
            if value:
                values.append((kind, value))
    # Replace longer values first so a full name becomes one placeholder.
    return sorted(set(values), key=lambda row: len(row[1]), reverse=True)


def _literal_pattern(value: str, *, whole_word: bool) -> re.Pattern:
    pieces = []
    for char in value:
        pieces.append("[её]" if char.casefold() in {"е", "ё"} else re.escape(char))
    body = "".join(pieces)
    if whole_word:
        body = rf"(?<!\w){body}(?!\w)"
    return re.compile(body, re.I)


def scrub(text: str, student) -> ScrubResult:
    value = str(text or "")
    counts = {
        "name": 0,
        "username": 0,
        "email": 0,
        "phone": 0,
        "url": 0,
        "number": 0,
        "self_introduction": 0,
    }

    def replace(pattern: re.Pattern, replacement: str, kind: str) -> None:
        nonlocal value
        value, made = pattern.subn(replacement, value)
        counts[kind] += made

    replace(_QUERY_URL_RE, "[ссылка]", "url")
    replace(_EMAIL_RE, "[почта]", "email")
    replace(_INTL_PHONE_RE, "[телефон]", "phone")
    replace(_RU_PHONE_RE, "[телефон]", "phone")
    for pattern in (_SNILS_RE, _PASSPORT_RE, _LONG_GROUP_RE):
        replace(pattern, "[номер]", "number")
    for pattern in _INTRO_PATTERNS:
        replace(pattern, "[имя]", "self_introduction")

    placeholders = {"name": "[имя]", "username": "[логин]", "email": "[почта]"}
    for kind, identity in _identity_values(student):
        # Usernames and e-mails can contain punctuation; boundaries still use
        # the adjacent word characters and avoid replacing parts of formulas.
        replace(_literal_pattern(identity, whole_word=True), placeholders[kind], kind)
    return ScrubResult(value, counts)


def merge_counts(*items: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for item in items:
        for key, value in item.items():
            merged[key] = merged.get(key, 0) + int(value)
    return merged


def _identifying_strings(student) -> list[str]:
    return [
        value for _kind, value in _identity_values(student)
        if len(value) >= 3
    ]


def _contains_identifier(serialized: str, identity: str) -> bool:
    return _literal_pattern(identity, whole_word=True).search(serialized) is not None


def defend_payload(payload: dict, student) -> tuple[dict, dict[str, int]]:
    """Re-scrub the complete payload and assert that direct identifiers are gone."""
    counts: list[dict[str, int]] = []

    def clean(value):
        if isinstance(value, str):
            result = scrub(value, student)
            counts.append(result.counts)
            return result.text
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()}
        return value

    cleaned = clean(payload)
    serialized = json.dumps(cleaned, ensure_ascii=False)
    leaked = [
        identity for identity in _identifying_strings(student)
        if _contains_identifier(serialized, identity)
    ]
    if leaked:
        logger.warning(
            "Outbound LLM payload required final identifier replacement (%d values)",
            len(leaked),
        )

        def force_replace(value):
            if isinstance(value, str):
                for identity in leaked:
                    value = _literal_pattern(identity, whole_word=True).sub("[данные]", value)
                return value
            if isinstance(value, list):
                return [force_replace(item) for item in value]
            if isinstance(value, dict):
                return {key: force_replace(item) for key, item in value.items()}
            return value

        cleaned = force_replace(cleaned)
        serialized = json.dumps(cleaned, ensure_ascii=False)
    assert not any(
        _contains_identifier(serialized, identity)
        for identity in _identifying_strings(student)
    ), "outbound payload contains a student identifier"
    return cleaned, merge_counts(*counts)


def student_for_pseudonym(pseudonym: str):
    """Resolve a local audit pseudonym during an incident investigation."""
    from .models import AiOutboundRequest

    row = (
        AiOutboundRequest.objects.filter(pseudonym=pseudonym, student__isnull=False)
        .select_related("student__user")
        .order_by("-created_at")
        .first()
    )
    return row.student if row else None
