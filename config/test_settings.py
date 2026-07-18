import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from config.settings import _env_bool, _load_env


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
