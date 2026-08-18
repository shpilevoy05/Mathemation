"""Двухуровневый рельс: группы и активный пункт считаются по маршруту."""

from django.test import RequestFactory, TestCase
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

    def test_anonymous_has_no_navigation(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(nav_groups(AnonymousUser()), [])


class NavigationContextTests(TestCase):
    def test_rail_renders_groups(self):
        student = make_student("nav-render-student")
        self.client.force_login(student.user)

        body = self.client.get(reverse("track")).content.decode()

        self.assertIn('class="nav-group"', body)
        self.assertIn("Проверить себя", body)
        # Группа с открытой страницей приходит раскрытой.
        self.assertIn('<details class="nav-group" open>', body)
