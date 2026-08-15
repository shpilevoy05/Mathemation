"""Дымовой обход интерфейса: каждая страница каждой роли должна открываться.

Тест намеренно тупой. Он не проверяет содержимое — он ловит то, что ломает
страницу целиком: несуществующая переменная в шаблоне, забытый фильтр, ошибка
в контексте после правки модели. Такие поломки не видны в юнит-тестах сервисов
и обнаруживаются вручную, случайно и поздно.

Проверяется три вещи: страница открывается, в разметке нет обращений к
несуществующим переменным и в атрибутах `style` нет дробных чисел с запятой —
последнее ломало шкалы молча, без единой ошибки в логах.
"""

import re

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User

# Django подставляет пустую строку вместо отсутствующей переменной. В обычной
# работе это удобно, в тесте — маскирует опечатку в имени.
INVALID_MARKER = ""

STRICT_TEMPLATES = override_settings(
    TEMPLATES=[
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [__import__("django.conf", fromlist=["settings"]).settings.BASE_DIR / "templates"],
            "APP_DIRS": True,
            "OPTIONS": {
                "string_if_invalid": INVALID_MARKER,
                "context_processors": [
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                    "apps.web.context_processors.cosmetics",
                    "apps.web.context_processors.access",
                ],
            },
        }
    ]
)


@STRICT_TEMPLATES
class PageSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def open(self, url: str, *, username: str):
        self.client.force_login(User.objects.get(username=username))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, f"{url} у {username}")
        body = response.content.decode()
        missing = []
        for match in re.finditer(r"\[\[НЕТ ПЕРЕМЕННОЙ:([^\]]*)\]\]", body):
            around = body[max(0, match.start() - 70):match.end() + 30]
            missing.append(f"{match.group(1)} << {' '.join(around.split())}")
        self.assertEqual(missing, [], "\n".join([f"{url}:"] + missing))

        # Русская локаль печатает дробное как «3,62». В тексте это верно, а в
        # CSS — невалидное значение: браузер отбрасывает объявление целиком, и
        # шкала схлопывается в ноль, ничего не написав в логи.
        commas = [
            " ".join(match.group(0).split())
            for match in re.finditer(r'style="[^"]*\d+,\d+[^"]*"', body)
        ]
        self.assertEqual(commas, [], f"{url}: дробное с запятой в CSS: {commas}")
        return body

    def test_student_pages_open(self):
        from apps.knowledge.models import KnowledgeNode

        node = KnowledgeNode.objects.exclude(
            node_type=KnowledgeNode.NodeType.GROUP
        ).first()
        for name in (
            "dashboard", "knowledge_map", "track", "diagnostics",
            "practice_backlog", "shop", "homework", "daily_challenge",
            "forecast", "mocks", "pricing",
        ):
            with self.subTest(page=name):
                self.open(reverse(name), username="student")
        with self.subTest(page="knowledge_node"):
            self.open(reverse("knowledge_node", args=[node.id]), username="student")
        with self.subTest(page="lesson"):
            self.open(reverse("lesson", args=[node.id]), username="student")

    def test_map_with_ceiling_overlay(self):
        self.open(reverse("knowledge_map") + "?overlay=ceiling", username="student")

    def test_parent_page_opens(self):
        self.open(reverse("parent_dashboard"), username="parent")

    def test_expert_pages_open(self):
        from apps.expert_review.models import ExpertReviewRequest

        self.open(reverse("expert_queue"), username="expert")
        review = ExpertReviewRequest.objects.filter(
            status=ExpertReviewRequest.Status.SUBMITTED
        ).first()
        if review is not None:
            self.open(reverse("expert_review", args=[review.id]), username="expert")

    def test_methodist_pages_open(self):
        self.open(reverse("methodist_dashboard"), username="methodist")
        self.open(reverse("admin-panel"), username="methodist")
