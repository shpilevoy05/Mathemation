import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from django.template import Context, Template
from django.test import SimpleTestCase
from django.templatetags.static import static
from django.urls import reverse


class AssetTemplateTagTests(SimpleTestCase):
    def render_asset(self, path: str) -> str:
        template = Template("{% load assets %}{% asset path %}")
        return template.render(Context({"path": path}))

    def test_asset_url_contains_ten_character_content_hash(self):
        with TemporaryDirectory() as directory:
            asset_path = Path(directory) / "css" / "test.css"
            asset_path.parent.mkdir()
            asset_path.write_text("body { color: navy; }", encoding="utf-8")

            with self.settings(STATICFILES_DIRS=[directory]):
                url = self.render_asset("css/test.css")

        self.assertRegex(url, rf"^{re.escape(static('css/test.css'))}\?v=[0-9a-f]{{10}}$")

    def test_asset_hash_changes_when_file_content_changes(self):
        with TemporaryDirectory() as directory:
            asset_path = Path(directory) / "js" / "test.js"
            asset_path.parent.mkdir()
            asset_path.write_text("const value = 1;", encoding="utf-8")

            with self.settings(STATICFILES_DIRS=[directory]):
                first_url = self.render_asset("js/test.js")
                first_mtime_ns = asset_path.stat().st_mtime_ns
                asset_path.write_text("const value = 2;", encoding="utf-8")
                os.utime(asset_path, ns=(first_mtime_ns + 1_000_000_000,) * 2)
                second_url = self.render_asset("js/test.js")

        self.assertNotEqual(first_url, second_url)

    def test_missing_asset_uses_plain_static_url(self):
        with TemporaryDirectory() as directory:
            static_root = Path(directory) / "collected"
            with self.settings(
                STATICFILES_DIRS=[Path(directory) / "source"],
                STATIC_ROOT=static_root,
            ):
                url = self.render_asset("css/missing.css")

        self.assertEqual(url, static("css/missing.css"))


class BaseAssetVersionTests(SimpleTestCase):
    def test_base_page_versions_app_stylesheet(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "app.css?v=")
