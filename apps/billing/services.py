"""Жизненный цикл платежа и подписки."""

from __future__ import annotations

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from decimal import Decimal

from .models import AddOn, Payment, PaymentMethod, Promotion, Subscription, Tariff
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


def active_payment_methods():
    """Способы оплаты для витрины, в порядке, заданном администратором."""
    return list(PaymentMethod.objects.filter(is_active=True))


def active_addons():
    """Докупки сверх тарифа: проверка эксперта и подсказки наставника."""
    return list(AddOn.objects.filter(is_active=True))


def running_promotions(now=None):
    """Действующие акции: по сроку, активности и остатку применений."""
    return [promotion for promotion in Promotion.objects.all() if promotion.is_running(now)]


def promotion_by_code(code: str, now=None) -> Promotion | None:
    """Найти акцию по промокоду. Регистр кода не важен."""
    code = (code or "").strip()
    if not code:
        return None
    promotion = Promotion.objects.filter(code__iexact=code).first()
    return promotion if promotion is not None and promotion.is_running(now) else None


def best_promotion(tariff: Tariff, *, code: str = "", now=None) -> Promotion | None:
    """Лучшая для ученика акция: введённый промокод или автоматическая скидка.

    Промокод имеет приоритет: если человек его ввёл и он подходит, показываем
    именно его, даже когда автоматическая акция выгоднее — иначе непонятно,
    сработал код или нет.
    """
    requested = promotion_by_code(code, now)
    if requested is not None and requested.applies_to(tariff):
        return requested
    automatic = [
        promotion for promotion in running_promotions(now)
        if not promotion.code and promotion.applies_to(tariff)
    ]
    if not automatic:
        return None
    return max(automatic, key=lambda promotion: promotion.discount_for(tariff.price_rub))


def quote(tariff: Tariff, *, code: str = "", now=None) -> dict:
    """Итоговая цена тарифа со скидкой: база, скидка, к оплате."""
    promotion = best_promotion(tariff, code=code, now=now)
    discount = promotion.discount_for(tariff.price_rub) if promotion else Decimal("0.00")
    return {
        "tariff": tariff,
        "base_rub": tariff.price_rub,
        "discount_rub": discount,
        "total_rub": (tariff.price_rub - discount).quantize(Decimal("0.01")),
        "promotion": promotion,
    }


@transaction.atomic
def start_payment(
    student, tariff: Tariff, payer, idempotency_key: str,
    *, promo_code: str = "", method: PaymentMethod | None = None,
) -> tuple[Payment, str]:
    """Создать платёж и получить ссылку на оплату. Идемпотентно по ключу."""
    if not tariff.is_active:
        raise ValidationError("Тариф больше не продаётся.")
    if payer is None or not payer.is_authenticated:
        raise ValidationError("Плательщик не определён.")
    if method is not None and not method.is_active:
        raise ValidationError("Способ оплаты сейчас недоступен.")

    existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing, get_provider().create_payment(existing)

    priced = quote(tariff, code=promo_code)
    promotion = priced["promotion"]
    metadata = {}
    if promotion is not None:
        metadata["promotion"] = {
            "id": promotion.id, "title": promotion.title, "code": promotion.code,
            "discount_rub": str(priced["discount_rub"]),
        }
        # Счётчик двигаем только при создании платежа: повторный клик по кнопке
        # попадает в ветку идемпотентности выше и лимит акции не тратит.
        Promotion.objects.filter(pk=promotion.pk).update(used_count=models.F("used_count") + 1)
    if method is not None:
        metadata["payment_method"] = method.code

    payment = Payment.objects.create(
        student=student, payer=payer, tariff=tariff,
        amount_rub=priced["total_rub"], idempotency_key=idempotency_key,
        provider=method.provider_key if method is not None else "",
        metadata=metadata,
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
