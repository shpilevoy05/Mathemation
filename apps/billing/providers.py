"""Интерфейс платёжного провайдера.

Провайдер выбирается настройкой `BILLING_PROVIDER` (dotted path), поэтому
эквайринг подключается без изменения доменного кода. Любой провайдер обязан:

* создавать платёж по нашему `idempotency_key` и возвращать ссылку на оплату;
* уметь разобрать колбэк и сказать, оплачено ли (без доверия к клиенту);
* поддерживать возврат.

Боевой провайдер дополнительно обязан фискализировать чек (54-ФЗ) — это
делается на его стороне и требует данных мерчанта.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from django.conf import settings
from django.utils.module_loading import import_string


class PaymentProvider(ABC):
    name = "abstract"

    @abstractmethod
    def create_payment(self, payment) -> str:
        """Создать платёж на стороне провайдера, вернуть ссылку на оплату."""

    @abstractmethod
    def parse_callback(self, payload: dict) -> dict:
        """Разобрать колбэк: {'idempotency_key', 'status', 'provider_payment_id'}."""

    def refund(self, payment) -> bool:
        """Вернуть деньги. По умолчанию не поддерживается."""
        raise NotImplementedError("Провайдер не поддерживает возвраты.")


class MockPaymentProvider(PaymentProvider):
    """Провайдер для разработки и тестов: платёж считается созданным сразу.

    Реальные деньги не двигаются. В проде подменяется настройкой
    `BILLING_PROVIDER`.
    """

    name = "mock"

    def create_payment(self, payment) -> str:
        payment.provider = self.name
        payment.provider_payment_id = f"mock-{payment.idempotency_key}"
        payment.save(update_fields=["provider", "provider_payment_id"])
        return f"https://payments.example/mock/{payment.provider_payment_id}"

    def parse_callback(self, payload: dict) -> dict:
        return {
            "idempotency_key": payload.get("idempotency_key", ""),
            "status": payload.get("status", ""),
            "provider_payment_id": payload.get("provider_payment_id", ""),
        }

    def refund(self, payment) -> bool:
        return True


def get_provider() -> PaymentProvider:
    return import_string(settings.BILLING_PROVIDER)()
