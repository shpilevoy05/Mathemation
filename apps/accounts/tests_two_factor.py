"""Второй фактор сотрудников: TOTP, резервные коды, требование на входе."""

import time

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.events.models import Event

from .models import TwoFactorDevice, User
from .two_factor import (
    code_for_step,
    current_step,
    generate_secret,
    is_required_for,
    verify_code,
)
from .two_factor_services import check_code, confirm_enrollment, reset_device, start_enrollment

ENFORCED = override_settings(
    TWO_FACTOR_ENFORCED=True, TWO_FACTOR_REQUIRED_ROLES=["methodist", "expert"]
)


def make_staff(username="methodist-2fa", role=User.Role.METHODIST) -> User:
    return User.objects.create_user(username, password="korova-9-luna", role=role)


class TotpTests(TestCase):
    def setUp(self):
        self.secret = generate_secret()

    def test_code_matches_the_current_step(self):
        step = current_step()

        self.assertEqual(verify_code(self.secret, code_for_step(self.secret, step)), step)

    def test_clock_drift_of_one_step_is_tolerated(self):
        step = current_step()

        self.assertIsNotNone(verify_code(self.secret, code_for_step(self.secret, step - 1)))
        self.assertIsNotNone(verify_code(self.secret, code_for_step(self.secret, step + 1)))

    def test_older_code_is_refused(self):
        step = current_step()

        self.assertIsNone(verify_code(self.secret, code_for_step(self.secret, step - 5)))

    def test_used_step_cannot_be_replayed(self):
        step = current_step()
        code = code_for_step(self.secret, step)

        self.assertIsNotNone(verify_code(self.secret, code))
        # Подсмотренный код живёт 30 секунд — второй раз он не проходит.
        self.assertIsNone(verify_code(self.secret, code, after_step=step))

    def test_garbage_is_refused(self):
        self.assertIsNone(verify_code(self.secret, "abcdef"))
        self.assertIsNone(verify_code(self.secret, ""))
        self.assertIsNone(verify_code(self.secret, "12345"))

    def test_another_secret_does_not_match(self):
        other = generate_secret()

        self.assertIsNone(
            verify_code(other, code_for_step(self.secret, current_step()))
        )


class EnrollmentTests(TestCase):
    def setUp(self):
        self.user = make_staff()

    def test_device_is_not_confirmed_until_the_code_is_entered(self):
        device = start_enrollment(self.user)

        self.assertFalse(device.is_confirmed)
        self.assertFalse(check_code(self.user, code_for_step(device.secret, current_step())))

    def test_confirmation_issues_recovery_codes(self):
        device = start_enrollment(self.user)

        codes = confirm_enrollment(self.user, code_for_step(device.secret, current_step()))

        device.refresh_from_db()
        self.assertTrue(device.is_confirmed)
        self.assertEqual(len(codes), device.recovery_left)
        # В базе только отпечатки: сами коды показываются один раз.
        self.assertNotIn(codes[0], device.recovery_hashes)

    def test_wrong_code_does_not_confirm(self):
        start_enrollment(self.user)

        self.assertIsNone(confirm_enrollment(self.user, "000000"))

    def test_recovery_code_works_once(self):
        device = start_enrollment(self.user)
        codes = confirm_enrollment(self.user, code_for_step(device.secret, current_step()))

        self.assertTrue(check_code(self.user, codes[0]))
        self.assertFalse(check_code(self.user, codes[0]))
        self.assertTrue(check_code(self.user, codes[1]))

    def test_code_cannot_be_replayed_at_login(self):
        device = start_enrollment(self.user)
        confirm_enrollment(self.user, code_for_step(device.secret, current_step()))
        # Следующий шаг: подтверждение уже израсходовало текущий.
        code = code_for_step(device.secret, current_step() + 1)

        self.assertTrue(check_code(self.user, code))
        self.assertFalse(check_code(self.user, code))

    def test_reset_is_written_to_the_audit_log(self):
        device = start_enrollment(self.user)
        confirm_enrollment(self.user, code_for_step(device.secret, current_step()))
        admin = User.objects.create_user("root-2fa", password="korova-9-luna", is_staff=True)

        self.assertTrue(reset_device(self.user, actor=admin))

        self.assertFalse(TwoFactorDevice.objects.filter(user=self.user).exists())
        event = Event.objects.filter(event_type=Event.Type.ADMIN_ACTION).last()
        self.assertEqual(event.payload["action"], "two_factor.reset")
        self.assertEqual(event.payload["actor"], "root-2fa")


class RequirementTests(TestCase):
    @ENFORCED
    def test_staff_roles_and_superusers_need_the_factor(self):
        self.assertTrue(is_required_for(make_staff()))
        self.assertTrue(is_required_for(make_staff("expert-2fa", User.Role.EXPERT)))
        self.assertTrue(
            is_required_for(User.objects.create_superuser("su-2fa", password="korova-9-luna"))
        )

    @ENFORCED
    def test_students_and_parents_are_not_forced(self):
        self.assertFalse(is_required_for(make_staff("student-2fa", User.Role.STUDENT)))
        self.assertFalse(is_required_for(make_staff("parent-2fa", User.Role.PARENT)))

    def test_requirement_is_off_by_setting(self):
        with override_settings(TWO_FACTOR_ENFORCED=False):
            self.assertFalse(is_required_for(make_staff()))


@ENFORCED
class LoginFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_staff()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def enroll(self) -> TwoFactorDevice:
        device = start_enrollment(self.user)
        confirm_enrollment(self.user, code_for_step(device.secret, current_step()))
        device.refresh_from_db()
        return device

    def test_staff_without_a_device_is_sent_to_setup(self):
        response = self.client.get(reverse("methodist_dashboard"))

        self.assertRedirects(response, reverse("two_factor_setup"))

    def test_django_admin_is_closed_until_the_factor_is_passed(self):
        self.enroll()

        response = self.client.get("/admin/")

        # Вход в систему не один: правило должно действовать и здесь.
        self.assertRedirects(
            response, reverse("two_factor_verify"), fetch_redirect_response=False
        )

    def test_code_opens_the_session(self):
        device = self.enroll()

        response = self.client.post(
            reverse("two_factor_verify"),
            {"code": code_for_step(device.secret, current_step() + 1)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("methodist_dashboard")).status_code, 200)

    def test_wrong_code_keeps_the_door_closed(self):
        self.enroll()

        self.client.post(reverse("two_factor_verify"), {"code": "000000"})

        self.assertRedirects(
            self.client.get(reverse("methodist_dashboard")), reverse("two_factor_verify")
        )

    @override_settings(TWO_FACTOR_MAX_ATTEMPTS=3, TWO_FACTOR_BLOCK_SECONDS=60)
    def test_guessing_is_blocked(self):
        device = self.enroll()
        for _ in range(3):
            self.client.post(reverse("two_factor_verify"), {"code": "000000"})

        response = self.client.post(
            reverse("two_factor_verify"),
            {"code": code_for_step(device.secret, current_step() + 1)},
        )

        # Даже верный код после блокировки не проходит: иначе лимит обходится
        # ожиданием следующего шага.
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Слишком много неверных кодов")

    def test_setup_page_confirms_and_shows_recovery_codes(self):
        device = start_enrollment(self.user)

        response = self.client.post(
            reverse("two_factor_setup"),
            {"code": code_for_step(device.secret, current_step())},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Фактор настроен")
        # Настроил — значит вошёл: второй раз код сразу не спрашиваем.
        self.assertEqual(self.client.get(reverse("methodist_dashboard")).status_code, 200)

    def test_student_is_not_stopped(self):
        student = make_staff("plain-student", User.Role.STUDENT)
        self.client.force_login(student)

        self.assertEqual(self.client.get("/").status_code, 200)


class ManagementCommandTests(TestCase):
    def test_command_removes_the_device(self):
        from django.core.management import call_command
        from io import StringIO

        user = make_staff("lost-phone")
        device = start_enrollment(user)
        confirm_enrollment(user, code_for_step(device.secret, current_step()))

        out = StringIO()
        call_command("reset_two_factor", "lost-phone", stdout=out)

        self.assertFalse(TwoFactorDevice.objects.filter(user=user).exists())
        self.assertIn("снят", out.getvalue())
