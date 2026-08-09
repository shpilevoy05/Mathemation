"""Настройки и проверки безопасности.

Две функции, вызываемые из `config/settings.py`:

* :func:`hardening_settings` — значения security-настроек Django, зависящие
  от режима (dev или production);
* :func:`validate_production_config` — fail-fast: процесс с `DEBUG=0` не
  поднимается на dev-ключе, на `ALLOWED_HOSTS=*` или когда приватные файлы
  учеников лежат внутри публичного `MEDIA_ROOT`.

Логика вынесена из settings, чтобы её можно было проверить тестами.
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Ключ по умолчанию: годится только для локальной разработки и тестов.
DEV_SECRET_KEY = "dev-insecure-key"

HSTS_SECONDS = 31536000  # один год
# Требование Django к длине ключа (см. check --deploy, security.W009).
MIN_SECRET_KEY_LENGTH = 50


def hardening_settings(*, debug: bool, behind_proxy: bool = True) -> dict:
    """Security-настройки Django для текущего режима.

    В dev cookie-флаги и редирект на HTTPS выключены, иначе локальный сервер
    на http становится неработоспособным. Заголовки, не зависящие от схемы
    (`nosniff`, `X-Frame-Options`, referrer policy), включены всегда.
    """
    common = {
        "SECURE_CONTENT_TYPE_NOSNIFF": True,
        "SECURE_REFERRER_POLICY": "same-origin",
        "SECURE_CROSS_ORIGIN_OPENER_POLICY": "same-origin",
        "X_FRAME_OPTIONS": "DENY",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "CSRF_COOKIE_SAMESITE": "Lax",
    }
    if debug:
        return {
            **common,
            "SECURE_SSL_REDIRECT": False,
            "SECURE_HSTS_SECONDS": 0,
            "SECURE_HSTS_INCLUDE_SUBDOMAINS": False,
            "SECURE_HSTS_PRELOAD": False,
            "SESSION_COOKIE_SECURE": False,
            "CSRF_COOKIE_SECURE": False,
        }
    hardened = {
        **common,
        "SECURE_SSL_REDIRECT": True,
        "SECURE_HSTS_SECONDS": HSTS_SECONDS,
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": True,
        "SECURE_HSTS_PRELOAD": True,
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
    }
    if behind_proxy:
        # Терминация TLS на nginx: без этого Django считает запрос http
        # и уходит в бесконечный редирект.
        hardened["SECURE_PROXY_SSL_HEADER"] = ("HTTP_X_FORWARDED_PROTO", "https")
    return hardened


def _is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def validate_production_config(
    *,
    debug: bool,
    secret_key: str,
    allowed_hosts: list[str],
    private_media_root: os.PathLike | str | None = None,
    media_root: os.PathLike | str | None = None,
    database_engine: str | None = None,
    billing_provider: str | None = None,
    billing_webhook_secret: str | None = None,
) -> list[str]:
    """Проверить прод-конфигурацию. Возвращает список проблем и поднимает
    :class:`ImproperlyConfigured`, если он не пуст.

    В режиме `DEBUG=1` проверки не выполняются: это разработка.
    """
    if debug:
        return []

    problems: list[str] = []
    if not secret_key or secret_key == DEV_SECRET_KEY:
        problems.append(
            "DJANGO_SECRET_KEY не задан: с DEBUG=0 использовать ключ разработки нельзя."
        )
    elif len(secret_key) < MIN_SECRET_KEY_LENGTH or len(set(secret_key)) < 5:
        problems.append(
            "DJANGO_SECRET_KEY слишком слабый: нужно не менее %d символов и "
            "не менее 5 различных." % MIN_SECRET_KEY_LENGTH
        )
    if not allowed_hosts or any(host.strip() in ("", "*") for host in allowed_hosts):
        problems.append(
            "DJANGO_ALLOWED_HOSTS должен перечислять конкретные домены (не '*')."
        )
    if private_media_root and media_root and _is_inside(Path(private_media_root), Path(media_root)):
        problems.append(
            "PRIVATE_MEDIA_ROOT находится внутри MEDIA_ROOT: работы учеников "
            "будут раздаваться веб-сервером как статика."
        )
    # Молчаливый откат на SQLite — это файл рядом с кодом, блокировки на записи
    # и потеря данных при пересоздании контейнера. С DEBUG=0 это ошибка старта,
    # а не «работает и ладно».
    if database_engine and "sqlite" in database_engine:
        problems.append(
            "С DEBUG=0 база должна быть PostgreSQL: задайте POSTGRES_DB "
            "(и POSTGRES_USER/PASSWORD/HOST)."
        )

    # Боевой эквайринг без секрета подписи означает, что колбэк об оплате
    # может прислать кто угодно и получить подписку бесплатно.
    if (
        billing_provider
        and not billing_provider.endswith("MockPaymentProvider")
        and not billing_webhook_secret
    ):
        problems.append(
            "BILLING_WEBHOOK_SECRET не задан: колбэк эквайринга нечем проверить."
        )

    if problems:
        raise ImproperlyConfigured(
            "Небезопасная конфигурация production:\n- " + "\n- ".join(problems)
        )
    return problems
