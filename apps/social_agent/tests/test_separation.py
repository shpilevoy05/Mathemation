import ast
from pathlib import Path

from django.test import SimpleTestCase


class SeparationTests(SimpleTestCase):
    """Allowlist project dependencies so future apps cannot silently expose user data."""

    ALLOWED_APP_MODULES = ("apps.content", "apps.social_agent")
    ALLOWED_MODEL_APPS = {"content", "social_agent"}
    MODEL_FIELDS = {"ForeignKey", "OneToOneField", "ManyToManyField"}

    @classmethod
    def _is_allowed_module(cls, module):
        return any(
            module == allowed or module.startswith(f"{allowed}.")
            for allowed in cls.ALLOWED_APP_MODULES
        )

    @staticmethod
    def _string_value(node):
        return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None

    @classmethod
    def _model_target(cls, node):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            return None
        if node.func.attr not in cls.MODEL_FIELDS:
            return None
        if node.args:
            target = cls._string_value(node.args[0])
            if target is not None:
                return target
        for keyword in node.keywords:
            if keyword.arg == "to":
                return cls._string_value(keyword.value)
        return None

    @classmethod
    def _get_model_app_label(cls, node):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "apps"
            and node.func.attr == "get_model"
            and node.args
        ):
            return None
        target = cls._string_value(node.args[0]) if node.args else None
        if target is None:
            for keyword in node.keywords:
                if keyword.arg == "app_label":
                    target = cls._string_value(keyword.value)
                    break
        return target.split(".", 1)[0] if target else None

    def test_social_agent_import_boundary(self):
        root = Path(__file__).resolve().parents[1]
        violations = []
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        names = []
                    elif node.module == "apps":
                        names = [f"apps.{alias.name}" for alias in node.names]
                    else:
                        names = [node.module or ""]
                else:
                    names = []
                for name in names:
                    if name.startswith("apps.") and not self._is_allowed_module(name):
                        violations.append(f"{path.name}: {name}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "get_user_model":
                    violations.append(f"{path.name}: get_user_model()")
                target = self._model_target(node)
                if target and target.split(".", 1)[0] not in self.ALLOWED_MODEL_APPS:
                    violations.append(f"{path.name}: model target {target}")
                app_label = self._get_model_app_label(node)
                if app_label and app_label not in self.ALLOWED_MODEL_APPS:
                    violations.append(f"{path.name}: apps.get_model({app_label})")
        self.assertEqual(violations, [])
