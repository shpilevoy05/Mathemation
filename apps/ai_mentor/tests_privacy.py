import hashlib
import hmac
import json

from django.test import TestCase, override_settings

from apps.accounts.models import ParentProfile, User
from apps.knowledge.tests import make_node, make_student
from apps.practice.tests import make_assignment

from .models import AiHintMessage, AiHintSession, AiOutboundRequest
from .privacy import defend_payload, pseudonym_for, scrub, student_for_pseudonym
from .providers import LLMHintProvider


class PrivacyScrubberTests(TestCase):
    def setUp(self):
        self.student = make_student("ivan.petrov")
        user = self.student.user
        user.first_name = "Иван"
        user.last_name = "Петров"
        user.email = "ivan.petrov@example.ru"
        user.save(update_fields=["first_name", "last_name", "email"])
        parent_user = User.objects.create_user(
            "mama.petrov",
            first_name="Алёна",
            last_name="Петрова",
            email="mama@example.ru",
        )
        parent = ParentProfile.objects.create(user=parent_user)
        parent.children.add(self.student)

    def test_pii_is_removed_and_math_is_preserved(self):
        cases = [
            ("Иван, помоги", "[имя], помоги"),
            ("иван петров решает", "[имя] решает"),
            ("IVAN.PETROV вошёл", "[логин] вошёл"),
            ("ivan.petrov@example.ru", "[почта]"),
            ("other.person@mail.example", "[почта]"),
            ("Алёна Петрова", "[имя]"),
            ("Алена, подскажи", "[имя], подскажи"),
            ("mama@example.ru", "[почта]"),
            ("+7 (999) 123-45-67", "[телефон]"),
            ("8 999 123 45 67", "[телефон]"),
            ("+44 20 7946 0958", "[телефон]"),
            ("https://example.ru/path?student=ivan", "[ссылка]"),
            ("Меня зовут Сергей Смирнов", "[имя]"),
            ("я — Сергей Смирнов", "[имя]"),
            ("112-233-445 95", "[номер]"),
            ("45 08 123456", "[номер]"),
            ("1234 5678 9012 3456", "[номер]"),
            ("x^2-5x+6=0", "x^2-5x+6=0"),
            ("3/4 + 5/8 = 11/8", "3/4 + 5/8 = 11/8"),
            (r"\frac{2}{3}+\sqrt{5}", r"\frac{2}{3}+\sqrt{5}"),
            ("x ∈ (2; 5)", "x ∈ (2; 5)"),
            ("профиль ЕГЭ 2027", "профиль ЕГЭ 2027"),
            ("0,375 и 12.5", "0,375 и 12.5"),
            ("корни -2 и 3", "корни -2 и 3"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(scrub(source, self.student).text, expected)

    def test_short_names_do_not_corrupt_longer_math_words(self):
        user = self.student.user
        user.first_name = "Ева"
        user.last_name = "Лев"
        user.save(update_fields=["first_name", "last_name"])

        statement = "Найдите левую часть и левый конец отрезка"
        self.assertEqual(scrub(statement, self.student).text, statement)
        cleaned, _counts = defend_payload({"statement": statement}, self.student)
        self.assertEqual(cleaned["statement"], statement)
        self.assertEqual(scrub("Меня зовут Ева Лев", self.student).text, "[имя]")

    def test_phone_patterns_preserve_math_and_remove_real_phones(self):
        unchanged = (
            "+8(9-1)-2(3-4)-5(6-7)",
            "8-1-2-3-4-5-6-7-8-9-0",
        )
        phones = (
            "+7 (912) 345-67-89",
            "8 912 345 67 89",
            "89123456789",
            "+44 20 7946 0958",
        )
        for source in unchanged:
            with self.subTest(source=source):
                self.assertEqual(scrub(source, self.student).text, source)
        for source in phones:
            with self.subTest(source=source):
                self.assertEqual(scrub(source, self.student).text, "[телефон]")

    def test_self_introduction_requires_capitalized_name(self):
        ordinary_text = "я — новичок в теме, помогите"
        self.assertEqual(scrub(ordinary_text, self.student).text, ordinary_text)
        self.assertEqual(scrub("Я — Иван Петров", self.student).text, "[имя]")

    @override_settings(AI_PRIVACY_PSEUDONYM_KEY="", SECRET_KEY="app-secret")
    def test_pseudonym_is_stable_and_uses_key_separation(self):
        first = pseudonym_for(self.student)
        self.assertEqual(first, pseudonym_for(self.student))
        self.assertRegex(first, r"^stu_[0-9a-f]{24}$")
        raw_secret = "stu_" + hmac.new(
            b"app-secret", str(self.student.pk).encode("ascii"), hashlib.sha256
        ).hexdigest()[:24]
        self.assertNotEqual(first, raw_secret)
        with self.settings(AI_PRIVACY_PSEUDONYM_KEY="dedicated-key"):
            self.assertNotEqual(first, pseudonym_for(self.student))


@override_settings(
    AI_MENTOR_LLM_FORMAT="openai",
    AI_MENTOR_LLM_BASE_URL="https://api.deepseek.com/chat/completions",
    AI_MENTOR_LLM_API_KEY="test-key",
    AI_MENTOR_LLM_MODEL="deepseek-chat",
    AI_PRIVACY_PSEUDONYM_KEY="privacy-test-key",
)
class PrivatePayloadTests(TestCase):
    def setUp(self):
        self.student = make_student("ivan.petrov")
        user = self.student.user
        user.first_name = "Иван"
        user.last_name = "Петров"
        user.email = "ivan.petrov@example.ru"
        user.save(update_fields=["first_name", "last_name", "email"])
        self.node = make_node("privacy-node")
        self.assignment = make_assignment(self.node, answer="2")
        self.assignment.statement = "Решите уравнение x^2-5x+6=0."
        self.assignment.reference_solution = "Разложите квадратный трёхчлен на множители."
        self.assignment.save(update_fields=["statement", "reference_solution"])
        self.session = AiHintSession.objects.create(
            student=self.student, assignment=self.assignment, node=self.node
        )
        AiHintMessage.objects.create(
            session=self.session,
            role=AiHintMessage.Role.STUDENT,
            text="Мой логин ivan.petrov, телефон +7 999 123-45-67",
        )

    def test_payload_has_no_pii_and_audit_metadata_is_created(self):
        captured = {}

        def transport(url, headers, payload):
            captured["payload"] = payload
            return {
                "choices": [{"message": {"content": "Какие два числа стоит подобрать?"}}],
                "usage": {"prompt_tokens": 123, "completion_tokens": 17},
            }

        result = LLMHintProvider(transport=transport).generate_hint(
            self.assignment,
            "Меня зовут Иван Петров, почта ivan.petrov@example.ru, "
            "как решить x^2-5x+6=0?",
            1,
            session=self.session,
        )

        self.assertEqual(result, "Какие два числа стоит подобрать?")
        serialized = json.dumps(captured["payload"], ensure_ascii=False).casefold()
        for pii in ("иван", "петров", "ivan.petrov", "ivan.petrov@example.ru", "+7 999"):
            self.assertNotIn(pii, serialized)
        self.assertIn("x^2-5x+6=0", serialized)
        pseudonym = pseudonym_for(self.student)
        self.assertEqual(captured["payload"]["user"], pseudonym)
        audit = AiOutboundRequest.objects.get()
        self.assertEqual(audit.student, self.student)
        self.assertEqual(audit.pseudonym, pseudonym)
        self.assertEqual(audit.prompt_tokens, 123)
        self.assertEqual(audit.completion_tokens, 17)
        self.assertGreater(sum(audit.redaction_counts.values()), 0)
        self.assertEqual(student_for_pseudonym(pseudonym), self.student)

    @override_settings(AI_MENTOR_LLM_FORMAT="yandexgpt")
    def test_yandex_payload_has_no_user_identifier_field(self):
        captured = {}

        def transport(url, headers, payload):
            captured["payload"] = payload
            return {"result": {"alternatives": [{"message": {"text": "С чего начнёшь?"}}]}}

        LLMHintProvider(transport=transport).generate_hint(
            self.assignment, "Иван просит подсказку", 1, session=self.session
        )

        self.assertNotIn("user", captured["payload"])
        self.assertNotIn("Иван", json.dumps(captured["payload"], ensure_ascii=False))
