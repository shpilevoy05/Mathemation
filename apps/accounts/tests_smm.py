from django.contrib import admin
from django.contrib.auth.models import AnonymousUser, Group
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.two_factor import is_required_for
from apps.web.navigation import nav_groups
from apps.web.permissions import is_smm


class SmmRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = Group.objects.get(name="SMM")
        cls.smm = User.objects.create_user(
            "smm-tests", password="demo12345", role=User.Role.SMM, is_staff=True
        )
        cls.smm.groups.add(cls.group)
        cls.methodist = User.objects.create_user(
            "smm-methodist", role=User.Role.METHODIST
        )

    def test_is_smm_accepts_role_group_and_superuser(self):
        by_group = User.objects.create_user("smm-by-group")
        by_group.groups.add(self.group)
        superuser = User.objects.create_superuser("smm-superuser", password="demo12345")

        self.assertTrue(is_smm(self.smm))
        self.assertTrue(is_smm(by_group))
        self.assertTrue(is_smm(superuser))
        self.assertFalse(is_smm(self.methodist))
        self.assertFalse(is_smm(AnonymousUser()))

    def test_smm_navigation_contains_only_social_and_account_groups(self):
        groups = {group.title: group for group in nav_groups(self.smm)}

        self.assertEqual(set(groups), {"Соцсети", "Аккаунт"})
        self.assertEqual(groups["Соцсети"].icon, "i-megaphone")
        self.assertEqual(
            [(item.label, item.icon) for item in groups["Соцсети"].items],
            [
                ("Публикации", "i-send"),
                ("Рубрики и расписание", "i-clock"),
                ("Каналы", "i-chat"),
                ("Идеи", "i-bulb"),
                ("Профиль бренда", "i-flame"),
                ("Разрешения", "i-lock"),
            ],
        )

    def test_methodist_does_not_see_social_navigation(self):
        self.assertNotIn("Соцсети", {group.title for group in nav_groups(self.methodist)})

    def test_smm_can_open_every_social_navigation_destination(self):
        self.client.force_login(self.smm)
        social_group = next(
            group for group in nav_groups(self.smm) if group.title == "Соцсети"
        )

        for item in social_group.items:
            with self.subTest(item=item.label):
                self.assertEqual(self.client.get(item.url).status_code, 200)

    def test_smm_landing_redirects_to_posts(self):
        self.client.force_login(self.smm)

        self.assertRedirects(
            self.client.get(reverse("dashboard")),
            reverse("admin:social_agent_post_changelist"),
            fetch_redirect_response=False,
        )

    def test_smm_is_denied_other_staff_sections(self):
        self.client.force_login(self.smm)

        for url in (
            reverse("studio_lessons"),
            reverse("methodist_dashboard"),
            reverse("expert_queue"),
            reverse("admin:accounts_user_changelist"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_smm_is_denied_every_other_apps_admin_changelist(self):
        self.client.force_login(self.smm)

        for model in admin.site._registry:
            if model._meta.app_label == "social_agent":
                continue
            url = reverse(
                f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist"
            )
            with self.subTest(model=model._meta.label):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_smm_group_permissions_are_exact_and_social_only(self):
        permissions = {
            f"{app_label}.{codename}"
            for app_label, codename in self.group.permissions.values_list(
                "content_type__app_label", "codename"
            )
        }
        standard_models = {
            "brandprofile",
            "channel",
            "rubric",
            "socialtaskpermission",
            "sociallessonpermission",
            "post",
            "mediaasset",
        }
        deletable_models = {"contentidea", "rubricslot"}
        readonly_models = {"llmcall", "postcheck", "botstate"}
        expected = {
            f"social_agent.{action}_{model}"
            for model in standard_models
            for action in ("add", "change", "view")
        }
        expected.update(
            f"social_agent.{action}_{model}"
            for model in deletable_models
            for action in ("add", "change", "delete", "view")
        )
        expected.update(
            f"social_agent.view_{model}" for model in readonly_models
        )

        self.assertEqual(permissions, expected)
        self.assertTrue(all(permission.startswith("social_agent.") for permission in permissions))

    @override_settings(
        TWO_FACTOR_ENFORCED=True,
        TWO_FACTOR_REQUIRED_ROLES=["methodist", "expert", "smm"],
    )
    def test_smm_role_requires_two_factor(self):
        role_only = User.objects.create_user("smm-2fa", role=User.Role.SMM)

        self.assertTrue(is_required_for(role_only))
