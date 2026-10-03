"""Второй фактор для сотрудников: TOTP и резервные коды.

Методист и администратор видят чужие персональные данные, публикуют контент и
двигают деньги, поэтому одного пароля им мало: утёкший или подобранный пароль
не должен давать доступ к бэкофису.

Алгоритм — обычный TOTP (RFC 6238, SHA-1, 6 цифр, шаг 30 секунд): его понимают
все приложения-аутентификаторы, а реализация умещается в тридцать строк на
`hmac` и `base64`. Новая зависимость ради этого потребовала бы согласования и
дала бы ровно то же самое.

Две вещи, которые обычно забывают и без которых второй фактор дырявый:

* повторное использование кода. Код живёт 30 секунд, и подсмотренный код можно
  ввести второй раз — поэтому последний принятый шаг запоминается;
* потеря телефона. Без резервных кодов единственным выходом остаётся ручное
  отключение фактора в базе, то есть обход защиты руками.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from django.conf import settings

DIGITS = 6
STEP_SECONDS = 30
# Допуск на расхождение часов: один шаг назад и вперёд.
WINDOW = 1
SECRET_BYTES = 20
RECOVERY_CODES = 8


def generate_secret() -> str:
    """Base32-секрет без заполнителей: его вводят руками."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode().rstrip("=")


def _decode_secret(secret: str) -> bytes:
    padded = secret.strip().upper()
    padded += "=" * (-len(padded) % 8)
    return base64.b32decode(padded, casefold=True)


def current_step(at: float | None = None) -> int:
    return int((at if at is not None else time.time()) // STEP_SECONDS)


def code_for_step(secret: str, step: int) -> str:
    """Одноразовый код для шага времени (RFC 4226 + RFC 6238)."""
    digest = hmac.new(_decode_secret(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    (truncated,) = struct.unpack(">I", digest[offset:offset + 4])
    return str((truncated & 0x7FFFFFFF) % 10**DIGITS).zfill(DIGITS)


def verify_code(secret: str, code: str, *, after_step: int = 0, at: float | None = None) -> int | None:
    """Проверить код. Возвращает принятый шаг или None.

    `after_step` отсекает уже использованные коды: шаг, который приняли в
    прошлый раз, второй раз не проходит.
    """
    candidate = (code or "").strip().replace(" ", "")
    if not candidate.isdigit() or len(candidate) != DIGITS:
        return None
    now = current_step(at)
    for step in range(now - WINDOW, now + WINDOW + 1):
        if step <= after_step:
            continue
        # Сравнение постоянного времени: код короткий, и утечка по времени
        # сузила бы перебор.
        if hmac.compare_digest(code_for_step(secret, step), candidate):
            return step
    return None


def provisioning_uri(user, secret: str) -> str:
    """Ссылка otpauth:// для приложения-аутентификатора."""
    issuer = getattr(settings, "TWO_FACTOR_ISSUER", "Матемация")
    label = quote(f"{issuer}:{user.get_username()}")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"
    )


# --- Резервные коды ---

def generate_recovery_codes(count: int = RECOVERY_CODES) -> list[str]:
    """Человекочитаемые одноразовые коды на случай потери телефона."""
    return [
        f"{secrets.token_hex(2)}-{secrets.token_hex(2)}".lower() for _ in range(count)
    ]


def hash_recovery_code(code: str) -> str:
    """Резервные коды хранятся хешами: база — не место для запасных ключей."""
    normalized = (code or "").strip().lower().replace(" ", "")
    return hashlib.sha256(normalized.encode()).hexdigest()


def required_roles() -> set[str]:
    return {
        role.strip()
        for role in getattr(settings, "TWO_FACTOR_REQUIRED_ROLES", ()) or ()
        if role.strip()
    }


def is_required_for(user) -> bool:
    """Нужен ли этому человеку второй фактор.

    Ученику и родителю фактор не навязываем: он не открывает чужие данные, а
    порог входа поднимает заметно. Сотруднику — обязателен.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if not getattr(settings, "TWO_FACTOR_ENFORCED", False):
        return False
    if user.is_superuser or user.is_staff:
        return True
    return getattr(user, "role", "") in required_roles()
