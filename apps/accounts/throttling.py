"""Защита от перебора: логин и коды приглашений.

DRF-троттлинг закрывает API, но вход и регистрация — обычные формы Django,
поэтому лимит для них живёт здесь. Счётчик хранится в общем кеше: у каждого
воркера свой локальный кеш, и без общего хранилища лимит перестаёт быть
лимитом (см. `CACHES` в настройках).

Ключ — пара «действие + отправитель». Для входа отправитель это IP и логин
одновременно: по одному IP могут сидеть все ученики школы, а один логин могут
подбирать с разных адресов.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("matemacia.security")

# Значения по умолчанию: осмысленный человек в них укладывается, скрипт — нет.
DEFAULTS = {
    "LOGIN_MAX_ATTEMPTS": 10,
    "LOGIN_BLOCK_SECONDS": 15 * 60,
    "INVITE_MAX_ATTEMPTS": 20,
    "INVITE_BLOCK_SECONDS": 60 * 60,
}


def client_ip(request) -> str:
    """IP отправителя с учётом обратного прокси."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


class BruteForceGuard:
    """Счётчик неудачных попыток с блокировкой на время."""

    def __init__(self, action: str, max_attempts_setting: str, block_setting: str):
        self.action = action
        self._max_attempts_setting = max_attempts_setting
        self._block_setting = block_setting

    @property
    def max_attempts(self) -> int:
        return int(getattr(settings, self._max_attempts_setting, DEFAULTS[self._max_attempts_setting]))

    @property
    def block_seconds(self) -> int:
        return int(getattr(settings, self._block_setting, DEFAULTS[self._block_setting]))

    def _key(self, sender: str) -> str:
        return f"guard:{self.action}:{sender}"

    def is_blocked(self, senders: list[str]) -> bool:
        return any(
            cache.get(self._key(sender), 0) >= self.max_attempts for sender in senders
        )

    def register_failure(self, senders: list[str]) -> None:
        """Записать неудачу. Окно продлевается от последней попытки."""
        for sender in senders:
            key = self._key(sender)
            attempts = cache.get(key, 0) + 1
            cache.set(key, attempts, timeout=self.block_seconds)
            if attempts == self.max_attempts:
                logger.warning(
                    "brute force blocked: action=%s sender=%s attempts=%s",
                    self.action, sender, attempts,
                )

    def reset(self, senders: list[str]) -> None:
        """Успех снимает счётчик: человек вспомнил пароль, а не подобрал его."""
        for sender in senders:
            cache.delete(self._key(sender))


login_guard = BruteForceGuard("login", "LOGIN_MAX_ATTEMPTS", "LOGIN_BLOCK_SECONDS")
invite_guard = BruteForceGuard("invite", "INVITE_MAX_ATTEMPTS", "INVITE_BLOCK_SECONDS")
