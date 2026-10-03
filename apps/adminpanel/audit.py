"""Журнал действий администратора.

Панель правит цены, публикует уроки, выдаёт домашки и начисляет сигмы. Через
месяц вопрос «кто поменял цену» встанет обязательно, а ответа в базе нет:
модели хранят текущее состояние, но не автора изменения. Пишем в тот же
append-only лог событий, что и учебные действия, — отдельная таблица для этого
не нужна и разъедется с ним по хранению.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("matemacia.security")

# Что считаем существенным: всё, что меняет деньги, доступ или видимость
# контента. Обычная правка описания в журнал не идёт — он должен читаться.
AUDITED_ACTIONS = {
    "lesson.publish", "lesson.unpublish",
    "lesson.save", "assignment.save", "assignment.new_version",
    "knowledge_node.save", "knowledge_dependency.add", "knowledge_dependency.delete",
    "daily_challenge.save", "daily_challenge.delete",
    "tariff.details", "addon.save", "diagnostic.save", "mock.save",
    "homework.assign",
    "student.deactivate", "student.reactivate", "student.grant_coins",
    "tariff.new_version",
    "payment.refund",
    "invite.create",
    "promotion.save", "payment_method.save", "addon.save",
    # Снятие второго фактора возвращает сотрудника к одному паролю.
    "two_factor.reset",
    "account.temporary_password",
    "data_deletion.complete", "feedback.update",
}


def log_admin_action(actor, action: str, *, target: str = "", **payload) -> None:
    """Записать действие администратора в лог событий и в логи процесса."""
    from apps.events.models import Event
    from apps.events.services import log_event

    log_event(
        Event.Type.ADMIN_ACTION,
        student=payload.pop("student", None),
        action=action,
        target=target,
        actor_id=getattr(actor, "id", None),
        actor=getattr(actor, "username", ""),
        **payload,
    )
    logger.info(
        "admin action: actor=%s action=%s target=%s",
        getattr(actor, "username", "anonymous"), action, target,
    )
