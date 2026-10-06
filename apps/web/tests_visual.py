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

    def test_only_theme_and_badge_use_the_legacy_art_field(self):
        badge = ShopItem.objects.create(
            title="Значок серии", slot=ShopItem.Slot.BADGE,
            code="streak7", price_coins=10,
        )
        expected_art = {
            (ShopItem.Slot.AVATAR, "owl"): ("", "avatar"),
            (ShopItem.Slot.FRAME, "flame"): ("", "frame"),
            (ShopItem.Slot.THEME, "forest"): ("theme", ""),
            (badge.slot, badge.code): ("badge", ""),
        }

        for (slot, code), (expected_art_value, expected_kind) in expected_art.items():
            with self.subTest(slot=slot, code=code):
                item = ShopItem.objects.get(slot=slot, code=code)
                card = _shop_card(shop_card_row(item), balance=0)
                self.assertEqual(card["art"], expected_art_value)
                self.assertEqual(card["art_kind"], expected_kind)

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

    def test_student_page_contains_brand_mark_and_arena_rank_symbols(self):
        # Аватары, рамки и знаки месячных лиг едут спрайтом cosmetics.svg;
        # в разметке страницы — рисунок логотипа (brand-art) и ранги арены.
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="avatar-owl"')
        self.assertContains(response, 'id="brand-art"')
        self.assertContains(response, "img/logo-flame.png")
        for symbol_id in (
            "rank-bronze",
            "rank-silver",
            "rank-gold",
            "rank-platinum",
            "rank-diamond",
        ):
            with self.subTest(symbol_id=symbol_id):
                self.assertContains(response, f'id="{symbol_id}"')

    def test_shop_renders_known_avatar_and_theme_art(self):
        response = self.client.get(reverse("shop"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cosmetics.svg#avatar-owl")
        self.assertContains(response, "theme-swatch--forest")

    def test_arena_renders_the_context_league_class_and_title(self):
        response = self.client.get(reverse("arena"))

        self.assertEqual(response.status_code, 200)
        league = response.context["arena_rank"]
        self.assertContains(response, f'league-card--{league["code"]}')
        self.assertContains(response, league["title"])


class LogoTemplateTests(SimpleTestCase):
    def test_logo_is_one_wordmark_drawing(self):
        # Логотип — фирменный вордмарк 1:1 одним рисунком: и слово, и эмблема
        # ссылаются на brand-art, отдельного растрового знака больше нет.
        logo = Path(settings.BASE_DIR, "templates", "partials", "logo.html").read_text(encoding="utf-8")

        self.assertEqual(logo.count('href="#brand-art"'), 2)
        self.assertNotIn("mark.png", logo)
        self.assertTrue(Path(settings.BASE_DIR, "static", "img", "logo-flame.png").is_file())
        self.assertTrue(Path(settings.BASE_DIR, "static", "img", "favicon.svg").is_file())
