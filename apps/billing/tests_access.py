"""Гейт подписки и колбэк эквайринга.

Тесты проверяют два разных обещания: платная часть закрыта тем, кто не платит,
и деньги признаются оплаченными только по подписи провайдера.
"""

import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.knowledge.tests import make_node, make_student
from apps.practice.tests import make_assignment

from .access import Feature, feature_access, subscription_state
from .models import Payment, Subscription, Tariff

ENFORCED = override_settings(BILLING_ENFORCED=True, TRIAL_DAYS=0, FREE_FEATURES=[])


def make_tariff(code="pro", price="1990.00", period_days=30) -> Tariff:
    return Tariff.objects.create(
        code=code, version=1, title=code, price_rub=Decimal(price),
        period_days=period_days,
    )


def give_subscription(student, *, days=30, status=Subscription.Status.ACTIVE):
    now = timezone.now()
    return Subscription.objects.create(
        student=student, tariff=make_tariff(f"t{student.pk}"), status=status,
        starts_at=now, ends_at=now + timedelta(days=days),
    )


@ENFORCED
class FeatureAccessTests(TestCase):
    def setUp(self):
        self.student = make_student("gate-student")

    def test_student_without_subscription_is_locked_out(self):
        access = feature_access(self.student.user, Feature.LESSONS)

        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "no_subscription")

    def test_active_subscription_opens_the_feature(self):
        give_subscription(self.student)

        access = feature_access(self.student.user, Feature.LESSONS)

        self.assertTrue(access.allowed)
        self.assertEqual(access.reason, "subscription")
        self.assertGreater(access.days_left, 0)

    def test_expired_subscription_is_a_separate_reason(self):
        subscription = give_subscription(self.student)
        subscription.ends_at = timezone.now() - timedelta(days=1)
        subscription.save(update_fields=["ends_at"])

        access = feature_access(self.student.user, Feature.LESSONS)

        # Продлить и купить впервые — разные разговоры с человеком.
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "expired")

    @override_settings(TRIAL_DAYS=7)
    def test_trial_opens_everything_until_it_runs_out(self):
        access = feature_access(self.student.user, Feature.MOCKS)
        self.assertTrue(access.allowed)
        self.assertEqual(access.reason, "trial")

        self.student.user.date_joined = timezone.now() - timedelta(days=8)
        self.student.user.save(update_fields=["date_joined"])

        self.assertFalse(feature_access(self.student.user, Feature.MOCKS).allowed)

    @override_settings(FREE_FEATURES=[Feature.PRACTICE])
    def test_free_feature_stays_open(self):
        self.assertTrue(feature_access(self.student.user, Feature.PRACTICE).allowed)
        self.assertFalse(feature_access(self.student.user, Feature.LESSONS).allowed)

    def test_staff_is_not_gated(self):
        methodist = User.objects.create_user("methodist-gate", role=User.Role.METHODIST)

        self.assertTrue(feature_access(methodist, Feature.LESSONS).allowed)

    def test_subscription_state_reports_trial_and_dates(self):
        with override_settings(TRIAL_DAYS=7):
            state = subscription_state(self.student)
        self.assertTrue(state["in_trial"])
        self.assertEqual(state["trial_days_left"], 7)

        give_subscription(self.student, days=10)
        state = subscription_state(self.student)
        self.assertTrue(state["is_active"])
        self.assertFalse(state["in_trial"])
        self.assertEqual(state["days_left"], 9)


class GateDisabledTests(TestCase):
    def test_nothing_is_gated_while_billing_is_off(self):
        student = make_student("free-student")

        self.assertTrue(feature_access(student.user, Feature.LESSONS).allowed)
        self.assertEqual(feature_access(student.user, Feature.LESSONS).reason, "free")


@ENFORCED
class GatedEndpointTests(TestCase):
    def setUp(self):
        self.student = make_student("api-gate-student")
        self.student.user.set_password("pwd12345")
        self.student.user.save()
        self.client.force_login(self.student.user)
        self.node = make_node("gate-node")
        self.assignment = make_assignment(self.node, answer="1")

    def test_attempt_is_refused_without_subscription(self):
        response = self.client.post(
            f"/api/assignments/{self.assignment.id}/attempt/",
            {"answer": "1"}, content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        # DRF отдаёт словарь отказа как есть: клиенту нужны и повод, и ссылка.
        payload = response.json()
        self.assertEqual(payload["code"], "subscription_required")
        self.assertEqual(payload["feature"], Feature.PRACTICE)
        self.assertEqual(payload["pricing_url"], "/pricing/")

    def test_attempt_passes_with_subscription(self):
        give_subscription(self.student)

        response = self.client.post(
            f"/api/assignments/{self.assignment.id}/attempt/",
            {"answer": "1"}, content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

    def test_lesson_page_sends_to_pricing(self):
        response = self.client.get(f"/lesson/{self.node.id}/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/pricing/", response["Location"])
        self.assertIn("locked=lessons", response["Location"])

    def test_free_page_stays_open(self):
        self.assertEqual(self.client.get("/map/").status_code, 200)

    def test_subscription_endpoint_reports_state(self):
        give_subscription(self.student, days=15)

        payload = self.client.get("/api/billing/subscription/").json()

        self.assertTrue(payload["is_active"])
        self.assertEqual(payload["days_left"], 14)


@override_settings(BILLING_WEBHOOK_SECRET="test-secret")
class WebhookTests(TestCase):
    def setUp(self):
        self.student = make_student("webhook-student")
        self.payer = User.objects.create_user("webhook-payer", role=User.Role.PARENT)
        self.tariff = make_tariff("webhook-pro")
        self.payment = Payment.objects.create(
            student=self.student, payer=self.payer, tariff=self.tariff,
            amount_rub=self.tariff.price_rub, idempotency_key="key-webhook-1",
        )
        self.url = reverse("billing-webhook")

    def body(self, **overrides) -> bytes:
        payload = {
            "idempotency_key": self.payment.idempotency_key,
            "status": "succeeded",
            "provider_payment_id": "provider-1",
        }
        payload.update(overrides)
        return json.dumps(payload).encode()

    def sign(self, body: bytes) -> str:
        return hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

    def post(self, body: bytes, signature: str | None = None):
        return self.client.post(
            self.url, body, content_type="application/json",
            HTTP_X_SIGNATURE=self.sign(body) if signature is None else signature,
        )

    def test_signed_callback_activates_the_subscription(self):
        response = self.post(self.body())

        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertTrue(self.student.subscriptions.filter(
            status=Subscription.Status.ACTIVE
        ).exists())

    def test_unsigned_callback_changes_nothing(self):
        response = self.post(self.body(), signature="")

        self.assertEqual(response.status_code, 403)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.CREATED)

    def test_forged_signature_is_rejected(self):
        response = self.post(self.body(), signature="0" * 64)

        self.assertEqual(response.status_code, 403)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.CREATED)

    def test_repeated_delivery_does_not_extend_twice(self):
        self.post(self.body())
        first_end = self.student.subscriptions.get().ends_at

        self.post(self.body())

        self.assertEqual(self.student.subscriptions.get().ends_at, first_end)

    def test_unknown_payment_is_acknowledged_not_retried(self):
        response = self.post(self.body(idempotency_key="missing-key"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ignored")

    @override_settings(BILLING_WEBHOOK_SECRET="")
    def test_callback_is_refused_when_no_secret_is_configured(self):
        response = self.post(self.body(), signature="whatever")

        self.assertEqual(response.status_code, 403)
