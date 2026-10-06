"""Платежи и подписки: идемпотентность, продление, возврат, версии цен."""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.knowledge.tests import make_student

from .models import Payment, Subscription, Tariff
from .services import (
    active_tariffs,
    confirm_payment,
    expire_subscriptions,
    handle_callback,
    has_active_subscription,
    new_tariff_version,
    refund_payment,
    start_payment,
)


class TariffVersionTests(TestCase):
    def setUp(self):
        self.tariff = Tariff.objects.create(
            code="pro", version=1, title="Про", price_rub=Decimal("1990.00")
        )

    def test_price_change_creates_new_version_and_archives_old(self):
        updated = new_tariff_version(self.tariff, price_rub=Decimal("2490.00"))
        self.tariff.refresh_from_db()
        self.assertEqual(updated.version, 2)
        self.assertFalse(self.tariff.is_active)
        self.assertEqual([t.pk for t in active_tariffs()], [updated.pk])

    def test_old_payments_keep_their_price(self):
        student = make_student("price-student")
        payer = User.objects.create_user("payer1", role=User.Role.PARENT)
        payment, _ = start_payment(student, self.tariff, payer, "key-1")
        new_tariff_version(self.tariff, price_rub=Decimal("2490.00"))
        payment.refresh_from_db()
        self.assertEqual(payment.amount_rub, Decimal("1990.00"))
        self.assertEqual(payment.tariff.version, 1)


class PaymentFlowTests(TestCase):
    def setUp(self):
        self.student = make_student("pay-student")
        self.payer = User.objects.create_user("payer2", role=User.Role.PARENT)
        self.tariff = Tariff.objects.create(
            code="base", version=1, title="Базовый",
            price_rub=Decimal("990.00"), period_days=30,
        )

    def test_start_payment_returns_link_and_is_idempotent(self):
        payment, url = start_payment(self.student, self.tariff, self.payer, "key-a")
        again, _ = start_payment(self.student, self.tariff, self.payer, "key-a")
        self.assertEqual(payment.pk, again.pk)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertIn("mock", url)

    def test_inactive_tariff_cannot_be_bought(self):
        self.tariff.is_active = False
        self.tariff.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            start_payment(self.student, self.tariff, self.payer, "key-b")

    def test_confirmation_activates_subscription(self):
        payment, _ = start_payment(self.student, self.tariff, self.payer, "key-c")
        subscription = confirm_payment(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertTrue(has_active_subscription(self.student))

    def test_repeated_callback_does_not_extend_twice(self):
        payment, _ = start_payment(self.student, self.tariff, self.payer, "key-d")
        first = confirm_payment(payment)
        ends_at = first.ends_at
        confirm_payment(payment)
        first.refresh_from_db()
        self.assertEqual(first.ends_at, ends_at)
        self.assertEqual(Subscription.objects.count(), 1)

    def test_second_payment_extends_from_current_end(self):
        first_payment, _ = start_payment(self.student, self.tariff, self.payer, "key-e")
        subscription = confirm_payment(first_payment)
        first_end = subscription.ends_at

        second_payment, _ = start_payment(self.student, self.tariff, self.payer, "key-f")
        subscription = confirm_payment(second_payment)
        self.assertEqual(subscription.ends_at, first_end + timedelta(days=30))
        self.assertEqual(Subscription.objects.count(), 1)

    def test_callback_marks_failure(self):
        payment, _ = start_payment(self.student, self.tariff, self.payer, "key-g")
        handle_callback({"idempotency_key": "key-g", "status": "failed"})
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertFalse(has_active_subscription(self.student))

    def test_callback_confirms_payment(self):
        payment, _ = start_payment(self.student, self.tariff, self.payer, "key-h")
        handle_callback(
            {"idempotency_key": "key-h", "status": "succeeded", "provider_payment_id": "x1"}
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(payment.provider_payment_id, "x1")

    def test_unknown_callback_is_ignored(self):
        self.assertIsNone(handle_callback({"idempotency_key": "nope", "status": "succeeded"}))

    def test_refund_cancels_subscription(self):
        payment, _ = start_payment(self.student, self.tariff, self.payer, "key-i")
        confirm_payment(payment)
        refund_payment(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REFUNDED)
        self.assertFalse(has_active_subscription(self.student))

    def test_refund_requires_successful_payment(self):
        payment, _ = start_payment(self.student, self.tariff, self.payer, "key-j")
        with self.assertRaises(ValidationError):
            refund_payment(payment)

    def test_confirm_after_refund_rejected(self):
        payment, _ = start_payment(self.student, self.tariff, self.payer, "key-k")
        confirm_payment(payment)
        refund_payment(payment)
        with self.assertRaises(ValidationError):
            confirm_payment(payment)

    def test_expire_job_is_idempotent(self):
        payment, _ = start_payment(self.student, self.tariff, self.payer, "key-l")
        subscription = confirm_payment(payment)
        subscription.ends_at = timezone.now() - timedelta(days=1)
        subscription.save(update_fields=["ends_at"])
        self.assertEqual(expire_subscriptions(), 1)
        self.assertEqual(expire_subscriptions(), 0)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.EXPIRED)
