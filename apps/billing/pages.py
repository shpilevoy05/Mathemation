"""Публичная страница тарифов и оплаты.

Страница открыта без входа: цену смотрят родители до регистрации ученика.
Провайдер эквайринга пока не подключён, поэтому кнопка оплаты ведёт на
заглушку, а способы оплаты и акции настраивает администратор в панели.
"""

from django.shortcuts import render

from .access import FEATURE_TITLES, LOCKED_EXPIRED, subscription_state
from .models import PaymentMethod
from .services import (
    active_addons,
    active_payment_methods,
    active_tariffs,
    quote,
    running_promotions,
)


def pricing_context(promo_code: str = "") -> dict:
    """Витрина: тарифы с учётом скидок, способы оплаты и текущие акции."""
    quotes = [quote(tariff, code=promo_code) for tariff in active_tariffs()]
    applied = next(
        (item["promotion"] for item in quotes if item["promotion"] is not None), None
    )
    return {
        "quotes": quotes,
        "payment_methods": active_payment_methods(),
        "addons": active_addons(),
        "promotions": running_promotions(),
        "promo_code": promo_code,
        "promo_applied": applied is not None and bool(promo_code),
        "promo_failed": bool(promo_code) and not any(
            item["promotion"] is not None and item["promotion"].code.lower() == promo_code.strip().lower()
            for item in quotes
        ),
        "checkout_enabled": PaymentMethod.objects.filter(is_active=True)
        .exclude(provider_key="")
        .exists(),
    }


def _lock_context(request) -> dict:
    """Пришёл ли человек с закрытой страницы и что именно ему закрыли."""
    feature = request.GET.get("locked", "")
    if feature not in FEATURE_TITLES:
        return {"locked_feature": ""}
    expired = request.GET.get("reason") == LOCKED_EXPIRED
    return {
        "locked_feature": feature,
        "locked_title": FEATURE_TITLES[feature],
        "locked_expired": expired,
        "locked_message": (
            "Подписка закончилась. Прогресс сохранён — продлите доступ, и занятия "
            "откроются с того же места."
            if expired
            else "Эта часть платформы входит в подписку."
        ),
    }


def pricing(request):
    context = pricing_context(request.GET.get("promo", ""))
    context.update(_lock_context(request))
    student = getattr(request.user, "student_profile", None)
    context["subscription_state"] = subscription_state(student) if student else None
    return render(request, "pricing.html", context)
