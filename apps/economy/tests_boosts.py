"""Р Р°СЃС…РѕРґРЅРёРєРё РјР°РіР°Р·РёРЅР°: Р·Р°РјРѕСЂРѕР·РєР° СЃС‚СЂРёРєР° Рё СѓСЃРєРѕСЂРёС‚РµР»СЊ РѕРїС‹С‚Р°."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import StudentProfile, User
from apps.gamification.models import GamificationProfile
from apps.gamification.services import advance_streak, award_xp

from .models import LedgerEntry, ShopItem, XpBoost
from .services import active_boost, boosted_xp, grant, purchase


def make_student(username="boost-student") -> StudentProfile:
    return StudentProfile.objects.create(user=User.objects.create_user(username))


def make_item(**overrides) -> ShopItem:
    defaults = {
        "title": "Р—Р°РјРѕСЂРѕР·РєР° СЃС‚СЂРёРєР°", "slot": ShopItem.Slot.BOOST,
        "price_coins": 100, "effect": ShopItem.Effect.STREAK_FREEZE,
        "effect_value": 1,
    }
    return ShopItem.objects.create(**{**defaults, **overrides})


class StreakFreezeTests(TestCase):
    def setUp(self):
        self.student = make_student()
        grant(self.student, 1000, LedgerEntry.Reason.ADMIN_GRANT, reference="seed")

    def test_purchase_adds_a_freeze_and_can_repeat(self):
        item = make_item()

        self.assertIsNone(purchase(self.student, item))
        purchase(self.student, item)

        profile = GamificationProfile.objects.get(student=self.student)
        self.assertEqual(profile.streak_freezes, 2)

    def test_freeze_saves_the_streak_after_a_missed_day(self):
        today = timezone.localdate()
        advance_streak(self.student, today - timedelta(days=2))
        purchase(self.student, make_item())

        profile = advance_streak(self.student, today)

        self.assertEqual(profile.streak_current, 2)
        self.assertEqual(profile.streak_freezes, 0)
        self.assertEqual(profile.streak_frozen_periods, 1)

    def test_streak_resets_when_there_are_not_enough_freezes(self):
        today = timezone.localdate()
        advance_streak(self.student, today - timedelta(days=4))

        profile = advance_streak(self.student, today)

        self.assertEqual(profile.streak_current, 1)

    def test_freeze_is_not_spent_on_an_unbroken_streak(self):
        today = timezone.localdate()
        purchase(self.student, make_item())
        advance_streak(self.student, today - timedelta(days=1))

        profile = advance_streak(self.student, today)

        self.assertEqual(profile.streak_current, 2)
        self.assertEqual(profile.streak_freezes, 1)


class XpBoostTests(TestCase):
    def setUp(self):
        self.student = make_student("boost-buyer")
        grant(self.student, 1000, LedgerEntry.Reason.ADMIN_GRANT, reference="seed")
        self.item = make_item(
            title="РЈСЃРєРѕСЂРёС‚РµР»СЊ", effect=ShopItem.Effect.XP_BOOST,
            effect_value=50, duration_hours=24,
        )

    def test_purchase_starts_a_timed_boost(self):
        purchase(self.student, self.item)

        boost = active_boost(self.student)
        self.assertEqual(boost.bonus_percent, 50)
        self.assertGreater(boost.ends_at, timezone.now())

    def test_boost_increases_awarded_xp(self):
        purchase(self.student, self.item)

        profile = award_xp(self.student, 10, source="test")

        self.assertEqual(profile.xp, 15)

    def test_expired_boost_stops_working(self):
        XpBoost.objects.create(
            student=self.student, bonus_percent=100,
            starts_at=timezone.now() - timedelta(days=2),
            ends_at=timezone.now() - timedelta(days=1),
        )

        self.assertIsNone(active_boost(self.student))
        self.assertEqual(boosted_xp(self.student, 10), 10)

    def test_boosts_do_not_stack_the_strongest_wins(self):
        purchase(self.student, self.item)
        purchase(self.student, make_item(
            title="РЈСЃРєРѕСЂРёС‚РµР»СЊ Г—2", effect=ShopItem.Effect.XP_BOOST,
            effect_value=100, duration_hours=3,
        ))

        self.assertEqual(boosted_xp(self.student, 10), 20)


class CosmeticsTests(TestCase):
    def setUp(self):
        self.student = make_student("cosmetics")
        grant(self.student, 1000, LedgerEntry.Reason.ADMIN_GRANT, reference="seed")

    def test_cosmetic_goes_to_inventory_and_cannot_be_bought_twice(self):
        item = ShopItem.objects.create(
            title="РђРІР°С‚Р°СЂ В«РЎРѕРІР°В»", slot=ShopItem.Slot.AVATAR, code="owl", price_coins=40
        )

        inventory = purchase(self.student, item)

        self.assertIsNotNone(inventory)
        with self.assertRaises(Exception):
            purchase(self.student, item)

    def test_equipped_theme_reaches_the_template_context(self):
        from apps.economy.services import equip
        from apps.web.context_processors import cosmetics

        theme = ShopItem.objects.create(
            title="РўРµРјР° В«РќРѕС‡СЊВ»", slot=ShopItem.Slot.THEME, code="dark", price_coins=120
        )
        purchase(self.student, theme)
        equip(self.student, theme)

        request = type("R", (), {"user": self.student.user})()
        self.assertEqual(cosmetics(request)["ui_theme"], "dark")

    def test_unknown_theme_code_is_ignored_instead_of_breaking_the_page(self):
        from apps.economy.services import equip
        from apps.web.context_processors import cosmetics

        theme = ShopItem.objects.create(
            title="РўРµРјР° В«?В»", slot=ShopItem.Slot.THEME, code="neon-city", price_coins=1
        )
        purchase(self.student, theme)
        equip(self.student, theme)

        request = type("R", (), {"user": self.student.user})()
        self.assertEqual(cosmetics(request)["ui_theme"], "")

