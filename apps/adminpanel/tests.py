"""Панель администратора: доступ по роли и действия сверх CRUD."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import StudentGroup, User
from apps.billing.models import Payment, PaymentMethod, Promotion, Subscription, Tariff
from apps.billing.services import confirm_payment, start_payment
from apps.content.models import Homework, Lesson, TheoryBlock
from apps.economy.models import LedgerEntry
from apps.economy.services import get_wallet
from apps.knowledge.models import KnowledgeDependency
from apps.knowledge.tests import make_node, make_student
from apps.planning.models import PlanChangeLog, StudyPlanItem
from apps.planning.services import build_study_plan
from apps.practice.tests import make_assignment


def make_admin(username="panel-admin") -> User:
    return User.objects.create_user(username=username, role=User.Role.METHODIST)


class PanelAccessTests(TestCase):
    def setUp(self):
        self.url = "/api/admin/lessons/"

    def test_admin_gets_access(self):
        self.client.force_login(make_admin())
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_expert_and_student_are_denied(self):
        for role in (User.Role.EXPERT, User.Role.STUDENT, User.Role.PARENT):
            with self.subTest(role=role):
                self.client.force_login(
                    User.objects.create_user(username=f"u-{role}", role=role)
                )
                self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_staff_without_admin_role_denied(self):
        self.client.force_login(
            User.objects.create_user(username="staffy", role=User.Role.EXPERT, is_staff=True)
        )
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_anonymous_denied(self):
        self.assertIn(self.client.get(self.url).status_code, (401, 403))

    def test_panel_page_requires_admin_role(self):
        self.client.force_login(
            User.objects.create_user(username="curious", role=User.Role.STUDENT)
        )
        self.assertEqual(self.client.get("/panel/").status_code, 403)
        self.client.force_login(make_admin("page-admin"))
        self.assertEqual(self.client.get("/panel/").status_code, 200)


class PanelPricingTests(TestCase):
    """Прайс настраивается из панели: способы оплаты, скидки и акции."""

    def setUp(self):
        self.client.force_login(make_admin("pricing-admin"))

    def test_admin_creates_a_payment_method(self):
        response = self.client.post(
            "/api/admin/payment-methods/",
            {"code": "sbp", "title": "СБП", "description": "Перевод по QR", "order": 1},
            "application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["is_placeholder"])
        self.assertEqual(PaymentMethod.objects.get(code="sbp").title, "СБП")

    def test_admin_creates_a_promotion_and_cannot_forge_its_counter(self):
        response = self.client.post(
            "/api/admin/promotions/",
            {
                "title": "Первый месяц", "code": "START10", "kind": "percent",
                "value": "10.00", "tariff_codes": ["solo"], "used_count": 99,
            },
            "application/json",
        )

        self.assertEqual(response.status_code, 201)
        promotion = Promotion.objects.get(code="START10")
        self.assertEqual(promotion.used_count, 0)
        self.assertTrue(response.json()["is_running"])

    def test_promotion_can_be_switched_off(self):
        promotion = Promotion.objects.create(title="Акция", value=10)

        response = self.client.patch(
            f"/api/admin/promotions/{promotion.pk}/", {"is_active": False}, "application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_running"])

    def test_admin_creates_an_addon(self):
        response = self.client.post(
            "/api/admin/addons/",
            {
                "code": "extra-hints", "kind": "mentor_hints",
                "title": "Пакет подсказок", "price_rub": "490.00",
                "quantity": 50, "unit_label": "подсказок",
            },
            "application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["price_per_unit"], "9.80")

    def test_pricing_sections_are_listed_in_the_panel_page(self):
        page = self.client.get("/panel/").content.decode()

        self.assertIn("Способы оплаты", page)
        self.assertIn("Скидки и акции", page)
        self.assertIn("Докупки (апселлы)", page)

    def test_pricing_endpoints_are_closed_for_students(self):
        self.client.force_login(User.objects.create_user("shopper", role=User.Role.STUDENT))

        for url in ("/api/admin/payment-methods/", "/api/admin/promotions/", "/api/admin/addons/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)


class PanelActionsTests(TestCase):
    def setUp(self):
        self.admin = make_admin("actions-admin")
        self.client.force_login(self.admin)
        self.student = make_student("panel-student")
        self.node = make_node("panel-node")
        self.lesson = Lesson.objects.create(node=self.node, title="Урок")

    def test_assign_homework_to_group(self):
        homework = Homework.objects.create(
            title="Домашка", status=Homework.Status.PUBLISHED
        )
        homework.tasks.create(assignment=make_assignment(self.node))
        group = StudentGroup.objects.create(title="Поток")
        group.students.add(self.student)

        response = self.client.post(
            f"/api/admin/homeworks/{homework.pk}/assign/", {"group": group.pk}, "application/json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["assigned"], 1)
        self.assertEqual(homework.submissions.count(), 1)

    def test_grant_coins_writes_ledger_with_author(self):
        response = self.client.post(
            f"/api/admin/students/{self.student.pk}/grant-coins/",
            {"amount": 50, "comment": "Олимпиада", "reference": "olymp-1"},
            "application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_wallet(self.student).balance, 50)
        entry = LedgerEntry.objects.get()
        self.assertEqual(entry.created_by, self.admin)
        self.assertEqual(entry.reason, LedgerEntry.Reason.ADMIN_GRANT)

    def test_grant_coins_is_idempotent_by_reference(self):
        for _ in range(2):
            self.client.post(
                f"/api/admin/students/{self.student.pk}/grant-coins/",
                {"amount": 50, "reference": "olymp-1"}, "application/json",
            )
        self.assertEqual(get_wallet(self.student).balance, 50)

    def test_deactivate_and_reactivate_student(self):
        self.client.post(f"/api/admin/students/{self.student.pk}/deactivate/")
        self.student.user.refresh_from_db()
        self.assertFalse(self.student.user.is_active)
        self.client.post(f"/api/admin/students/{self.student.pk}/reactivate/")
        self.student.user.refresh_from_db()
        self.assertTrue(self.student.user.is_active)

    def test_invite_creation_returns_code(self):
        response = self.client.post(
            "/api/admin/invites/", {"role": "student"}, "application/json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["code"])

    def test_tariff_price_change_creates_new_version(self):
        tariff = Tariff.objects.create(
            code="pro", version=1, title="Про", price_rub=Decimal("1990.00")
        )
        response = self.client.post(
            f"/api/admin/tariffs/{tariff.pk}/new-version/",
            {"price_rub": "2490.00"}, "application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["version"], 2)
        tariff.refresh_from_db()
        self.assertFalse(tariff.is_active)

    def test_refund_payment_cancels_subscription(self):
        tariff = Tariff.objects.create(
            code="base", version=1, title="Базовый", price_rub=Decimal("990.00")
        )
        payer = User.objects.create_user("payer-panel", role=User.Role.PARENT)
        payment, _ = start_payment(self.student, tariff, payer, "panel-key")
        confirm_payment(payment)

        response = self.client.post(f"/api/admin/payments/{payment.pk}/refund/")
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REFUNDED)
        self.assertEqual(
            Subscription.objects.get(student=self.student).status,
            Subscription.Status.CANCELED,
        )

    def test_ledger_is_read_only(self):
        response = self.client.post(
            "/api/admin/ledger/", {"amount": 100}, "application/json"
        )
        self.assertEqual(response.status_code, 405)

    def test_assignment_new_version_keeps_history(self):
        assignment = make_assignment(self.node, answer="42")
        response = self.client.post(
            f"/api/admin/assignments/{assignment.pk}/new-version/",
            {"statement": "Уточнённое условие", "change_note": "Опечатка"},
            "application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["number"], 2)
        assignment.refresh_from_db()
        self.assertEqual(assignment.statement, "Уточнённое условие")
        self.assertEqual(assignment.versions.count(), 2)

    def test_assignment_versions_are_read_only(self):
        assignment = make_assignment(self.node)
        response = self.client.post(
            "/api/admin/assignment-versions/",
            {"assignment": assignment.pk, "number": 5, "statement": "x"},
            "application/json",
        )
        self.assertEqual(response.status_code, 405)

    def test_daily_challenge_can_be_created(self):
        assignment = make_assignment(self.node)
        response = self.client.post(
            "/api/admin/daily-challenges/",
            {
                "date": (timezone.localdate() + timedelta(days=1)).isoformat(),
                "assignment": assignment.pk,
                "reward_coins": 20,
            },
            "application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["created_by"], self.admin.pk)
