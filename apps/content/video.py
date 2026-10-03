"""Выдача ссылки на видео занятия.

Видео — самая дорогая часть контента и единственная, которую можно унести
целиком одной ссылкой. Поэтому ссылка на плеер не рендерится в HTML, а
выдаётся отдельным запросом: его видно в логах, он проходит через гейт
подписки и живёт минуты, а не вечно.

Хостинг спрятан за адаптером (`VideoLink`): Kinescope умеет приватные ролики с
подписанным токеном, YouTube и VK — нет, и разница не должна протекать в
шаблоны. Подпись — JWT HS256 без внешней библиотеки: алгоритм умещается в
двадцать строк, а новая зависимость ради него требовала бы согласования.

Что остаётся подключить руками: ключ подписи Kinescope
(`KINESCOPE_SIGNING_KEY`, `KINESCOPE_KEY_ID`) и — если контракт хостинга
отличается — имена параметра и полей токена (`KINESCOPE_TOKEN_PARAM`,
`KINESCOPE_TOKEN_CLAIMS`). Пока ключа нет, выдаётся обычная публичная ссылка,
и это видно в ответе полем `is_private`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


@dataclass(frozen=True)
class VideoLink:
    """Что показывать плееру прямо сейчас."""

    url: str
    provider: str
    is_private: bool
    expires_at: object = None
    can_embed: bool = True

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "provider": self.provider,
            "is_private": self.is_private,
            "expires_at": self.expires_at,
            "can_embed": self.can_embed,
        }


def allowed_hosts() -> set[str]:
    return {host.lower() for host in getattr(settings, "VIDEO_ALLOWED_HOSTS", ()) or ()}


def link_ttl() -> int:
    return int(getattr(settings, "VIDEO_LINK_TTL_SECONDS", 600) or 600)


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def is_allowed_host(url: str) -> bool:
    """Разрешён ли хост встраивания.

    Список закрытый: iframe исполняется в контексте страницы ученика, и
    произвольный чужой хост в нём — это доверие к тому, кто заполнил поле.
    """
    hosts = allowed_hosts()
    if not hosts:
        return True
    host = host_of(url)
    if not host:
        return False
    return any(host == allowed or host.endswith("." + allowed) for allowed in hosts)


def validate_video_url(url: str) -> None:
    """Проверка при сохранении урока: только https и только известные хосты."""
    value = (url or "").strip()
    if not value or "://" not in value:
        # Пустое поле и голый идентификатор ролика Kinescope — это не ссылка.
        return
    if not value.startswith("https://"):
        raise ValidationError("Ссылка на видео должна быть https.")
    if not is_allowed_host(value):
        raise ValidationError(
            "Хост видео не в списке разрешённых: %s" % ", ".join(sorted(allowed_hosts()))
        )


# --- JWT HS256 ---

def _b64(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode()


def sign_jwt(claims: dict, *, key: str, key_id: str = "") -> str:
    """Компактный JWT HS256. Ровно столько, сколько нужно подписи ссылки."""
    header = {"alg": "HS256", "typ": "JWT"}
    if key_id:
        header["kid"] = key_id
    segments = [
        _b64(json.dumps(header, separators=(",", ":"), sort_keys=True).encode()),
        _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()),
    ]
    signing_input = ".".join(segments).encode()
    signature = hmac.new(key.encode(), signing_input, hashlib.sha256).digest()
    segments.append(_b64(signature))
    return ".".join(segments)


def _kinescope_id(video_url: str) -> str:
    value = (video_url or "").strip().rstrip("/")
    if not value:
        return ""
    return value.rsplit("/", 1)[-1]


def _kinescope_claims(video_id: str, student, expires_at) -> dict:
    """Поля токена. Имена вынесены в настройку: контракт хостинга может
    отличаться, и подстраиваться под него должен конфиг, а не код."""
    names = dict(getattr(settings, "KINESCOPE_TOKEN_CLAIMS", {}) or {})
    now = timezone.now()
    claims = {
        names.get("video", "video_id"): video_id,
        names.get("expires", "exp"): int(expires_at.timestamp()),
        names.get("issued", "iat"): int(now.timestamp()),
        # Одноразовый идентификатор: по нему хостинг отличает выданные ссылки
        # друг от друга, а мы — находим выдачу в логах.
        names.get("nonce", "jti"): secrets.token_hex(8),
    }
    if student is not None:
        claims[names.get("subject", "sub")] = str(student.pk)
    return claims


def kinescope_link(lesson, student) -> VideoLink:
    video_id = _kinescope_id(lesson.video_url)
    if not video_id:
        return VideoLink("", lesson.video_provider, False, can_embed=False)

    base = f"https://kinescope.io/embed/{video_id}"
    key = getattr(settings, "KINESCOPE_SIGNING_KEY", "")
    if not key:
        # Ключа нет — ролик публичный. Врать об этом нельзя: подписка на такое
        # видео ничего не защищает, и это должно быть видно в ответе.
        return VideoLink(base, lesson.video_provider, False)

    expires_at = timezone.now() + timedelta(seconds=link_ttl())
    token = sign_jwt(
        _kinescope_claims(video_id, student, expires_at),
        key=key,
        key_id=getattr(settings, "KINESCOPE_KEY_ID", ""),
    )
    param = getattr(settings, "KINESCOPE_TOKEN_PARAM", "token") or "token"
    return VideoLink(
        f"{base}?{urlencode({param: token})}",
        lesson.video_provider,
        True,
        expires_at=expires_at,
    )


def public_link(lesson) -> VideoLink:
    url = (lesson.video_url or "").strip()
    return VideoLink(
        url, lesson.video_provider, False, can_embed=is_allowed_host(url) and url.startswith("https://")
    )


def playback_link(lesson, student=None) -> VideoLink:
    """Ссылка на воспроизведение для конкретного ученика."""
    if lesson.video_provider == lesson.VideoProvider.KINESCOPE:
        return kinescope_link(lesson, student)
    return public_link(lesson)
