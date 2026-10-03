"""Настройка и проверка второго фактора.

Правила домена собраны здесь, а не во вьюхах: тот же порядок нужен и странице
входа, и Django-админке, и будущему API. Ключевое правило — фактор считается
настроенным только после того, как человек ввёл код с телефона: секрет,
записанный с ошибкой, иначе превращается в потерянный доступ.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from .models import TwoFactorDevice
from .two_factor import (
    generate_recovery_codes,
    generate_secret,
    hash_recovery_code,
    verify_code,
)

logger = logging.getLogger("matemacia.security")

# Флаг в сессии: фактор пройден. Живёт ровно столько, сколько сессия.
SESSION_FLAG = "two_factor_passed"


def get_device(user) -> TwoFactorDevice | None:
    return TwoFactorDevice.objects.filter(user=user).first()


def start_enrollment(user) -> TwoFactorDevice:
    """Выдать (или перевыдать) секрет. Пока код не подтверждён, доступ не меняется."""
    device = get_device(user)
    if device is not None and device.is_confirmed:
        return device
    if device is None:
        device = TwoFactorDevice(user=user)
    device.secret = generate_secret()
    device.last_step = 0
    device.recovery_hashes = []
    device.save()
    return device


@transaction.atomic
def confirm_enrollment(user, code: str) -> list[str] | None:
    """Подтвердить настройку кодом с телефона. Возвращает резервные коды.

    Коды показываются один раз: в базе лежат только их хеши.
    """
    device = TwoFactorDevice.objects.select_for_update().filter(user=user).first()
    if device is None or device.is_confirmed:
        return None
    step = verify_code(device.secret, code, after_step=device.last_step)
    if step is None:
        return None
    recovery = generate_recovery_codes()
    device.confirmed_at = timezone.now()
    device.last_step = step
    device.last_used_at = timezone.now()
    device.recovery_hashes = [hash_recovery_code(item) for item in recovery]
    device.save(update_fields=[
        "confirmed_at", "last_step", "last_used_at", "recovery_hashes"
    ])
    logger.info("two_factor.enrolled user=%s", user.pk)
    return recovery


@transaction.atomic
def check_code(user, code: str) -> bool:
    """Проверить код при входе. Принимает и одноразовый код, и резервный."""
    device = TwoFactorDevice.objects.select_for_update().filter(user=user).first()
    if device is None or not device.is_confirmed:
        return False

    step = verify_code(device.secret, code, after_step=device.last_step)
    if step is not None:
        device.last_step = step
        device.last_used_at = timezone.now()
        device.save(update_fields=["last_step", "last_used_at"])
        return True

    # Резервный код: одноразовый, поэтому сразу вычёркивается.
    digest = hash_recovery_code(code)
    remaining = list(device.recovery_hashes or [])
    if digest in remaining:
        remaining.remove(digest)
        device.recovery_hashes = remaining
        device.last_used_at = timezone.now()
        device.save(update_fields=["recovery_hashes", "last_used_at"])
        logger.warning(
            "two_factor.recovery_used user=%s left=%s", user.pk, len(remaining)
        )
        return True
    return False


@transaction.atomic
def reset_device(user, *, actor=None) -> bool:
    """Снять фактор (потерян телефон и резервные коды).

    Это возврат к одному паролю, поэтому действие пишется в аудит: у него
    должен быть автор и повод.
    """
    from apps.adminpanel.audit import log_admin_action

    deleted, _ = TwoFactorDevice.objects.filter(user=user).delete()
    if not deleted:
        return False
    # В журнале только идентификатор: логин — персональные данные, а событие
    # хранится долго (см. проверку в `log_event`).
    log_admin_action(actor, "two_factor.reset", target=f"user:{user.pk}")
    return True


def mark_session_passed(request) -> None:
    request.session[SESSION_FLAG] = True


def session_passed(request) -> bool:
    return bool(request.session.get(SESSION_FLAG))
