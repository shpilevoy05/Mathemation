"""Косметика: каталог, спрайт и отрисовка совпадают с дизайн-исходниками."""

from pathlib import Path

from django.conf import settings
from django.template import Context, Template
from django.test import TestCase

from apps.knowledge.tests import make_student

from .catalog import (
    ANIMATED_AVATARS,
    LEAGUE_MARKS,
    ANIMATED_FRAMES,
    AVATAR_CODES,
    BASE_AVATARS,
    FRAMES,
    FRAME_CODES,
    PENNANT_CODES,
    Tier,
    grant_base_avatars,
    load_cosmetics,
)
from .models import InventoryItem, ShopItem
from .services import KNOWN_AVATARS, KNOWN_FRAMES, cosmetic_codes
from .sprite import build_sprite, design_root, symbol_id


def render(template: str, **context) -> str:
    return Template("{% load cosmetics %}" + template).render(Context(context))


class CatalogMatchesDesignTests(TestCase):
    """Код без картинки и картинка без кода — одинаково плохо."""

    def test_every_avatar_has_a_file(self):
        for code in AVATAR_CODES:
            with self.subTest(code=code):
                self.assertTrue((design_root() / "avatars" / f"{code}.svg").exists())

    def test_every_frame_has_a_file(self):
        for code in FRAME_CODES:
            with self.subTest(code=code):
                self.assertTrue((design_root() / "frames" / f"{code}.svg").exists())

    def test_every_file_is_sold(self):
        files = sorted(path.stem for path in (design_root() / "avatars").glob("*.svg"))

        self.assertEqual(files, sorted(AVATAR_CODES))

    def test_every_frame_file_is_sold(self):
        files = sorted(path.stem for path in (design_root() / "frames").glob("*.svg"))

        self.assertEqual(files, sorted(FRAME_CODES))

    def test_every_pennant_file_has_a_trophy_code(self):
        files = sorted(path.stem for path in (design_root() / "pennants").glob("*.svg"))

        self.assertEqual(files, sorted(PENNANT_CODES))

    def test_known_codes_come_from_the_catalog(self):
        self.assertEqual(KNOWN_AVATARS, set(AVATAR_CODES))
        self.assertEqual(KNOWN_FRAMES, set(FRAME_CODES))

    def test_animated_items_never_stand_still(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "cosmetics.css").read_text(
            encoding="utf-8"
        )
        import re

        # Вещь, проданная как анимированная, должна двигаться и в покое:
        # разовая анимация при надевании в списке выглядит картинкой.
        for kind, codes in (("frame", ANIMATED_FRAMES), ("avatar", ANIMATED_AVATARS)):
            for code in codes:
                selector = (
                    r'\[class\*="frame-rosette-"\]'
                    if code.startswith("rosette-") else rf"\.{kind}-{code}"
                )
                rules = re.findall(rf"{selector} [^{{]*\{{[^}}]*\}}", css, re.S)
                with self.subTest(item=f"{kind}-{code}"):
                    self.assertIn("infinite", " ".join(rules))

    def test_animated_items_have_their_css(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "cosmetics.css").read_text(
            encoding="utf-8"
        )

        # Анимированная вещь без правил — это просто дорогая картинка.
        for code in ANIMATED_FRAMES:
            with self.subTest(frame=code):
                selector = (
                    '[class*="frame-rosette-"]'
                    if code.startswith("rosette-") else f".frame-{code} "
                )
                self.assertIn(selector, css)
        for code in ANIMATED_AVATARS:
            with self.subTest(avatar=code):
                self.assertIn(f".avatar-{code} ", css)

    def test_animated_frames_are_derived_from_tier_and_rosettes(self):
        expected_rosettes = [
            f"rosette-{league}-{place}"
            for league in LEAGUE_MARKS
            for place in (1, 2, 3)
        ]
        expected_animated = [
            code for code, _title, tier, _price in FRAMES if tier == Tier.ANIMATED
        ]

        self.assertEqual(
            set(expected_animated),
            {"saturn", "comet", "aurora", "gears", "bitflow", "nebula"},
        )
        self.assertEqual(ANIMATED_FRAMES, expected_animated + expected_rosettes)
        self.assertNotIn("coordinates", ANIMATED_FRAMES)
        self.assertNotIn("flame", ANIMATED_FRAMES)


class SpriteTests(TestCase):
    def setUp(self):
        self.markup, self.report = build_sprite()

    def test_sprite_holds_every_avatar_and_frame(self):
        for code in AVATAR_CODES:
            self.assertIn(f'id="{symbol_id("avatar", code)}"', self.markup)
        for code in FRAME_CODES:
            self.assertIn(f'id="{symbol_id("frame", code)}"', self.markup)

    def test_league_marks_are_in_the_sprite(self):
        self.assertIn('id="league-sigma"', self.markup)
        self.assertIn('id="league-sigma-1"', self.markup)

    def test_pennants_are_in_the_sprite(self):
        for code in PENNANT_CODES:
            self.assertIn(f'id="{symbol_id("pennant", code)}"', self.markup)

    def test_symbols_keep_the_root_fill(self):
        import re

        # У исходников `fill="none"` на корне: фигуры без своей заливки
        # рассчитывают на наследование. Потеряв атрибут, они становятся
        # чёрными — вместо аватара получается чёрный круг.
        symbols = re.findall(r"<symbol[^>]*>", self.markup)

        self.assertTrue(symbols)
        self.assertTrue(all('fill="none"' in symbol for symbol in symbols))

    def test_identifiers_do_not_collide(self):
        import re

        ids = re.findall(r'id="([^"]+)"', self.markup)

        # Одинаковый id из двух картинок покрасил бы вторую в цвета первой.
        self.assertEqual(len(ids), len(set(ids)))

    def test_built_sprite_is_up_to_date(self):
        stored = (Path(settings.BASE_DIR) / "static" / "img" / "cosmetics.svg").read_text(
            encoding="utf-8"
        )

        # Спрайт лежит в репозитории собранным: продакшену незачем читать
        # дизайн-исходники, но и разъезжаться с ними он не должен.
        self.assertEqual(stored, self.markup)


class LoadCatalogTests(TestCase):
    def test_items_appear_in_the_shop(self):
        load_cosmetics()

        self.assertEqual(ShopItem.objects.filter(slot="avatar").count(), len(AVATAR_CODES))
        self.assertEqual(ShopItem.objects.filter(slot="frame").count(), len(FRAME_CODES))

    def test_base_avatars_are_free(self):
        load_cosmetics()

        for code in BASE_AVATARS:
            with self.subTest(code=code):
                self.assertEqual(
                    ShopItem.objects.get(slot="avatar", code=code).price_coins, 0
                )

    def test_animated_items_are_marked(self):
        load_cosmetics()

        item = ShopItem.objects.get(slot="avatar", code="blackhole")
        self.assertEqual(item.tier, ShopItem.Tier.ANIMATED)

    def test_downgraded_frames_are_paid_items(self):
        load_cosmetics()

        expected = {"coordinates": 180, "flame": 190}
        for code, price in expected.items():
            with self.subTest(code=code):
                item = ShopItem.objects.get(slot="frame", code=code)
                self.assertEqual(item.tier, ShopItem.Tier.PAID)
                self.assertEqual(item.price_coins, price)

    def test_loading_twice_changes_nothing(self):
        load_cosmetics()
        before = ShopItem.objects.count()

        load_cosmetics()

        self.assertEqual(ShopItem.objects.count(), before)

    def test_retired_items_leave_the_storefront_but_not_the_inventory(self):
        student = make_student("cosmetics-owner")
        legacy = ShopItem.objects.create(
            title="Аватар «Старый талисман»", slot="avatar", code="old-mascot",
            price_coins=90,
        )
        InventoryItem.objects.create(student=student, item=legacy)

        load_cosmetics()

        legacy.refresh_from_db()
        self.assertFalse(legacy.is_active)
        # Купленное остаётся у ученика: снять с витрины — не значит отобрать.
        self.assertTrue(InventoryItem.objects.filter(item=legacy).exists())


class RetiredSlotTests(TestCase):
    """Значки не продаются: их выдают за достижения."""

    def test_badges_leave_the_storefront(self):
        badge = ShopItem.objects.create(
            title="Значок «Стрик 7»", slot="badge", code="streak7", price_coins=30
        )

        load_cosmetics()

        badge.refresh_from_db()
        self.assertFalse(badge.is_active)

    def test_bloom_is_not_sold_as_animated(self):
        from .catalog import ANIMATED_FRAMES

        # Раскрытие «Цветущей» происходит один раз при надевании: в списке
        # движения не видно, и обещать его в цене нечестно.
        self.assertNotIn("bloom", ANIMATED_FRAMES)


class BaseAvatarTests(TestCase):
    def setUp(self):
        load_cosmetics()
        self.student = make_student("base-avatars")

    def test_four_base_avatars_are_granted(self):
        granted = grant_base_avatars(self.student)

        self.assertEqual(granted, len(BASE_AVATARS))

    def test_one_of_them_is_put_on(self):
        grant_base_avatars(self.student)

        self.assertTrue(cosmetic_codes(self.student)["avatar"])

    def test_granting_twice_changes_nothing(self):
        grant_base_avatars(self.student)

        self.assertEqual(grant_base_avatars(self.student), 0)

    def test_registration_grants_them(self):
        from apps.accounts.services import accept_invite, create_invite

        invite = create_invite(None)
        user = accept_invite(
            invite.code,
            username="newbie",
            email="newbie@example.com",
            password="pass12345",
        )

        # Кабинет не должен встречать ученика пустым кружком с буквой.
        self.assertTrue(cosmetic_codes(user.student_profile)["avatar"])


class RenderTests(TestCase):
    def test_plain_avatar_comes_from_the_sprite(self):
        markup = render('{% cosmetic "avatar" "owl" %}')

        self.assertIn("cosmetics.svg#avatar-owl", markup)

    def test_animated_avatar_is_inlined(self):
        markup = render('{% cosmetic "avatar" "blackhole" %}')

        # CSS не достаёт внутрь внешнего спрайта: анимированное встраивается.
        self.assertNotIn("cosmetics.svg#", markup)
        self.assertIn("avatar-blackhole", markup)

    def test_every_drawing_carries_the_root_fill(self):
        for markup in (
            render('{% cosmetic "avatar" "owl" %}'),
            render('{% cosmetic "avatar" "blackhole" %}'),
            render('{% cosmetic "frame" "saturn" %}'),
            render("{% league_mark 'sigma' %}"),
        ):
            with self.subTest(markup=markup[:40]):
                self.assertIn('fill="none"', markup)

    def test_animated_frame_is_inlined(self):
        markup = render('{% cosmetic "frame" "saturn" %}')

        self.assertNotIn("cosmetics.svg#", markup)
        self.assertIn("sa-moon", markup)

    def test_paid_frames_come_from_the_sprite(self):
        for code in ("coordinates", "flame"):
            with self.subTest(code=code):
                markup = render('{% cosmetic "frame" code %}', code=code)
                self.assertIn(f"cosmetics.svg#frame-{code}", markup)

    def test_pennant_uses_the_128_view_box(self):
        markup = render('{% cosmetic "pennant" "pennant-delta-1" %}')

        self.assertIn('viewBox="0 0 128 128"', markup)
        self.assertIn("#pennant-delta-1", markup)

    def test_empty_code_renders_nothing(self):
        self.assertEqual(render('{% cosmetic "avatar" "" %}'), "")

    def test_league_mark_uses_the_place(self):
        markup = render("{% league_mark 'sigma' 1 %}")

        self.assertIn("#league-sigma-1", markup)

    def test_every_league_has_a_mark(self):
        from apps.gamification.models import LEAGUE_ORDER

        # Знак есть у каждой лиги, включая младшие: иначе ступень лестницы
        # выглядела бы пустым местом.
        self.assertEqual(LEAGUE_MARKS, [str(league) for league in LEAGUE_ORDER])

    def test_unknown_league_renders_nothing(self):
        # Чужой знак поставить нельзя — лига читается по знаку.
        self.assertEqual(render("{% league_mark 'unknown' %}"), "")

    def test_league_marks_are_drawn_for_every_place(self):
        for league in LEAGUE_MARKS:
            for place in (1, 2, 3):
                with self.subTest(league=league, place=place):
                    self.assertIn(
                        f"#league-{league}-{place}",
                        render("{% league_mark league place %}", league=league, place=place),
                    )


class RewardOnlyTests(TestCase):
    def setUp(self):
        load_cosmetics()
        self.student = make_student("league-reward-owner")
        self.client.force_login(self.student.user)
        self.reward = ShopItem.objects.get(slot="frame", code="rosette-delta-1")

    def test_reward_cannot_be_bought(self):
        response = self.client.post(
            f"/api/shop/items/{self.reward.pk}/buy/", {}, "application/json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Награду лиги нельзя купить.")

    def test_unowned_reward_is_hidden_but_owned_reward_can_be_equipped(self):
        item_ids = {row["id"] for row in self.client.get("/api/shop/").json()["items"]}
        self.assertNotIn(self.reward.pk, item_ids)

        InventoryItem.objects.create(student=self.student, item=self.reward)
        item_ids = {row["id"] for row in self.client.get("/api/shop/").json()["items"]}
        self.assertIn(self.reward.pk, item_ids)

        response = self.client.post(
            f"/api/shop/items/{self.reward.pk}/equip/", {}, "application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            InventoryItem.objects.get(student=self.student, item=self.reward).is_equipped
        )

        page = self.client.get("/shop/")
        self.assertContains(page, "награда лиги")
        self.assertContains(page, self.reward.title)


class ConsumableTests(TestCase):
    """Ускорители и заморозки продаются теми же наборами, что выдаёт лига."""

    def setUp(self):
        load_cosmetics()

    def test_boosts_match_the_league_prizes(self):
        from apps.gamification.leagues import LEAGUE_PRIZE_SCALE

        hours = sorted({hours for hours, _freezes in LEAGUE_PRIZE_SCALE.values()})
        sold = sorted(
            ShopItem.objects.filter(slot="boost", effect="xp_boost")
            .values_list("duration_hours", flat=True)
        )

        # Награда и товар — одна и та же вещь: разойтись им нельзя.
        self.assertEqual(sold, hours)

    def test_freeze_bundles_are_cheaper_than_singles(self):
        from .catalog import BUNDLE_DISCOUNTS

        single = ShopItem.objects.get(slot="boost", code="freeze-1")
        for count, discount in BUNDLE_DISCOUNTS.items():
            with self.subTest(count=count):
                bundle = ShopItem.objects.get(slot="boost", code=f"freeze-{count}")
                self.assertEqual(bundle.effect_value, count)
                self.assertLess(bundle.price_coins, single.price_coins * count)
                expected = single.price_coins * count * (100 - discount) / 100
                self.assertAlmostEqual(bundle.price_coins, expected, delta=5)

    def test_old_boosters_leave_the_storefront(self):
        legacy = ShopItem.objects.create(
            title="Ускоритель опыта +100 % на 3 часа", slot="boost",
            code="", effect="xp_boost", effect_value=100, duration_hours=3,
            price_coins=120,
        )

        load_cosmetics()

        legacy.refresh_from_db()
        # Два разных «ускорителя на сутки» выглядят ошибкой, а не выбором.
        self.assertFalse(legacy.is_active)
