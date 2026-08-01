"""Валюта, реестр и магазин: идемпотентность и запрет ухода в минус."""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.content.models import DailyChallenge
from apps.knowledge.tests import make_node, make_student
from apps.practice.tests import make_assignment

from .models import InventoryItem, LedgerEntry, ShopItem, Wallet
from .services import (
    equip,
    equipped_items,
    get_wallet,
    grant,
    purchase,
    reward_for_xp,
    spend,
    storefront,
    wallet_summary,
)


class WalletTests(TestCase):
    def setUp(self):
        self.student = make_student("wallet-student")

    def test_wallet_created_on_demand_with_zero_balance(self):
        self.assertEqual(get_wallet(self.student).balance, 0)

    def test_grant_increases_balance_and_records_entry(self):
        entry = grant(self.student, 30, LedgerEntry.Reason.ADMIN_GRANT, "manual:1")
        self.assertEqual(entry.balance_after, 30)
        self.assertEqual(get_wallet(self.student).balance, 30)

    def test_grant_is_idempotent_per_event(self):
        grant(self.student, 30, LedgerEntry.Reason.ADMIN_GRANT, "manual:1")
        grant(self.student, 30, LedgerEntry.Reason.ADMIN_GRANT, "manual:1")
        self.assertEqual(get_wallet(self.student).balance, 30)
        self.assertEqual(LedgerEntry.objects.count(), 1)

    def test_different_reference_grants_twice(self):
        grant(self.student, 10, LedgerEntry.Reason.ADMIN_GRANT, "manual:1")
        grant(self.student, 10, LedgerEntry.Reason.ADMIN_GRANT, "manual:2")
        self.assertEqual(get_wallet(self.student).balance, 20)

    def test_balance_cannot_go_negative(self):
        grant(self.student, 10, LedgerEntry.Reason.ADMIN_GRANT, "manual:1")
        with self.assertRaises(ValidationError):
            spend(self.student, 25, LedgerEntry.Reason.PURCHASE, "item:99")
        self.assertEqual(get_wallet(self.student).balance, 10)

    def test_zero_and_negative_grants_rejected(self):
        for amount in (0, -5):
            with self.subTest(amount=amount):
                with self.assertRaises(ValidationError):
                    grant(self.student, amount, LedgerEntry.Reason.ADMIN_GRANT, "x")

    def test_summary_splits_earned_and_spent(self):
        grant(self.student, 50, LedgerEntry.Reason.ADMIN_GRANT, "manual:1")
        spend(self.student, 20, LedgerEntry.Reason.PURCHASE, "item:1")
        self.assertEqual(
            wallet_summary(self.student), {"balance": 30, "earned": 50, "spent": 20}
        )


class XpRewardTests(TestCase):
    """Монеты идут за тем же событием, что и XP, и ровно один раз."""

    def setUp(self):
        self.student = make_student("reward-student")

    def test_coins_follow_xp_award(self):
        reward_for_xp(self.student, source="attempt", amount_xp=10, total_xp=10)
        self.assertEqual(get_wallet(self.student).balance, 10)

    def test_same_xp_event_pays_once(self):
        for _ in range(2):
            reward_for_xp(self.student, source="attempt", amount_xp=10, total_xp=10)
        self.assertEqual(get_wallet(self.student).balance, 10)

    def test_next_award_has_its_own_reference(self):
        reward_for_xp(self.student, source="attempt", amount_xp=10, total_xp=10)
        reward_for_xp(self.student, source="review", amount_xp=15, total_xp=25)
        self.assertEqual(get_wallet(self.student).balance, 25)

    def test_zero_rate_disables_coins(self):
        with self.settings(COINS_PER_XP=0):
            reward_for_xp(self.student, source="attempt", amount_xp=10, total_xp=10)
        self.assertEqual(get_wallet(self.student).balance, 0)

    def test_award_xp_pays_coins_through_gamification(self):
        from apps.gamification.services import award_xp

        award_xp(self.student, 10, source="attempt")
        self.assertEqual(get_wallet(self.student).balance, 10)


class ShopTests(TestCase):
    def setUp(self):
        self.student = make_student("shop-student")
        self.avatar = ShopItem.objects.create(
            title="Аватар «Сова»", slot=ShopItem.Slot.AVATAR, price_coins=40
        )
        self.frame = ShopItem.objects.create(
            title="Рамка «Золото»", slot=ShopItem.Slot.FRAME, price_coins=60
        )
        grant(self.student, 200, LedgerEntry.Reason.ADMIN_GRANT, "seed")

    def test_purchase_takes_coins_and_adds_to_inventory(self):
        purchase(self.student, self.avatar)
        self.assertEqual(get_wallet(self.student).balance, 160)
        self.assertTrue(
            InventoryItem.objects.filter(student=self.student, item=self.avatar).exists()
        )

    def test_second_purchase_of_same_item_rejected(self):
        purchase(self.student, self.avatar)
        with self.assertRaises(ValidationError):
            purchase(self.student, self.avatar)
        self.assertEqual(get_wallet(self.student).balance, 160)

    def test_purchase_without_funds_rejected(self):
        expensive = ShopItem.objects.create(title="Тема", price_coins=1000)
        with self.assertRaises(ValidationError):
            purchase(self.student, expensive)
        self.assertEqual(InventoryItem.objects.count(), 0)

    def test_inactive_or_expired_item_not_sold(self):
        hidden = ShopItem.objects.create(title="Скрытый", price_coins=10, is_active=False)
        expired = ShopItem.objects.create(
            title="Прошлогодний", price_coins=10,
            available_to=timezone.now() - timedelta(days=1),
        )
        for item in (hidden, expired):
            with self.subTest(item=item.title):
                with self.assertRaises(ValidationError):
                    purchase(self.student, item)
        self.assertNotIn(hidden, storefront())
        self.assertNotIn(expired, storefront())

    def test_equip_is_exclusive_within_slot(self):
        second_avatar = ShopItem.objects.create(
            title="Аватар «Лис»", slot=ShopItem.Slot.AVATAR, price_coins=30
        )
        purchase(self.student, self.avatar)
        purchase(self.student, second_avatar)
        purchase(self.student, self.frame)

        equip(self.student, self.avatar)
        equip(self.student, second_avatar)
        equip(self.student, self.frame)

        equipped = equipped_items(self.student)
        self.assertEqual(equipped[ShopItem.Slot.AVATAR].item, second_avatar)
        self.assertEqual(equipped[ShopItem.Slot.FRAME].item, self.frame)
        self.assertEqual(
            InventoryItem.objects.filter(student=self.student, is_equipped=True).count(), 2
        )

    def test_cannot_equip_unowned_item(self):
        with self.assertRaises(ValidationError):
            equip(self.student, self.avatar)

    def test_purchase_does_not_touch_learning_state(self):
        # Инвариант: косметика не влияет на обучение.
        purchase(self.student, self.avatar)
        self.assertFalse(hasattr(self.avatar, "node"))
        self.assertEqual(self.student.masteries.count(), 0)


class ShopApiTests(TestCase):
    """Витрина ученика: баланс, покупка и примерка."""

    def setUp(self):
        self.student = make_student("shop-api-student")
        self.client.force_login(self.student.user)
        self.item = ShopItem.objects.create(
            title="Аватар «Сова»", slot=ShopItem.Slot.AVATAR, price_coins=30
        )
        grant(self.student, 50, LedgerEntry.Reason.ADMIN_GRANT, "seed")

    def test_storefront_shows_balance_and_ownership(self):
        payload = self.client.get("/api/shop/").json()
        self.assertEqual(payload["balance"], 50)
        self.assertFalse(payload["items"][0]["owned"])

    def test_buy_then_equip(self):
        bought = self.client.post(f"/api/shop/items/{self.item.pk}/buy/")
        self.assertEqual(bought.status_code, 201)
        self.assertEqual(bought.json()["balance"], 20)

        equipped = self.client.post(f"/api/shop/items/{self.item.pk}/equip/")
        self.assertEqual(equipped.status_code, 200)
        self.assertEqual(equipped.json()["equipped"][ShopItem.Slot.AVATAR], self.item.pk)

    def test_buy_without_coins_returns_readable_error(self):
        expensive = ShopItem.objects.create(title="Тема", price_coins=999)
        response = self.client.post(f"/api/shop/items/{expensive.pk}/buy/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Недостаточно", response.json()["detail"])

    def test_wallet_shows_recent_entries(self):
        payload = self.client.get("/api/wallet/").json()
        self.assertEqual(payload["balance"], 50)
        self.assertEqual(payload["entries"][0]["amount"], 50)

    def test_shop_requires_login(self):
        self.client.logout()
        self.assertIn(self.client.get("/api/shop/").status_code, (401, 403))
