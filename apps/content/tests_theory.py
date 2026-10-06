"""Вопросы по теории: формат ответа, сравнение и загрузка банка."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.knowledge.models import TopicCluster

from .models import TheoryQuestion
from .theory_bank import BANK, load_theory_bank


def make_question(**fields) -> TheoryQuestion:
    cluster, _ = TopicCluster.objects.get_or_create(title="Тема", defaults={"order": 0})
    defaults = {
        "cluster": cluster,
        "prompt": "Как называется график квадратичной функции?",
        "correct_answer": "парабола",
        "difficulty": 2,
    }
    return TheoryQuestion(**{**defaults, **fields})


class AnswerFormatTests(TestCase):
    """Под таймером ответ не должен пропадать из-за записи, а не из-за незнания."""

    def test_case_and_yo_do_not_matter(self):
        question = make_question(correct_answer="чётная")

        self.assertTrue(question.check_answer("Четная"))
        self.assertTrue(question.check_answer("  ЧЁТНАЯ "))

    def test_synonyms_are_accepted(self):
        question = make_question(correct_answer="нуль", accepted_answers=["ноль", "корень"])

        self.assertTrue(question.check_answer("ноль"))
        self.assertTrue(question.check_answer("Корень"))
        self.assertFalse(question.check_answer("минимум"))

    def test_number_reads_a_decimal_comma(self):
        question = make_question(
            answer_format=TheoryQuestion.Format.NUMBER, correct_answer="0,375"
        )

        self.assertTrue(question.check_answer("0.375"))
        self.assertTrue(question.check_answer("0,375"))
        self.assertFalse(question.check_answer("0,38"))

    def test_number_ignores_spaces_inside(self):
        question = make_question(
            answer_format=TheoryQuestion.Format.NUMBER, correct_answer="1000"
        )

        self.assertTrue(question.check_answer("1 000"))

    def test_empty_answer_is_wrong_not_an_error(self):
        question = make_question()

        self.assertFalse(question.check_answer(""))
        self.assertFalse(question.check_answer("   "))

    def test_multiword_answer_is_refused_at_the_source(self):
        question = make_question(correct_answer="центр тяжести")

        # Не ученик виноват, а вопрос: два слова нельзя сравнить однозначно.
        with self.assertRaises(ValidationError):
            question.full_clean(exclude=["node"])

    def test_number_answer_must_be_a_number(self):
        question = make_question(
            answer_format=TheoryQuestion.Format.NUMBER, correct_answer="много"
        )

        with self.assertRaises(ValidationError):
            question.full_clean(exclude=["node"])


class QuizOptionTests(TestCase):
    def test_four_options_are_required(self):
        question = make_question(options=["парабола", "прямая"])

        with self.assertRaises(ValidationError):
            question.full_clean(exclude=["node"])

    def test_options_must_contain_the_right_answer(self):
        question = make_question(options=["прямая", "гипербола", "синусоида", "круг"])

        with self.assertRaises(ValidationError):
            question.full_clean(exclude=["node"])

    def test_correct_option_is_found_by_meaning(self):
        question = make_question(
            options=["Парабола", "гипербола", "прямая", "синусоида"]
        )

        self.assertEqual(question.correct_option(), 0)

    def test_price_follows_difficulty(self):
        self.assertEqual(make_question(difficulty=1).price, 100)
        self.assertEqual(make_question(difficulty=5).price, 500)


class BankTests(TestCase):
    def setUp(self):
        for order, title in enumerate(BANK):
            TopicCluster.objects.get_or_create(title=title, defaults={"order": order})

    def test_bank_loads_and_is_idempotent(self):
        first = load_theory_bank()
        count = TheoryQuestion.objects.count()

        second = load_theory_bank()

        self.assertGreater(first["created"], 0)
        self.assertEqual(second["created"], 0)
        self.assertEqual(TheoryQuestion.objects.count(), count)

    def test_every_bank_question_passes_its_own_rules(self):
        load_theory_bank()

        for question in TheoryQuestion.objects.all():
            question.full_clean(exclude=["node"])

    def test_bank_covers_five_prices_in_every_topic(self):
        load_theory_bank()

        for title in BANK:
            levels = set(
                TheoryQuestion.objects.filter(cluster__title=title)
                .values_list("difficulty", flat=True)
            )
            # Доска «своей игры» — пять цен: тема без полного набора оставит
            # на доске дыры.
            self.assertEqual(levels, {1, 2, 3, 4, 5}, title)

    def test_missing_topic_is_skipped_not_broken(self):
        TopicCluster.objects.all().delete()

        report = load_theory_bank()

        self.assertEqual(report["created"], 0)
        self.assertGreater(report["skipped"], 0)
