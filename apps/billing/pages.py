"""Публичная страница тарифов и оплаты.

Страница открыта без входа: цену смотрят родители до регистрации ученика.
Провайдер эквайринга пока не подключён, поэтому кнопка оплаты ведёт на
заглушку, а способы оплаты и акции настраивает администратор в панели.
"""

from django.shortcuts import render

from .models import PaymentMethod
from .services import active_payment_methods, active_tariffs, quote, running_promotions


def pricing_context(promo_code: str = "") -> dict:
    """Витрина: тарифы с учётом скидок, способы оплаты и текущие акции."""
    quotes = [quote(tariff, code=promo_code) for tariff in active_tariffs()]
    applied = next(
        (item["promotion"] for item in quotes if item["promotion"] is not None), None
    )
    return {
        "quotes": quotes,
        "payment_methods": active_payment_methods(),
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


def pricing(request):
    return render(request, "pricing.html", pricing_context(request.GET.get("promo", "")))
