import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase

from config.settings import _env_bool, _load_env, _parse_admins


class EnvBoolTests(SimpleTestCase):
    def test_true_values(self):
        for value in ("True", "true", "1", "yes"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"TEST_BOOL": value}, clear=True):
                    self.assertTrue(_env_bool("TEST_BOOL", default=False))

    def test_false_values(self):
        for value in ("False", "0", "off"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"TEST_BOOL": value}, clear=True):
                    self.assertFalse(_env_bool("TEST_BOOL", default=True))

    def test_unknown_value_uses_default(self):
        with patch.dict(os.environ, {"TEST_BOOL": "banana"}, clear=True):
            self.assertTrue(_env_bool("TEST_BOOL", default=True))
            self.assertFalse(_env_bool("TEST_BOOL", default=False))

    def test_missing_value_uses_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(_env_bool("TEST_BOOL", default=True))
            self.assertFalse(_env_bool("TEST_BOOL", default=False))

    def test_legal_consent_can_override_debug_based_default(self):
        with patch.dict(os.environ, {"LEGAL_CONSENT_ENFORCED": "1"}, clear=True):
            self.assertTrue(_env_bool("LEGAL_CONSENT_ENFORCED", default=False))
        with patch.dict(os.environ, {"LEGAL_CONSENT_ENFORCED": "0"}, clear=True):
            self.assertFalse(_env_bool("LEGAL_CONSENT_ENFORCED", default=True))


class LoadEnvTests(SimpleTestCase):
    def test_loads_values_and_preserves_existing_environment(self):
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "KEY=VALUE\n"
                'KEY2="quoted"\n'
                "# comment\n"
                "\n"
                "EXISTING=from-file\n",
                encoding="utf-8-sig",
            )
            with patch.dict(os.environ, {"EXISTING": "from-environment"}, clear=True):
                _load_env(env_path)

                self.assertEqual(os.environ["KEY"], "VALUE")
                self.assertEqual(os.environ["KEY2"], "quoted")
                self.assertEqual(os.environ["EXISTING"], "from-environment")


class AdminsParsingTests(SimpleTestCase):
    def test_parses_named_comma_separated_admins_and_skips_invalid_values(self):
        self.assertEqual(
            _parse_admins("Иван <ivan@example.ru>, Мария <maria@example.ru>, сломано"),
            [
                ("Иван", "ivan@example.ru"),
                ("Мария", "maria@example.ru"),
            ],
        )


class TestOutboundSettingsTests(SimpleTestCase):
    def test_test_settings_scrub_outbound_integrations(self):
        self.assertEqual(settings.SOCIAL_AGENT_TELEGRAM_BOT_TOKEN, "")
        self.assertEqual(settings.SOCIAL_AGENT_REVIEW_CHAT_IDS, [])
        self.assertEqual(settings.SOCIAL_AGENT_REVIEWER_USER_IDS, [])
        self.assertFalse(settings.SOCIAL_AGENT_ENABLED)
        self.assertFalse(settings.SOCIAL_AGENT_PUBLISH_ENABLED)
        self.assertEqual(
            settings.SOCIAL_AGENT_PROVIDER,
            "apps.social_agent.providers.MockProvider",
        )
        self.assertEqual(settings.SOCIAL_AGENT_LLM_API_KEY, "")
        self.assertEqual(
            settings.AI_MENTOR_PROVIDER,
            "apps.ai_mentor.providers.MockHintProvider",
        )
        self.assertEqual(settings.AI_MENTOR_LLM_API_KEY, "")
        self.assertEqual(
            settings.EMAIL_BACKEND,
            "django.core.mail.backends.locmem.EmailBackend",
        )
        self.assertEqual(settings.BILLING_PROVIDER, "apps.billing.providers.MockPaymentProvider")
        self.assertEqual(settings.BILLING_WEBHOOK_SECRET, "")
        self.assertEqual(settings.KINESCOPE_SIGNING_KEY, "")
        self.assertEqual(settings.KINESCOPE_KEY_ID, "")
