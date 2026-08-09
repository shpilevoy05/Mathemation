"""Эксплуатационный контур: health-check, лимиты, аудит, конфигурация базы."""
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import StudentGroup, User
from apps.accounts.services import create_invite
from config.security import validate_production_config


class HealthEndpointTests(TestCase):
    def test_healthz_answers_without_touching_anything(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readyz_reports_database_and_cache(self):
        response = self.client.get("/readyz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"], {"database": "ok", "cache": "ok"})

    def test_health_endpoints_are_open_without_login(self):
        # Балансировщик не умеет логиниться.
        for url in ("/healthz", "/readyz"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class ProductionConfigTests(TestCase):
    def test_sqlite_is_rejected_with_debug_off(self):
        with self.assertRaises(ImproperlyConfigured) as error:
            validate_production_config(
                debug=False,
                secret_key="x" * 60 + "aBc9!",
                allowed_hosts=["matemacia.ru"],
                database_engine="django.db.backends.sqlite3",
            )

        self.assertIn("PostgreSQL", str(error.exception))

    def test_postgres_passes(self):
        problems = validate_production_config(
            debug=False,
            secret_key="x" * 60 + "aBc9!",
            allowed_hosts=["matemacia.ru"],
            database_engine="django.db.backends.postgresql",
        )

        self.assertEqual(problems, [])

    def test_dev_mode_checks_nothing(self):
        self.assertEqual(
            validate_production_config(
                debug=True, secret_key="dev-insecure-key", allowed_hosts=["*"],
                database_engine="django.db.backends.sqlite3",
            ),
            [],
        )


@override_settings(LOGIN_MAX_ATTEMPTS=3, LOGIN_BLOCK_SECONDS=60)
class LoginBruteForceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("brute-target", password="korova-9-luna")
        self.url = reverse("login")

    def tearDown(self):
        cache.clear()

    def _attempt(self, password: str):
        return self.client.post(self.url, {"username": self.user.username, "password": password})

    def test_repeated_failures_lock_the_form(self):
        from apps.accounts.throttling import login_guard

        for _ in range(login_guard.max_attempts):
            self._attempt("wrong")

        response = self._attempt("korova-9-luna")

        # Даже верный пароль не проходит, пока действует блокировка.
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Слишком много неудачных попыток")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_successful_login_clears_the_counter(self):
        self._attempt("wrong")
        self._attempt("wrong")

        self.assertRedirects(self._attempt("korova-9-luna"), "/", fetch_redirect_response=False)

        self.client.logout()
        for _ in range(2):
            self._attempt("wrong")
        self.assertNotContains(self._attempt("wrong"), "Слишком много неудачных попыток")


class InviteBruteForceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.methodist = User.objects.create_user("guard-methodist", role=User.Role.METHODIST)
        self.group = StudentGroup.objects.create(title="Поток")

    def tearDown(self):
        cache.clear()

    def test_wrong_codes_eventually_block_the_page(self):
        from apps.accounts.throttling import invite_guard

        url = reverse("register")
        payload = {
            "code": "НЕВЕРНЫЙ", "username": "guest",
            "password1": "korova-9-luna", "password2": "korova-9-luna",
        }
        for index in range(invite_guard.max_attempts):
            self.client.post(url, {**payload, "username": f"guest{index}"})

        response = self.client.post(url, {**payload, "username": "guest-last"})

        self.assertContains(response, "Слишком много попыток ввести код")
        self.assertFalse(User.objects.filter(username="guest-last").exists())

    def test_valid_code_still_works_before_the_limit(self):
        invite = create_invite(self.methodist, group=self.group)

        response = self.client.post(reverse("register"), {
            "code": invite.code, "username": "novichok",
            "password1": "korova-9-luna", "password2": "korova-9-luna",
        })

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)


class ThrottleConfigTests(TestCase):
    def test_money_and_llm_endpoints_have_their_own_limits(self):
        from apps.ai_mentor.api import HintView
        from apps.economy.api import BuyItemView
        from apps.expert_review.api import SubmitSolutionView
        from apps.practice.api import SubmitAttemptView

        scopes = {
            SubmitAttemptView.throttle_scope,
            HintView.throttle_scope,
            BuyItemView.throttle_scope,
            SubmitSolutionView.throttle_scope,
        }

        self.assertEqual(scopes, {"attempt", "hint", "purchase", "upload"})

    def test_every_scope_has_a_configured_rate(self):
        from django.conf import settings

        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        for scope in ("user", "anon", "attempt", "hint", "purchase", "upload"):
            with self.subTest(scope=scope):
                self.assertTrue(rates.get(scope))


class AdminAuditTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("audit-admin", role=User.Role.METHODIST)
        self.client.force_login(self.admin)

    def test_publishing_a_lesson_is_recorded_with_the_actor(self):
        from apps.content.models import Lesson, TheoryBlock
        from apps.events.models import Event
        from apps.knowledge.tests import make_node

        lesson = Lesson.objects.create(node=make_node("audit-node"), title="Урок")
        TheoryBlock.objects.create(lesson=lesson, title="Коротко", body="Текст")

        self.client.post(f"/api/admin/lessons/{lesson.pk}/publish/")

        event = Event.objects.get(event_type=Event.Type.ADMIN_ACTION)
        self.assertEqual(event.payload["action"], "lesson.publish")
        self.assertEqual(event.payload["actor"], "audit-admin")
        self.assertEqual(event.payload["target"], f"lesson:{lesson.pk}")

    def test_price_change_records_both_prices(self):
        from decimal import Decimal

        from apps.billing.models import Tariff
        from apps.events.models import Event

        tariff = Tariff.objects.create(code="solo", title="Соло", price_rub=Decimal("2900.00"))

        self.client.post(
            f"/api/admin/tariffs/{tariff.pk}/new-version/",
            {"price_rub": "3300.00"}, "application/json",
        )

        payload = Event.objects.get(event_type=Event.Type.ADMIN_ACTION).payload
        self.assertEqual(payload["action"], "tariff.new_version")
        self.assertEqual(payload["price_from"], "2900.00")
        self.assertEqual(payload["price_to"], "3300.00")

    def test_granting_coins_names_the_student_and_the_amount(self):
        from apps.events.models import Event
        from apps.knowledge.tests import make_student

        student = make_student("audited-student")

        self.client.post(
            f"/api/admin/students/{student.pk}/grant-coins/",
            {"amount": 50, "comment": "Олимпиада", "reference": "olymp-7"},
            "application/json",
        )

        payload = Event.objects.get(event_type=Event.Type.ADMIN_ACTION).payload
        self.assertEqual(payload["action"], "student.grant_coins")
        self.assertEqual(payload["amount"], 50)
        self.assertEqual(payload["actor"], "audit-admin")
