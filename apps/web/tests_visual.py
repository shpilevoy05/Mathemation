from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.economy.models import ShopItem

from .services import _shop_card


def shop_card_row(item, *, owned=False, equipped=False):
    return {
        "item": item,
        "owned": owned,
        "equipped": equipped,
        "affordable": False,
        "is_consumable": item.effect != ShopItem.Effect.NONE,
        "effect_note": "",
    }


class ShopCardArtworkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def test_known_cosmetic_codes_use_their_slot_as_art(self):
        expected_art = {
            (ShopItem.Slot.AVATAR, "owl"): "avatar",
            (ShopItem.Slot.FRAME, "flame"): "frame",
            (ShopItem.Slot.THEME, "forest"): "theme",
            (ShopItem.Slot.BADGE, "streak7"): "badge",
        }

        for (slot, code), expected in expected_art.items():
            with self.subTest(slot=slot, code=code):
                item = ShopItem.objects.get(slot=slot, code=code)
                card = _shop_card(shop_card_row(item), balance=0)
                self.assertEqual(card["art"], expected)

    def test_consumable_and_unknown_cosmetic_codes_have_no_art(self):
        freeze = ShopItem.objects.filter(
            effect=ShopItem.Effect.STREAK_FREEZE
        ).first()
        unknown = ShopItem.objects.create(
            title="Аватар без иллюстрации",
            slot=ShopItem.Slot.AVATAR,
            code="unknown-avatar",
            price_coins=10,
        )

        self.assertEqual(_shop_card(shop_card_row(freeze), balance=0)["art"], "")
        self.assertEqual(_shop_card(shop_card_row(unknown), balance=0)["art"], "")

    def test_unowned_avatar_uses_the_russian_slot_label(self):
        avatar = ShopItem.objects.get(slot=ShopItem.Slot.AVATAR, code="owl")

        card = _shop_card(shop_card_row(avatar), balance=0)

        self.assertEqual(card["tag"], "аватар")
        self.assertNotEqual(card["tag"], ShopItem.Slot.AVATAR)


class RenderedArtworkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.user = User.objects.get(username="student")

    def setUp(self):
        self.client.force_login(self.user)

    def test_student_page_contains_brand_league_and_avatar_symbols(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        for symbol_id in (
            "brand-mark",
            "league-bronze",
            "league-silver",
            "league-gold",
            "league-platinum",
            "league-diamond",
            "avatar-owl",
        ):
            with self.subTest(symbol_id=symbol_id):
                self.assertContains(response, f'id="{symbol_id}"')

    def test_shop_renders_known_avatar_and_theme_art(self):
        response = self.client.get(reverse("shop"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="#avatar-owl"')
        self.assertContains(response, "theme-swatch--forest")

    def test_arena_renders_the_context_league_class_and_title(self):
        response = self.client.get(reverse("arena"))

        self.assertEqual(response.status_code, 200)
        league = response.context["arena_league"]
        self.assertContains(response, f'league-card--{league["code"]}')
        self.assertContains(response, league["title"])


class LogoTemplateTests(SimpleTestCase):
    def test_logo_uses_no_removed_raster_mark(self):
        logo = Path(settings.BASE_DIR, "templates", "partials", "logo.html")

        self.assertNotIn("img/mark.png", logo.read_text(encoding="utf-8"))
