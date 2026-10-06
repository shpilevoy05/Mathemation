"""Диагностика, снятие косметики, необязательная вторая часть и панель."""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.diagnostics.models import DiagnosticResult, DiagnosticTest
from apps.economy.models import InventoryItem, ShopItem
from apps.economy.services import equip, purchase
from apps.economy.services import grant
from apps.economy.models import LedgerEntry


class DiagnosticFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def setUp(self):
        self.user = User.objects.get(username="student")
        self.student = self.user.student_profile
        self.client.force_login(self.user)

    def test_page_lists_available_tests(self):
        response = self.client.get(reverse("diagnostics"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["tests"])
        self.assertContains(response, "Входная диагностика")

    def test_student_starts_and_finishes_a_diagnostic(self):
        test = DiagnosticTest.objects.filter(is_active=True).first()

        started = self.client.post(f"/api/diagnostics/{test.id}/start/", {}, "application/json")
        result_id = started.json()["result_id"]
        run_page = self.client.get(reverse("diagnostic_run", args=[result_id]))
        answers = {
            str(assignment.id): assignment.correct_answer
            for assignment in test.assignments.all()
        }
        finished = self.client.post(
            f"/api/diagnostics/results/{result_id}/submit/",
            {"answers": answers}, "application/json",
        )

        self.assertEqual(run_page.status_code, 200)
        self.assertEqual(finished.status_code, 200)
        self.assertEqual(
            DiagnosticResult.objects.get(pk=result_id).status,
            DiagnosticResult.Status.COMPLETED,
        )
        self.assertGreater(finished.json()["primary_score"], 0)

    def test_finished_diagnostic_shows_up_on_the_page(self):
        test = DiagnosticTest.objects.filter(is_active=True).first()
        started = self.client.post(f"/api/diagnostics/{test.id}/start/", {}, "application/json")
        self.client.post(
            f"/api/diagnostics/results/{started.json()['result_id']}/submit/",
            {"answers": {}}, "application/json",
        )

        response = self.client.get(reverse("diagnostics"))

        self.assertIsNotNone(response.context["last_completed"])
        self.assertContains(response, "Последний результат")

    def test_dashboard_links_to_the_diagnostic(self):
        self.assertContains(self.client.get(reverse("dashboard")), reverse("diagnostics"))


class UnequipTests(TestCase):
    def setUp(self):
        from apps.knowledge.tests import make_student

        self.student = make_student("look-student")
        grant(self.student, 500, LedgerEntry.Reason.ADMIN_GRANT, reference="look")
        self.avatar = ShopItem.objects.create(
            title="Аватар «Сова»", slot=ShopItem.Slot.AVATAR, code="owl", price_coins=40
        )
        self.theme = ShopItem.objects.create(
            title="Тема «Ночь»", slot=ShopItem.Slot.THEME, code="dark", price_coins=120
        )
        for item in (self.avatar, self.theme):
            purchase(self.student, item)
            equip(self.student, item)
        self.client.force_login(self.student.user)

    def test_single_item_can_be_taken_off_but_stays_owned(self):
        response = self.client.post(
            f"/api/shop/items/{self.avatar.id}/unequip/", {}, "application/json"
        )

        self.assertEqual(response.status_code, 200)
        inventory = InventoryItem.objects.get(student=self.student, item=self.avatar)
        self.assertFalse(inventory.is_equipped)
        self.assertTrue(InventoryItem.objects.filter(student=self.student, item=self.avatar).exists())

    def test_reset_returns_the_cabinet_to_the_default_look(self):
        response = self.client.post("/api/shop/reset-look/", {}, "application/json")

        self.assertEqual(response.json()["unequipped"], 2)
        self.assertFalse(
            InventoryItem.objects.filter(student=self.student, is_equipped=True).exists()
        )

    def test_shop_offers_the_take_off_button_while_something_is_worn(self):
        response = self.client.get(reverse("shop"))

        self.assertTrue(response.context["has_equipped"])
        self.assertContains(response, "unequip")
        self.assertContains(response, "Базовое оформление")


class PanelBootTests(TestCase):
    """Панель падала целиком: словарь действий печатался repr-ом Python."""

    def setUp(self):
        self.client.force_login(
            User.objects.create_user("panel-boot", role=User.Role.METHODIST)
        )

    def test_row_actions_are_valid_json(self):
        import json
        import re

        page = self.client.get("/panel/").content.decode()

        raw = re.search(
            r'<script id="row-actions" type="application/json">(.*?)</script>', page, re.S
        )
        self.assertIsNotNone(raw)
        actions = json.loads(raw.group(1))
        self.assertIn("payments", actions)
        self.assertTrue(actions["payments"][0]["confirm"])

    def test_tariff_price_cannot_be_edited_in_place(self):
        from decimal import Decimal

        from apps.billing.models import Tariff

        tariff = Tariff.objects.create(
            code="solo", title="Соло", price_rub=Decimal("2900.00")
        )

        response = self.client.patch(
            f"/api/admin/tariffs/{tariff.pk}/",
            {"title": "Соло+", "price_rub": "1.00"}, "application/json",
        )

        self.assertEqual(response.status_code, 200)
        tariff.refresh_from_db()
        self.assertEqual(tariff.title, "Соло+")
        self.assertEqual(tariff.price_rub, Decimal("2900.00"))
