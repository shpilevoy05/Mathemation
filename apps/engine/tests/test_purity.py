"""Architecture guard for the extractable engine boundary."""
import ast
import importlib
from pathlib import Path

from django.test import SimpleTestCase

import apps.engine


class EnginePurityTests(SimpleTestCase):
    def test_engine_modules_import_without_django_or_other_apps(self):
        package_dir = Path(apps.engine.__file__).resolve().parent
        module_files = [
            path
            for path in package_dir.glob("*.py")
            if path.name != "__init__.py"
        ]
        for path in module_files:
            importlib.import_module(f"apps.engine.{path.stem}")
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for statement in ast.walk(tree):
                imported: list[str] = []
                if isinstance(statement, ast.Import):
                    imported = [alias.name for alias in statement.names]
                elif isinstance(statement, ast.ImportFrom) and statement.level == 0:
                    imported = [statement.module or ""]
                for module_name in imported:
                    self.assertFalse(
                        module_name == "django" or module_name.startswith("django."),
                        f"{path.name} imports forbidden module {module_name}",
                    )
                    self.assertFalse(
                        (module_name == "apps" or module_name.startswith("apps."))
                        and not module_name.startswith("apps.engine"),
                        f"{path.name} imports outside engine: {module_name}",
                    )

