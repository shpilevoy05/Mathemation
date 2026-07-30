"""Тарифы, подписки и платежи за реальные деньги.

Домен отделён от провайдера: платформа хранит тариф, подписку и платёж, а
конкретный эквайринг подключается через `settings.BILLING_PROVIDER` — так же,
как провайдер подсказок наставника. Пока подключён mock-провайдер: боевое
подключение требует ключей мерчанта, фискализации (54-ФЗ) и юридического
решения по оплате за несовершеннолетнего.

Ключевые правила:

* цена тарифа версионируется: изменение цены — новая версия тарифа, иначе
  нельзя объяснить, за что списали деньги полгода назад;
* платёж идемпотентен по `idempotency_key`: повторный клик и повторный
  колбэк провайдера не создают второй платёж и не продлевают подписку дважды;
* платит взрослый: у платежа есть плательщик, и для ученика младше 18 это
  родитель.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils import timezone


class Tariff(models.Model):
    """Версионируемый тариф: код + версия уникальны."""

    code = models.SlugField(max_length=64)
    version = models.PositiveSmallIntegerField(default=1)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price_rub = models.DecimalField(max_digits=10, decimal_places=2)
    period_days = models.PositiveSmallIntegerField(default=30)
    features = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="uniq_tariff_version"),
            models.CheckConstraint(
                condition=models.Q(price_rub__gte=Decimal("0")), name="tariff_price_non_negative"
            ),
        ]

    def __str__(self):
        return f"{self.title} v{self.version} ({self.price_rub} ₽)"


class Subscription(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        ACTIVE = "active"
        CANCELED = "canceled"
        EXPIRED = "expired"

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="subscriptions"
    )
    tariff = models.ForeignKey(Tariff, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student.user.username}: {self.tariff.title} ({self.status})"

    @property
    def is_active_now(self) -> bool:
        return (
            self.status == self.Status.ACTIVE
            and self.ends_at is not None
            and self.ends_at > timezone.now()
        )


class Payment(models.Model):
    class Status(models.TextChoices):
        CREATED = "created"
        SUCCEEDED = "succeeded"
        FAILED = "failed"
        REFUNDED = "refunded"

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.PROTECT, related_name="payments"
    )
    # Плательщик — взрослый: родитель или сам ученик, если он совершеннолетний.
    payer = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="payments"
    )
    tariff = models.ForeignKey(Tariff, on_delete=models.PROTECT, related_name="payments")
    subscription = models.ForeignKey(
        Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments"
    )
    amount_rub = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED)
    provider = models.CharField(max_length=64, blank=True)
    provider_payment_id = models.CharField(max_length=128, blank=True)
    # Ключ идемпотентности приходит от клиента: повторный клик по кнопке
    # оплаты не должен создавать второй платёж.
    idempotency_key = models.CharField(max_length=64, unique=True)
    receipt_url = models.URLField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.amount_rub} ₽ ({self.status})"
