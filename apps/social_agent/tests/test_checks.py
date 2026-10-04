from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from apps.content.models import Assignment
from apps.social_agent.checks import (
    all_passed,
    answer_integrity,
    banned_phrase,
    competitor,
    length,
    number_whitelist,
    personal_data,
    run_checks,
)
from apps.social_agent.models import BrandProfile, Channel, Post, PostCheck, Rubric
from apps.social_agent.sources import SourceMaterial


class CheckFunctionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.profile = BrandProfile.objects.create(
            name="Матемация",
            forbidden_phrases=["секретный метод"],
            competitors=["Чужая Школа", "ЕГЭ+"],
        )

    def test_banned_phrase_positive_and_negative(self):
        self.assertTrue(banned_phrase("Спокойно разберём тему", self.profile).passed)
        for text in (
            "Гарантируем результат",
            "Получишь 100 баллов",
            "Скидка 20%",
            "Курс за 500 руб",
            "Бесплатно",
            "Мы вылечим тревожность",
            "Наш секретный метод",
        ):
            with self.subTest(text=text):
                self.assertFalse(banned_phrase(text, self.profile).passed)

    def test_competitor_uses_case_insensitive_whole_words(self):
        self.assertFalse(competitor("Сравним с ЧУЖАЯ ШКОЛА", self.profile).passed)
        self.assertFalse(competitor("Курс ЕГЭ+ хорош", self.profile).passed)
        self.assertTrue(competitor("Это чужая школьная задача", self.profile).passed)

    def test_number_whitelist_rejects_invented_number(self):
        material = SourceMaterial(facts={"answer": "0,5", "count": 12}, reference_text="", source_ref="test")
        self.assertTrue(number_whitelist("Ответ 0.5, решим 12 задач", material).passed)
        self.assertFalse(number_whitelist("Ответ 0,5, решим 13 задач", material).passed)

    def test_number_whitelist_ignores_list_markers_and_publication_datetime(self):
        material = SourceMaterial(facts={}, reference_text="", source_ref="test")
        published = timezone.make_aware(datetime(2027, 5, 4, 12, 30))
        text = "1. Первый шаг\n2) Второй шаг\nПубликация 04.05.2027 12:30"
        self.assertTrue(number_whitelist(text, material, published).passed)

    def test_answer_integrity_for_revealed_and_question_only_versions(self):
        assignment = Assignment.objects.create(
            title="Сумма",
            statement="Сколько будет два плюс два?",
            correct_answer="4",
            reference_solution="Сложение даёт четыре.",
            exam_part=Assignment.Part.PART1,
        )
        revealed = SourceMaterial(
            facts={"correct_answer": "4"}, reference_text="", source_ref=f"assignment:{assignment.pk}",
            assignment_id=assignment.pk, reveal_answer=True,
        )
        hidden = SourceMaterial(
            facts={"correct_answer": "4"}, reference_text="", source_ref=f"assignment:{assignment.pk}",
            assignment_id=assignment.pk, reveal_answer=False,
        )
        self.assertTrue(answer_integrity("Ответ: 4", revealed).passed)
        self.assertFalse(answer_integrity("Ответ: 5", revealed).passed)
        self.assertTrue(answer_integrity("Найдите ответ самостоятельно", hidden).passed)
        self.assertFalse(answer_integrity("Правильный ответ: 4", hidden).passed)

        assignment.correct_answer = "0,5"
        assignment.save(update_fields=["correct_answer"])
        self.assertTrue(answer_integrity("Ответ: 0.5.", revealed).passed)
        self.assertFalse(answer_integrity("Получилось 0.5", hidden).passed)

    def test_question_statement_is_excluded_from_answer_leak_scan(self):
        assignment = Assignment.objects.create(
            title="Рабочие",
            statement=r"За сколько дней $2$ рабочих выполнят задачу? Сравните с $x^2$.",
            correct_answer="2",
            reference_solution="Эталонное решение.",
            exam_part=Assignment.Part.PART1,
        )
        material = SourceMaterial(
            facts={"statement": assignment.statement, "correct_answer": "2"},
            reference_text=assignment.statement,
            source_ref=f"assignment:{assignment.pk}",
            assignment_id=assignment.pk,
        )
        raw_post = f"Задача дня\n{assignment.statement}\nРешите самостоятельно."
        rendered_post = "Задача дня\nЗа сколько дней 2 рабочих выполнят задачу? Сравните с x².\nРешите самостоятельно."
        self.assertTrue(answer_integrity(raw_post, material).passed)
        self.assertTrue(answer_integrity(rendered_post, material).passed)
        self.assertFalse(answer_integrity(f"{rendered_post}\nПолучилось 2", material).passed)

    def test_length_hard_limit_and_soft_recommendation(self):
        self.assertTrue(length("коротко", Rubric.SourceKind.EVERGREEN).passed)
        soft = length("x" * 1300, Rubric.SourceKind.EVERGREEN)
        self.assertTrue(soft.passed)
        self.assertIn("рекомендовано", soft.detail)
        self.assertFalse(length("x" * 4097, Rubric.SourceKind.EVERGREEN).passed)

    def test_personal_data_positive_and_negative(self):
        self.assertTrue(personal_data("Ссылка: https://example.com/page").passed)
        for text in (
            "Пишите pupil@example.com",
            "Телефон +7 (999) 123-45-67",
            "https://example.com/reset?token=secret",
        ):
            with self.subTest(text=text):
                self.assertFalse(personal_data(text).passed)


class RunChecksTests(TestCase):
    def test_run_checks_persists_all_results_and_all_passed(self):
        BrandProfile.objects.create(name="Матемация")
        channel = Channel.objects.create(platform="telegram", title="Канал", external_id="@test")
        rubric = Rubric.objects.create(
            slug="tip", title="Совет", audience="both", source_kind=Rubric.SourceKind.LESSON_TIP
        )
        post = Post.objects.create(
            channel=channel, rubric=rubric, text="Полезный совет", scheduled_for=timezone.now()
        )
        material = SourceMaterial(facts={}, reference_text="", source_ref="test")

        checks = run_checks(post, material)

        self.assertEqual(len(checks), len(PostCheck.Kind.values))
        self.assertEqual(post.checks.count(), len(PostCheck.Kind.values))
        self.assertTrue(all_passed(checks))

    def test_run_checks_records_failure(self):
        BrandProfile.objects.create(name="Матемация", competitors=["Конкурент"])
        channel = Channel.objects.create(platform="telegram", title="Канал", external_id="@test")
        rubric = Rubric.objects.create(
            slug="tip", title="Совет", audience="both", source_kind=Rubric.SourceKind.LESSON_TIP
        )
        post = Post.objects.create(
            channel=channel,
            rubric=rubric,
            text="Конкурент обещает 99 баллов",
            scheduled_for=timezone.now(),
        )
        checks = run_checks(post, SourceMaterial(facts={}, reference_text="", source_ref="test"))
        self.assertFalse(all_passed(checks))
        self.assertTrue(post.checks.filter(kind=PostCheck.Kind.COMPETITOR, passed=False).exists())
        self.assertTrue(post.checks.filter(kind=PostCheck.Kind.NUMBER_WHITELIST, passed=False).exists())
