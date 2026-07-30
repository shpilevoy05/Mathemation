"""Тесты security-конфигурации (config/security.py)."""
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from .security import (
    DEV_SECRET_KEY,
    HSTS_SECONDS,
    hardening_settings,
    validate_production_config,
)

GOOD = {
    "debug": False,
    "secret_key": "s3cret-key-with-enough-entropy-0123456789-abcdefghij-klmnop",
    "allowed_hosts": ["matemacia.ru"],
}


class HardeningSettingsTests(SimpleTestCase):
    def test_production_enables_https_and_secure_cookies(self):
        values = hardening_settings(debug=False)
        self.assertTrue(values["SECURE_SSL_REDIRECT"])
        self.assertTrue(values["SESSION_COOKIE_SECURE"])
        self.assertTrue(values["CSRF_COOKIE_SECURE"])
        self.assertEqual(values["SECURE_HSTS_SECONDS"], HSTS_SECONDS)
        self.assertTrue(values["SECURE_HSTS_INCLUDE_SUBDOMAINS"])
        self.assertTrue(values["SECURE_HSTS_PRELOAD"])
        self.assertEqual(values["X_FRAME_OPTIONS"], "DENY")
        self.assertEqual(
            values["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https")
        )

    def test_production_without_proxy_has_no_forwarded_header(self):
        self.assertNotIn(
            "SECURE_PROXY_SSL_HEADER", hardening_settings(debug=False, behind_proxy=False)
        )

    def test_dev_keeps_http_usable_but_headers_on(self):
        values = hardening_settings(debug=True)
        self.assertFalse(values["SECURE_SSL_REDIRECT"])
        self.assertFalse(values["SESSION_COOKIE_SECURE"])
        self.assertEqual(values["SECURE_HSTS_SECONDS"], 0)
        self.assertTrue(values["SECURE_CONTENT_TYPE_NOSNIFF"])
        self.assertEqual(values["X_FRAME_OPTIONS"], "DENY")
        self.assertTrue(values["SESSION_COOKIE_HTTPONLY"])


class ValidateProductionConfigTests(SimpleTestCase):
    def test_good_config_passes(self):
        self.assertEqual(validate_production_config(**GOOD), [])

    def test_debug_skips_validation(self):
        self.assertEqual(
            validate_production_config(
                debug=True, secret_key=DEV_SECRET_KEY, allowed_hosts=["*"]
            ),
            [],
        )

    def test_dev_secret_key_blocks_start(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_config(**{**GOOD, "secret_key": DEV_SECRET_KEY})
        self.assertIn("DJANGO_SECRET_KEY", str(ctx.exception))

    def test_weak_secret_key_blocks_start(self):
        for weak in ("short", "k" * 60):
            with self.subTest(secret_key=weak):
                with self.assertRaises(ImproperlyConfigured) as ctx:
                    validate_production_config(**{**GOOD, "secret_key": weak})
                self.assertIn("слишком слабый", str(ctx.exception))

    def test_wildcard_allowed_hosts_blocks_start(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_config(**{**GOOD, "allowed_hosts": ["*"]})
        self.assertIn("DJANGO_ALLOWED_HOSTS", str(ctx.exception))

    def test_empty_allowed_hosts_blocks_start(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_production_config(**{**GOOD, "allowed_hosts": []})

    def test_private_media_inside_public_media_blocks_start(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_config(
                **GOOD,
                media_root="/srv/matemacia/media",
                private_media_root="/srv/matemacia/media/private",
            )
        self.assertIn("PRIVATE_MEDIA_ROOT", str(ctx.exception))

    def test_private_media_outside_public_media_passes(self):
        self.assertEqual(
            validate_production_config(
                **GOOD,
                media_root="/srv/matemacia/media",
                private_media_root="/srv/matemacia/private-media",
            ),
            [],
        )

    def test_all_problems_reported_at_once(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            validate_production_config(
                debug=False, secret_key=DEV_SECRET_KEY, allowed_hosts=["*"]
            )
        message = str(ctx.exception)
        self.assertIn("DJANGO_SECRET_KEY", message)
        self.assertIn("DJANGO_ALLOWED_HOSTS", message)
