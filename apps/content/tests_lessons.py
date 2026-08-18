"""Занятие как три этапа: материал, задачи, отработка."""
from django.test import TestCase
from django.urls import reverse

from apps.knowledge.tests import make_node, make_student
from apps.practice.models import Attempt
from apps.practice.services import submit_attempt
from apps.practice.tests import make_assignment

from .lessons import lesson_stages, lesson_summary_text, mark_material_viewed
from .models import Lesson, TheoryBlock


class LessonStageTests(TestCase):
    def setUp(self):
        self.student = make_student("stage-student")
        self.node = make_node("stage-node")
        self.lesson = Lesson.objects.create(node=self.node, title="Урок")
        TheoryBlock.objects.create(
            lesson=self.lesson, title="Коротко о главном", body="Вынеси общий множитель."
        )
        self.assignment = make_assignment(self.node, answer="42")

    def stages(self) -> dict:
        return {stage["key"]: stage for stage in lesson_stages(self.student, self.node)}

    def test_fresh_lesson_starts_on_the_material_stage(self):
        stages = self.stages()

        self.assertTrue(stages["material"]["is_current"])
        self.assertFalse(stages["material"]["is_done"])
        self.assertFalse(stages["tasks"]["is_done"])

    def test_material_is_closed_by_the_student_and_only_once(self):
        first = mark_material_viewed(self.student, self.node)
        second = mark_material_viewed(self.student, self.node)

        self.assertEqual(first.material_viewed_at, second.material_viewed_at)
        self.assertTrue(self.stages()["material"]["is_done"])
        self.assertTrue(self.stages()["tasks"]["is_current"])

    def test_tasks_stage_closes_when_every_task_is_solved(self):
        mark_material_viewed(self.student, self.node)
        submit_attempt(self.student, self.assignment, "42", Attempt.Context.LESSON)

        stages = self.stages()

        self.assertTrue(stages["tasks"]["is_done"])
        self.assertEqual(stages["tasks"]["caption"], "Решено 1 из 1")

    def test_wrong_answer_puts_the_mistake_into_the_review_stage(self):
        mark_material_viewed(self.student, self.node)
        submit_attempt(self.student, self.assignment, "неверно", Attempt.Context.LESSON)

        review = self.stages()["review"]

        # Первый повтор назначается на завтра, поэтому на сегодня этап пуст,
        # но ошибка уже числится за темой и вернётся по расписанию.
        self.assertEqual(review["open_count"], 1)
        self.assertEqual(review["caption"], "Повторов на сегодня нет")

    def test_review_stage_is_open_while_a_repeat_is_due_today(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.practice.models import ReviewSchedule

        mark_material_viewed(self.student, self.node)
        submit_attempt(self.student, self.assignment, "неверно", Attempt.Context.LESSON)
        ReviewSchedule.objects.filter(backlog_item__node=self.node).update(
            due_date=timezone.localdate() - timedelta(days=1)
        )

        stages = self.stages()

        self.assertFalse(stages["review"]["is_done"])
        # Ошибка планирует всю лестницу повторов 1/3/7/30, и после сдвига дат
        # на сегодня приходят все четыре круга сразу.
        self.assertEqual(stages["review"]["caption"], "Повторов на сегодня: 4")
        # Текущим остаётся более ранний незакрытый этап: задача ещё не решена.
        self.assertTrue(stages["tasks"]["is_current"])

    def test_one_stage_is_current_at_a_time(self):
        current = [stage for stage in lesson_stages(self.student, self.node) if stage["is_current"]]

        self.assertEqual(len(current), 1)


class LessonSummaryTests(TestCase):
    def setUp(self):
        self.student = make_student("summary-student")
        self.node = make_node("summary-node")
        lesson = Lesson.objects.create(node=self.node, title="Урок")
        TheoryBlock.objects.create(lesson=lesson, title="Приём", body="Раздели случаи.")
        make_assignment(self.node, answer="7")
        self.client.force_login(self.student.user)

    def test_summary_downloads_as_a_file(self):
        response = self.client.get(reverse("lesson-summary", args=[self.node.id]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn("Приём", response.content.decode())

    def test_summary_contains_theory_and_tasks(self):
        text = lesson_summary_text(self.node)

        self.assertIn("## Приём", text)
        self.assertIn("## Задачи занятия", text)

    def test_summary_is_closed_for_non_students(self):
        from apps.accounts.models import User

        self.client.force_login(User.objects.create_user("nobody"))

        response = self.client.get(reverse("lesson-summary", args=[self.node.id]))

        self.assertEqual(response.status_code, 404)


class LessonStageApiTests(TestCase):
    def setUp(self):
        self.student = make_student("api-stage-student")
        self.node = make_node("api-stage-node")
        Lesson.objects.create(node=self.node, title="Урок")
        make_assignment(self.node, answer="1")
        self.client.force_login(self.student.user)
        self.url = f"/api/lessons/{self.node.id}/stages/"

    def test_get_returns_three_stages(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [stage["key"] for stage in response.json()["stages"]],
            ["material", "tasks", "review"],
        )

    def test_post_marks_the_material_as_seen(self):
        response = self.client.post(self.url, {}, "application/json")

        self.assertTrue(response.json()["stages"][0]["is_done"])

    def test_attempt_response_reports_rewards(self):
        assignment = make_assignment(self.node, answer="55")

        response = self.client.post(
            f"/api/assignments/{assignment.id}/attempt/",
            {"answer": "55", "context": "lesson"}, "application/json",
        )

        rewards = response.json()["rewards"]
        self.assertGreater(rewards["xp"], 0)
        self.assertTrue(rewards["mastery"])
        self.assertEqual(rewards["mastery"][0]["node_id"], self.node.id)
        self.assertGreater(rewards["mastery"][0]["to"], rewards["mastery"][0]["from"])
