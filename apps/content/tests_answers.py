"""Проверка ответа по смыслу: множества и семейства корней.

Задание 13 — это ответ-множество, а не число, поэтому здесь проверяется не
«совпала ли строка», а «то же ли это множество точек». Часть случаев взята из
корпуса методистов: там и табличные значения, и арксинусы, и запись через ±.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.knowledge.tests import make_node, make_student
from apps.practice.services import AnswerNotUnderstood, submit_attempt
from apps.practice.models import Attempt, MistakeBacklogItem

from .answers import AnswerParseError, Family, parse_answer, same_families
from .models import Assignment


def make_task(spec: dict, answer_type=Assignment.AnswerType.ROOT_FAMILIES) -> Assignment:
    return Assignment.objects.create(
        title="Задача 13", statement="Решите уравнение",
        answer_type=answer_type, answer_spec=spec, max_score=2,
    )


class ParsingTests(TestCase):
    def parse(self, text: str):
        return parse_answer(text)

    def test_pi_symbol_and_implicit_multiplication(self):
        families, roots = self.parse("π/6 + 2πk")

        self.assertEqual(len(families), 1)
        self.assertFalse(roots)

    def test_parameter_letter_does_not_matter(self):
        first, _ = self.parse("π/6 + 2πk")
        second, _ = self.parse("π/6 + 2πn")

        self.assertTrue(same_families(first, second))

    def test_plus_minus_expands_into_two_series(self):
        families, _ = self.parse("±π/3 + 2πk")

        self.assertEqual(len(families), 2)

    def test_separators_are_semicolon_comma_and_newline(self):
        for text in ("π/6; 5π/6", "π/6, 5π/6", "π/6\n5π/6"):
            _, roots = self.parse(text)
            self.assertEqual(len(roots), 2, text)

    def test_decimal_comma_is_not_a_separator(self):
        _, roots = self.parse("1,5")

        self.assertEqual(len(roots), 1)

    def test_variable_prefix_is_ignored(self):
        families, _ = self.parse("x = π/4 + πk/2")

        self.assertEqual(len(families), 1)

    def test_negative_period_is_normalized(self):
        (family,), _ = self.parse("π/6 - 2πk")

        # k пробегает все целые: знак при параметре множество не меняет.
        self.assertTrue(family.period.is_positive)

    def test_unknown_letter_is_refused(self):
        with self.assertRaises(AnswerParseError):
            self.parse("y + 2πk")

    def test_quadratic_series_is_refused(self):
        with self.assertRaises(AnswerParseError):
            self.parse("πk*k")

    def test_two_parameters_in_one_series_are_refused(self):
        with self.assertRaises(AnswerParseError):
            self.parse("πk + πn")

    def test_code_like_input_never_reaches_the_parser(self):
        for attack in ("__import__('os')", "9**9**9", "eval(\"1\")", "a" * 500):
            with self.assertRaises(AnswerParseError, msg=attack):
                self.parse(attack)


class FamilyEquivalenceTests(TestCase):
    def same(self, first: str, second: str) -> bool:
        return same_families(parse_answer(first)[0], parse_answer(second)[0])

    def test_same_set_written_with_different_periods(self):
        # π/4+πk/2 и пара π/4+πk, 3π/4+πk описывают одни и те же точки.
        self.assertTrue(self.same("π/4 + πk/2", "π/4 + πk; 3π/4 + πk"))

    def test_shifted_base_by_a_whole_period(self):
        self.assertTrue(self.same("π/6 + 2πk", "13π/6 + 2πk"))

    def test_order_of_series_does_not_matter(self):
        self.assertTrue(self.same("π/6 + 2πk; 5π/6 + 2πk", "5π/6 + 2πn; π/6 + 2πn"))

    def test_missing_series_is_not_the_same_answer(self):
        self.assertFalse(self.same("π/6 + 2πk; 5π/6 + 2πk", "π/6 + 2πk"))

    def test_wrong_period_is_not_the_same_answer(self):
        self.assertFalse(self.same("π/6 + 2πk", "π/6 + πk"))

    def test_non_table_value_survives(self):
        self.assertTrue(
            self.same("arcsin(2/3) + 2πk", "arcsin(2/3) + 2πn")
        )


class CheckAnswerTests(TestCase):
    def test_families_accept_an_equivalent_form(self):
        task = make_task({"families": ["pi/4 + pi*k/2"]})

        self.assertIs(task.check_answer("π/4+πk; 3π/4+πk"), True)

    def test_root_set_ignores_order(self):
        task = make_task(
            {"roots": ["7*pi/6", "11*pi/6", "19*pi/6"]},
            answer_type=Assignment.AnswerType.ROOT_SET,
        )

        self.assertIs(task.check_answer("19π/6, 7π/6, 11π/6"), True)

    def test_root_set_needs_every_root(self):
        task = make_task(
            {"roots": ["7*pi/6", "11*pi/6"]},
            answer_type=Assignment.AnswerType.ROOT_SET,
        )

        self.assertIs(task.check_answer("7π/6"), False)

    def test_unreadable_answer_is_neither_right_nor_wrong(self):
        task = make_task({"families": ["pi/6 + 2*pi*k"]})

        self.assertIsNone(task.check_answer("π/6 + 2πk +"))

    def test_number_type_compares_by_value(self):
        task = Assignment.objects.create(
            title="Число", statement="", correct_answer="0.5",
            answer_type=Assignment.AnswerType.NUMBER,
        )

        self.assertIs(task.check_answer("1/2"), True)
        self.assertIs(task.check_answer("0,5"), True)
        self.assertIs(task.check_answer("2"), False)

    def test_text_type_keeps_the_old_behaviour(self):
        task = Assignment.objects.create(
            title="Строка", statement="", correct_answer="12"
        )

        self.assertIs(task.check_answer(" 12 "), True)
        self.assertIs(task.check_answer("13"), False)


class ReferenceAnswerValidationTests(TestCase):
    def test_broken_reference_answer_is_refused_on_save(self):
        task = make_task({"families": ["pi/6 + 2*pi*"]})

        with self.assertRaises(ValidationError):
            task.full_clean()

    def test_missing_reference_answer_is_refused(self):
        task = make_task({})

        with self.assertRaises(ValidationError):
            task.full_clean()

    def test_valid_reference_answer_passes(self):
        task = make_task({"families": ["pi/6 + 2*pi*k"]})

        task.full_clean()


class AttemptTests(TestCase):
    def setUp(self):
        self.student = make_student("answer-student")
        self.node = make_node("answer-node")
        self.task = make_task({"families": ["pi/6 + 2*pi*k"]})
        self.task.skill_tags.create(node=self.node, weight=1.0)

    def test_unreadable_answer_does_not_become_a_mistake(self):
        with self.assertRaises(AnswerNotUnderstood):
            submit_attempt(self.student, self.task, "π/6 + 2πk +", Attempt.Context.LESSON)

        self.assertFalse(Attempt.objects.filter(student=self.student).exists())
        self.assertFalse(
            MistakeBacklogItem.objects.filter(student=self.student).exists()
        )

    def test_equivalent_answer_is_accepted(self):
        attempt = submit_attempt(
            self.student, self.task, "13π/6 + 2πn", Attempt.Context.LESSON
        )

        self.assertTrue(attempt.is_correct)

    def test_exam_context_counts_unreadable_answer_as_wrong(self):
        # На пробнике переспросить некого: работа сдаётся целиком.
        attempt = submit_attempt(
            self.student, self.task, "π/6 + 2πk +", Attempt.Context.MOCK, strict=False
        )

        self.assertIs(attempt.is_correct, False)


class AttemptApiTests(TestCase):
    def setUp(self):
        self.student = make_student("api-answer-student")
        self.client.force_login(self.student.user)
        self.node = make_node("api-answer-node")
        self.task = make_task({"families": ["pi/6 + 2*pi*k"]})
        self.task.skill_tags.create(node=self.node, weight=1.0)

    def post(self, answer: str):
        return self.client.post(
            f"/api/assignments/{self.task.id}/attempt/",
            {"answer": answer}, content_type="application/json",
        )

    def test_unreadable_answer_returns_422_with_a_hint(self):
        response = self.post("π/6 + 2πk +")

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["code"], "answer_not_understood")
        self.assertIn("π/6", payload["detail"])

    def test_correct_answer_still_returns_201(self):
        response = self.post("π/6 + 2πn")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["is_correct"])


class CorpusAnswerTests(TestCase):
    """Ответы из корпуса методистов, записанные учеником по-своему."""

    CASES = [
        # Задача 1.1: фильтр по знаку, одна серия.
        ({"families": ["pi/3 + 2*pi*k"]}, "π/3+2πn", True),
        # Задача 3.1: две серии табличного синуса.
        ({"families": ["pi/6 + 2*pi*k", "5*pi/6 + 2*pi*k"]}, "π/6+2πk; 5π/6+2πk", True),
        # Задача 5.1: составной угол, период делится.
        ({"families": ["-pi/6 + pi*k/2"]}, "−π/6+πk/2", True),
        # Задача 8.1: нетабличное значение через арксинус.
        (
            {"families": ["arcsin(2/3) + 2*pi*k", "pi - arcsin(2/3) + 2*pi*k"]},
            "arcsin(2/3)+2πk; π−arcsin(2/3)+2πk",
            True,
        ),
        # Задача 13.1: ответ через ±.
        ({"families": ["pi/4 + pi*k/2", "-pi/4 + pi*k/2"]}, "±π/4+πk/2", True),
        # Потерянная серия — не тот же ответ.
        ({"families": ["pi/6 + 2*pi*k", "5*pi/6 + 2*pi*k"]}, "π/6+2πk", False),
    ]

    def test_corpus_answers(self):
        for spec, given, expected in self.CASES:
            with self.subTest(given=given):
                self.assertIs(make_task(spec).check_answer(given), expected)
