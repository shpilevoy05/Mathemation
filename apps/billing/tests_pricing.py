"""Витрина тарифов: скидки, акции, способы оплаты и страница /pricing/."""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentProfile, User

from .models import Payment, PaymentMethod, Promotion, Tariff
from .services import (
    active_payment_methods,
    best_promotion,
    promotion_by_code,
    quote,
    running_promotions,
    start_payment,
)


def make_tariff(code="solo", price="2900.00", **extra):
    return Tariff.objects.create(
        code=code, title=f"Тариф {code}", price_rub=Decimal(price), **extra
    )


class PromotionRulesTests(TestCase):
    def setUp(self):
        self.tariff = make_tariff()

    def test_percent_promotion_discounts_the_price(self):
        promotion = Promotion.objects.create(
            title="Первый месяц", kind=Promotion.Kind.PERCENT, value=10
        )

        self.assertEqual(promotion.discount_for(self.tariff.price_rub), Decimal("290.00"))

    def test_fixed_promotion_never_exceeds_the_price(self):
        promotion = Promotion.objects.create(
            title="Подарок", kind=Promotion.Kind.FIXED, value=5000
        )

        self.assertEqual(promotion.discount_for(self.tariff.price_rub), Decimal("2900.00"))

    def test_expired_and_exhausted_promotions_do_not_run(self):
        expired = Promotion.objects.create(
            title="Вчерашняя", value=10, ends_at=timezone.now() - timedelta(hours=1)
        )
        exhausted = Promotion.objects.create(
            title="Кончилась", value=10, max_uses=2, used_count=2
        )
        future = Promotion.objects.create(
            title="Завтрашняя", value=10, starts_at=timezone.now() + timedelta(days=1)
        )
        live = Promotion.objects.create(title="Идёт", value=10)

        self.assertEqual(running_promotions(), [live])
        for promotion in (expired, exhausted, future):
            with self.subTest(promotion=promotion.title):
                self.assertFalse(promotion.is_running())

    def test_promotion_limited_to_other_tariffs_is_skipped(self):
        Promotion.objects.create(title="Только интенсив", value=20, tariff_codes=["intensive"])

        self.assertIsNone(best_promotion(self.tariff))

    def test_promo_code_wins_over_automatic_sale(self):
        Promotion.objects.create(title="Автоскидка", value=5)
        Promotion.objects.create(title="По коду", code="START10", value=10)

        priced = quote(self.tariff, code="start10")

        self.assertEqual(priced["promotion"].code, "START10")
        self.assertEqual(priced["total_rub"], Decimal("2610.00"))

    def test_unknown_code_falls_back_to_the_automatic_sale(self):
        Promotion.objects.create(title="Автоскидка", value=5)

        priced = quote(self.tariff, code="НЕТ-ТАКОГО")

        self.assertEqual(priced["promotion"].title, "Автоскидка")
        self.assertIsNone(promotion_by_code("НЕТ-ТАКОГО"))

    def test_quote_without_promotions_keeps_the_base_price(self):
        priced = quote(self.tariff)

        self.assertIsNone(priced["promotion"])
        self.assertEqual(priced["discount_rub"], Decimal("0.00"))
        self.assertEqual(priced["total_rub"], Decimal("2900.00"))


class PaymentWithPromotionTests(TestCase):
    def setUp(self):
        self.tariff = make_tariff()
        self.payer = User.objects.create_user("pricing-parent")
        self.student = StudentProfile.objects.create(
            user=User.objects.create_user("pricing-student")
        )
        self.method = PaymentMethod.objects.create(code="card", title="Карта")

    def test_payment_is_created_with_the_discounted_amount(self):
        promotion = Promotion.objects.create(title="По коду", code="START10", value=10)

        payment, _url = start_payment(
            self.student, self.tariff, self.payer, "key-1", promo_code="START10",
            method=self.method,
        )

        self.assertEqual(payment.amount_rub, Decimal("2610.00"))
        self.assertEqual(payment.metadata["promotion"]["id"], promotion.id)
        self.assertEqual(payment.metadata["payment_method"], "card")
        promotion.refresh_from_db()
        self.assertEqual(promotion.used_count, 1)

    def test_repeated_click_does_not_spend_the_promotion_twice(self):
        promotion = Promotion.objects.create(title="По коду", code="START10", value=10, max_uses=1)

        start_payment(self.student, self.tariff, self.payer, "key-2", promo_code="START10")
        start_payment(self.student, self.tariff, self.payer, "key-2", promo_code="START10")

        promotion.refresh_from_db()
        self.assertEqual(promotion.used_count, 1)
        self.assertEqual(Payment.objects.count(), 1)

    def test_disabled_payment_method_is_rejected(self):
        self.method.is_active = False
        self.method.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            start_payment(self.student, self.tariff, self.payer, "key-3", method=self.method)

    def test_inactive_methods_are_hidden_from_the_storefront(self):
        PaymentMethod.objects.create(code="sbp", title="СБП", is_active=False)

        self.assertEqual([method.code for method in active_payment_methods()], ["card"])


class PricingPageTests(TestCase):
    def setUp(self):
        self.tariff = make_tariff(price="2900.00")
        make_tariff(code="expert", price="5900.00")
        PaymentMethod.objects.create(
            code="sbp", title="СБП по QR-коду", instructions="Куратор пришлёт QR-код."
        )

    def test_page_is_public_and_lists_tariffs_and_methods(self):
        response = self.client.get(reverse("pricing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Тариф solo")
        self.assertContains(response, "СБП по QR-коду")
        self.assertEqual(len(response.context["quotes"]), 2)

    def test_checkout_is_a_placeholder_until_a_provider_is_configured(self):
        response = self.client.get(reverse("pricing"))

        self.assertFalse(response.context["checkout_enabled"])
        self.assertContains(response, "Оплата скоро")

    def test_configured_provider_enables_the_checkout_button(self):
        PaymentMethod.objects.filter(code="sbp").update(provider_key="mock")

        response = self.client.get(reverse("pricing"))

        self.assertTrue(response.context["checkout_enabled"])
        self.assertNotContains(response, "Оплата скоро")

    def test_promo_code_from_the_query_lowers_the_shown_price(self):
        Promotion.objects.create(title="Первый месяц", code="START10", value=10)

        response = self.client.get(reverse("pricing"), {"promo": "START10"})

        self.assertTrue(response.context["promo_applied"])
        self.assertEqual(response.context["quotes"][0]["total_rub"], Decimal("2610.00"))

    def test_wrong_promo_code_is_reported_without_breaking_prices(self):
        response = self.client.get(reverse("pricing"), {"promo": "НЕТ"})

        self.assertTrue(response.context["promo_failed"])
        self.assertEqual(response.context["quotes"][0]["total_rub"], Decimal("2900.00"))

    def test_running_promotions_are_announced(self):
        Promotion.objects.create(title="Первый месяц −10%", code="START10", value=10)

        response = self.client.get(reverse("pricing"))

        self.assertContains(response, "Первый месяц")
        self.assertContains(response, "START10")
