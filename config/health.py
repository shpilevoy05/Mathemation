"""Проверка живости для балансировщика и деплоя.

Две ручки. `/healthz` отвечает, что процесс жив, — её опрашивает балансировщик
часто, поэтому она ничего не трогает. `/readyz` проверяет зависимости (база и
кеш) и используется деплоем, чтобы не пускать трафик в контейнер с оборванным
соединением.
"""

import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger("matemacia.integrations")


def healthz(request):
    return JsonResponse({"status": "ok"})


def readyz(request):
    checks: dict[str, str] = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 — ответ важнее типа ошибки
        logger.error("readiness: database unavailable (%s)", type(exc).__name__)
        checks["database"] = "fail"
    try:
        cache.set("readyz", "1", timeout=5)
        checks["cache"] = "ok" if cache.get("readyz") == "1" else "fail"
    except Exception as exc:  # noqa: BLE001
        logger.error("readiness: cache unavailable (%s)", type(exc).__name__)
        checks["cache"] = "fail"

    ready = all(value == "ok" for value in checks.values())
    return JsonResponse({"status": "ok" if ready else "fail", "checks": checks},
                        status=200 if ready else 503)
