"""Жизненный цикл платежа и подписки."""

from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Payment, Subscription, Tariff
from .providers import get_provider


def active_tariffs():
    """Актуальные тарифы: по последней версии каждого кода."""
    latest = {}
    for tariff in Tariff.objects.filter(is_active=True):
        current = latest.get(tariff.code)
        if current is None or tariff.version > current.version:
            latest[tariff.code] = tariff
    return sorted(latest.values(), key=lambda t: t.price_rub)


def new_tariff_version(tariff: Tariff, *, price_rub, **changes) -> Tariff:
    """Изменение цены — новая версия, старая уходит в архив.

    Так у каждого платежа остаётся тариф с той ценой, по которой платили.
    """
    updated = Tariff.objects.create(
        code=tariff.code,
        version=tariff.version + 1,
        title=changes.get("title", tariff.title),
        description=changes.get("description", tariff.description),
        price_rub=price_rub,
        period_days=changes.get("period_days", tariff.period_days),
        features=changes.get("features", tariff.features),
        is_active=True,
    )
    Tariff.objects.filter(pk=tariff.pk).update(is_active=False)
    return updated


@transaction.atomic
def start_payment(student, tariff: Tariff, payer, idempotency_key: str) -> tuple[Payment, str]:
    """Создать платёж и получить ссылку на оплату. Идемпотентно по ключу."""
    if not tariff.is_active:
        raise ValidationError("Тариф больше не продаётся.")
    if payer is None or not payer.is_authenticated:
        raise ValidationError("Плательщик не определён.")

    existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing, get_provider().create_payment(existing)

    payment = Payment.objects.create(
        student=student, payer=payer, tariff=tariff,
        amount_rub=tariff.price_rub, idempotency_key=idempotency_key,
    )
    return payment, get_provider().create_payment(payment)


@transaction.atomic
def confirm_payment(payment: Payment, *, provider_payment_id: str = "") -> Subscription:
    """Подтвердить оплату и продлить подписку. Повторный колбэк ничего не меняет."""
    caller_instance = payment
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status == Payment.Status.SUCCEEDED:
        caller_instance.refresh_from_db()
        return payment.subscription
    if payment.status == Payment.Status.REFUNDED:
        raise ValidationError("Платёж уже возвращён.")

    now = timezone.now()
    subscription = (
        Subscription.objects.filter(
            student=payment.student, tariff__code=payment.tariff.code,
            status=Subscription.Status.ACTIVE,
        )
        .order_by("-ends_at")
        .first()
    )
    period = timedelta(days=payment.tariff.period_days)
    if subscription is not None and subscription.ends_at and subscription.ends_at > now:
        # Продление: считаем от конца текущего периода, а не от сегодня.
        subscription.ends_at += period
        subscription.tariff = payment.tariff
        subscription.save(update_fields=["ends_at", "tariff"])
    else:
        subscription = Subscription.objects.create(
            student=payment.student, tariff=payment.tariff,
            status=Subscription.Status.ACTIVE, starts_at=now, ends_at=now + period,
        )

    payment.status = Payment.Status.SUCCEEDED
    payment.paid_at = now
    payment.subscription = subscription
    if provider_payment_id:
        payment.provider_payment_id = provider_payment_id
    payment.save(
        update_fields=["status", "paid_at", "subscription", "provider_payment_id"]
    )
    # Экземпляр вызывающего кода мог остаться со старым статусом: обновляем,
    # иначе следующий шаг (возврат, отчёт) увидит платёж неоплаченным.
    if caller_instance is not payment:
        caller_instance.refresh_from_db()
    return subscription


def handle_callback(payload: dict) -> Payment | None:
    """Обработать колбэк провайдера. Источник истины — провайдер, не клиент."""
    parsed = get_provider().parse_callback(payload)
    payment = Payment.objects.filter(
        idempotency_key=parsed.get("idempotency_key", "")
    ).first()
    if payment is None:
        return None
    if parsed.get("status") == "succeeded":
        confirm_payment(payment, provider_payment_id=parsed.get("provider_payment_id", ""))
    elif parsed.get("status") == "failed" and payment.status == Payment.Status.CREATED:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status"])
    return payment


@transaction.atomic
def refund_payment(payment: Payment) -> Payment:
    """Вернуть деньги и снять подписку, оплаченную этим платежом."""
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status != Payment.Status.SUCCEEDED:
        raise ValidationError("Возврат возможен только по оплаченному платежу.")
    get_provider().refund(payment)
    payment.status = Payment.Status.REFUNDED
    payment.refunded_at = timezone.now()
    payment.save(update_fields=["status", "refunded_at"])

    subscription = payment.subscription
    if subscription is not None:
        subscription.status = Subscription.Status.CANCELED
        subscription.ends_at = timezone.now()
        subscription.save(update_fields=["status", "ends_at"])
    return payment


def has_active_subscription(student) -> bool:
    return any(s.is_active_now for s in student.subscriptions.all())


def expire_subscriptions(now=None) -> int:
    """Джоб: перевести истёкшие подписки в expired. Идемпотентен."""
    now = now or timezone.now()
    return Subscription.objects.filter(
        status=Subscription.Status.ACTIVE, ends_at__lte=now
    ).update(status=Subscription.Status.EXPIRED)
