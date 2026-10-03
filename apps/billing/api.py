"""Колбэк эквайринга и состояние подписки для интерфейса.

Вебхук — единственная точка платформы, которая принимает запрос из интернета
без сессии и меняет деньги, поэтому у него отдельные правила:

* источник истины — подпись тела, а не содержимое JSON;
* тело читается сырым: подпись считается по байтам, а не по разобранному
  словарю (после `json.dumps` порядок ключей уже другой);
* повторная доставка обязана быть безопасной — идемпотентность обеспечивает
  `confirm_payment` по `idempotency_key`;
* неизвестный платёж не ошибка доставки: отвечаем 200, иначе провайдер будет
  ретраить вечно.
"""

from __future__ import annotations

import json
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, views
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.api import get_student

from .access import subscription_state
from .providers import get_provider
from .services import handle_callback

logger = logging.getLogger("matemacia.integrations")


@method_decorator(csrf_exempt, name="dispatch")
class PaymentWebhookView(views.APIView):
    """POST /api/billing/webhook/ — колбэк провайдера об оплате."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "webhook"

    def post(self, request):
        provider = get_provider()
        signature = request.headers.get(provider.signature_header, "")
        if not provider.verify_callback(request.body, signature):
            # Логируем как событие безопасности: подделка колбэка — попытка
            # получить подписку бесплатно.
            logging.getLogger("matemacia.security").warning(
                "billing.webhook.bad_signature provider=%s", provider.name
            )
            return Response({"detail": "Подпись не совпала."}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return Response({"detail": "Тело не разобрано."}, status=400)
        if not isinstance(payload, dict):
            return Response({"detail": "Тело не разобрано."}, status=400)

        payment = handle_callback(payload)
        if payment is None:
            logger.warning("billing.webhook.unknown_payment provider=%s", provider.name)
            return Response({"status": "ignored"})
        logger.info(
            "billing.webhook.handled payment=%s status=%s", payment.pk, payment.status
        )
        return Response({"status": payment.status})


class SubscriptionView(views.APIView):
    """GET /api/billing/subscription/ — что открыто ученику и до какого дня."""

    def get(self, request):
        student = get_student(request)
        state = subscription_state(student)
        subscription = state["subscription"]
        return Response({
            "enforced": state["enforced"],
            "is_active": state["is_active"],
            "in_trial": state["in_trial"],
            "trial_days_left": state["trial_days_left"],
            "days_left": state["days_left"],
            "ends_at": state["ends_at"],
            "tariff": {
                "code": subscription.tariff.code,
                "title": subscription.tariff.title,
            } if subscription is not None else None,
        })
