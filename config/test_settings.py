import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from config.settings import _load_env


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
