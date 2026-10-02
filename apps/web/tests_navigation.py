"""Двухуровневый рельс: группы и активный пункт считаются по маршруту."""

import re

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.knowledge.tests import make_student

from .navigation import nav_groups


class NavigationTests(TestCase):
    def groups(self, user):
        return {group.title: group for group in nav_groups(user)}

    def test_student_sees_grouped_sections(self):
        student = make_student("nav-student")

        groups = self.groups(student.user)

        self.assertIn("Учёба", groups)
        self.assertIn("Проверить себя", groups)
        # Плоский список из одиннадцати ссылок разошёлся по разделам.
        self.assertTrue(all(len(group.items) <= 6 for group in groups.values()))

    def test_group_with_the_open_page_is_expanded(self):
        student = make_student("nav-open-student")
        groups = self.groups(student.user)

        self.assertTrue(groups["Учёба"].is_open("track"))
        self.assertFalse(groups["Проверить себя"].is_open("track"))

    def test_active_item_is_marked_including_child_routes(self):
        student = make_student("nav-active-student")
        study = self.groups(student.user)["Учёба"]

        track = next(item for item in study.items if item.label == "Дорожка")
        self.assertTrue(track.is_active("lesson"))
        self.assertFalse(track.is_active("shop"))

    def test_schedule_lives_next_to_the_track(self):
        student = make_student("nav-schedule-student")
        study = self.groups(student.user)["Учёба"]

        labels = [item.label for item in study.items]
        self.assertIn("Расписание", labels)
        self.assertLess(labels.index("Дорожка"), labels.index("Карта навыков"))

    def test_single_item_group_is_a_plain_link(self):
        student = make_student("nav-single-student")

        self.assertTrue(self.groups(student.user)["Результат"].is_single)

    def test_parent_and_staff_see_their_own_sections(self):
        from apps.accounts.models import ParentProfile

        parent = User.objects.create_user("nav-parent", role=User.Role.PARENT)
        ParentProfile.objects.create(user=parent)
        methodist = User.objects.create_user("nav-methodist", role=User.Role.METHODIST)

        self.assertIn("Ребёнок", self.groups(parent))
        self.assertIn("Контент", self.groups(methodist))
        self.assertNotIn("Учёба", self.groups(methodist))
        self.assertEqual(self.groups(parent)["Аккаунт"].items[0].label, "Настройки")
        self.assertEqual(self.groups(methodist)["Аккаунт"].items[0].label, "Настройки")

    def test_student_sees_account_settings(self):
        student = make_student("nav-settings-student")
        item = self.groups(student.user)["Аккаунт"].items[0]

        self.assertEqual(item.url, reverse("account_settings"))
        self.assertTrue(item.is_active("account_password"))

    def test_methodist_content_navigation_contains_studio_before_admin_tools(self):
        methodist = User.objects.create_user(
            "nav-studio-methodist", role=User.Role.METHODIST
        )
        content = self.groups(methodist)["Контент"]

        self.assertEqual(
            [item.label for item in content.items],
            [
                "Обзор", "Уроки", "Задачи", "Граф знаний", "Задания дня",
                "Диагностики и пробники", "Цены и акции", "Панель", "Django-админка",
            ],
        )
        self.assertTrue(
            next(item for item in content.items if item.label == "Уроки").is_active(
                "studio_lesson_edit"
            )
        )

    def test_anonymous_has_no_navigation(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(nav_groups(AnonymousUser()), [])


class NavigationContextTests(TestCase):
    def test_rail_renders_groups(self):
        student = make_student("nav-render-student")
        self.client.force_login(student.user)

        body = self.client.get(reverse("track")).content.decode()

        self.assertIn('class="nav-group"', body)
        self.assertIn('class="nav-link nav-level-one', body)
        self.assertIn("Проверить себя", body)
        # Группа с открытой страницей приходит раскрытой.
        self.assertIn('<details class="nav-group" open>', body)
        self.assertIn('aria-current="page"', body)

    def test_mobile_navigation_contains_only_destination_links(self):
        student = make_student("nav-mobile-student")
        self.client.force_login(student.user)

        body = self.client.get(reverse("track")).content.decode()
        mobile_nav = re.search(
            r'<nav class="mobile-tabs".*?>(.*?)</nav>',
            body,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(mobile_nav)
        links = re.findall(
            r'<a class="mobile-tab.*?</a>',
            mobile_nav.group(1),
            flags=re.DOTALL,
        )
        expected_urls = [
            item.url
            for group in nav_groups(student.user)
            for item in group.items
        ]
        rendered_urls = [re.search(r'href="([^"]+)"', link).group(1) for link in links]

        self.assertEqual(len(links), len(expected_urls))
        self.assertCountEqual(rendered_urls, expected_urls)
        self.assertEqual(sum('aria-current="page"' in link for link in links), 1)
        for link in links:
            self.assertIn('<use href="#i-', link)
            self.assertRegex(link, r'<span class="mobile-tab-label">\s*\S+.*?</span>')


class ThemeCssTests(SimpleTestCase):
    TRACK_TOKENS = (
        "--track-title",
        "--track-copy",
        "--tooltip-bg",
        "--tooltip-ink",
        "--locked-bg",
        "--locked-shadow",
        "--locked-ink",
        "--track-line",
        "--track-line-done",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = (settings.BASE_DIR / "static" / "css" / "app.css").read_text(encoding="utf-8")
        cls.javascript = (settings.BASE_DIR / "static" / "js" / "app.js").read_text(encoding="utf-8")

    def css_block(self, selector, start=0):
        block_start = self.css.index(selector, start) + len(selector)
        depth = 1
        for position in range(block_start, len(self.css)):
            if self.css[position] == "{":
                depth += 1
            elif self.css[position] == "}":
                depth -= 1
                if depth == 0:
                    return self.css[block_start:position]
        self.fail(f"CSS block is not closed: {selector}")

    def test_every_theme_defines_track_tokens(self):
        selectors = (
            ":root {",
            ':root[data-theme="dark"] {',
            ':root[data-theme="sunrise"] {',
            ':root[data-theme="forest"] {',
            ':root[data-theme="graphite"] {',
        )
        for selector in selectors:
            with self.subTest(selector=selector):
                block = self.css_block(selector)
                for token in self.TRACK_TOKENS:
                    self.assertIn(f"{token}:", block)

        media_start = self.css.index("@media (prefers-color-scheme: dark)")
        automatic_dark = self.css_block(
            ':root:not([data-theme="light"]):not([data-theme="sunrise"]):not([data-theme="forest"]):not([data-theme="graphite"]) {',
            media_start,
        )
        for token in self.TRACK_TOKENS:
            self.assertIn(f"{token}:", automatic_dark)

    def test_light_theme_rail_tokens_are_readable_values(self):
        sunrise = self.css_block(':root[data-theme="sunrise"] {')
        forest = self.css_block(':root[data-theme="forest"] {')

        self.assertIn("--night-ink: #F4E3CC", sunrise)
        self.assertIn("--night-muted: #D7BC96", sunrise)
        self.assertIn("--night-ink: #D3EADD", forest)
        self.assertIn("--night-muted: #A5C6B4", forest)

    def test_mobile_navigation_and_track_rules(self):
        cabinet_breakpoints = self.css.index("@media (max-width: 900px)")
        mobile = self.css_block("@media (max-width: 720px) {", cabinet_breakpoints)

        self.assertIn(".main-nav { display: none; }", mobile)
        self.assertIn(".mobile-tabs", mobile)
        self.assertIn("flex-direction: row", mobile)
        self.assertIn("flex: 0 0 72px", mobile)
        self.assertIn("min-width: 72px", mobile)
        self.assertIn("scroll-snap-type: x proximity", mobile)
        self.assertIn("text-overflow: ellipsis", mobile)
        self.assertIn("translate: -36px 0", mobile)
        self.assertIn("translate: 36px 0", mobile)
        self.assertIn("padding-inline: 16px", mobile)

    def test_curve_and_labels_stay_clear_of_track_text(self):
        self.assertIn(
            "text-shadow: 0 0 3px var(--bg), 0 0 6px var(--bg), 0 0 10px var(--bg)",
            self.css,
        )
        self.assertIn(
            "const points = [{ x: nodePoints[0].x, y: 0 }, ...nodePoints];",
            self.javascript,
        )
        self.assertIn('document.querySelector(".mobile-tabs")', self.javascript)
        self.assertIn('nav?.querySelector(".mobile-tab.is-active")', self.javascript)
        self.assertIn("nav.scrollTo", self.javascript)
