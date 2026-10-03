"""Пошаговый вердикт эксперта: слабое место — шаг, а не задача целиком."""

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.accounts.models import User
from apps.content.models import Assignment, SolutionPath, SolutionStep
from apps.knowledge.models import KnowledgeNode, SkillMastery
from apps.knowledge.services import set_mastery
from apps.knowledge.tests import make_node, make_student
from apps.practice.models import MistakeBacklogItem

from .evidence import apply_step_marks, canonical_path, missing_required_steps
from .models import ExpertReviewRequest, SolutionStepMark
from .services import finish_review, submit_solution

# Заголовок JPEG: загрузка проверяет сигнатуру файла, а не расширение.
JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + bytes(64)


class PathFixture(TestCase):
    """Задача второй части с эталонным путём из трёх шагов."""

    def setUp(self):
        self.student = make_student("steps-student")
        self.expert = User.objects.create_user("steps-expert", role=User.Role.EXPERT)
        self.equation_node = make_node("equation-skill")
        self.constraints_node = make_node(
            "constraints-skill", cluster=self.equation_node.cluster
        )
        self.selection_node = make_node(
            "selection-skill", cluster=self.equation_node.cluster
        )
        self.assignment = Assignment.objects.create(
            title="Задание 13", statement="Решите уравнение",
            exam_part=Assignment.Part.PART2, max_score=2,
        )
        self.path = SolutionPath.objects.create(
            assignment=self.assignment, code="path-13", title="Через окружность",
            selection_method="Числовая окружность",
        )
        self.solve = SolutionStep.objects.create(
            path=self.path, order=1, stage=SolutionStep.Stage.EQUATION,
            node=self.equation_node, role=SolutionStep.Role.PRIMARY,
            signal=SolutionStep.Signal.STRONG, description="Решить простейшее уравнение",
        )
        self.constraints = SolutionStep.objects.create(
            path=self.path, order=2, stage=SolutionStep.Stage.CONSTRAINTS,
            node=self.constraints_node, role=SolutionStep.Role.SUPPORTING,
            signal=SolutionStep.Signal.WEAK, description="Выписать ограничения",
        )
        self.selection = SolutionStep.objects.create(
            path=self.path, order=3, stage=SolutionStep.Stage.SELECTION,
            node=self.selection_node, role=SolutionStep.Role.PRIMARY,
            signal=SolutionStep.Signal.STRONG, description="Отобрать корни на дуге",
        )
        self.review = submit_solution(
            self.student, self.assignment,
            SimpleUploadedFile("steps-solution.jpg", JPEG, content_type="image/jpeg"),
        )

    def mastery(self, node) -> float:
        record = SkillMastery.objects.filter(student=self.student, node=node).first()
        return float(record.mastery) if record else 0.0

    def mark(self, **outcomes) -> list[dict]:
        by_step = {
            "solve": self.solve,
            "constraints": self.constraints,
            "selection": self.selection,
        }
        return [
            {"step_id": by_step[name].id, "outcome": outcome}
            for name, outcome in outcomes.items()
        ]


class StepModelTests(PathFixture):
    def test_step_cannot_point_at_a_folder(self):
        folder = make_node(
            "folder-skill", cluster=self.equation_node.cluster,
            node_type=KnowledgeNode.NodeType.GROUP,
        )
        step = SolutionStep(
            path=self.path, order=9, node=folder, description="Шаг по папке"
        )

        with self.assertRaises(ValidationError):
            step.full_clean()

    def test_canonical_path_is_preferred(self):
        SolutionPath.objects.create(
            assignment=self.assignment, code="path-13-alt", title="Через неравенства",
            path_type=SolutionPath.PathType.ALTERNATIVE,
        )

        # Альтернативный путь — не ошибка, но учим мы каноническому.
        self.assertEqual(canonical_path(self.assignment), self.path)

    def test_inactive_path_is_not_used(self):
        self.path.is_active = False
        self.path.save(update_fields=["is_active"])

        self.assertIsNone(canonical_path(self.assignment))


class EvidenceTests(PathFixture):
    def test_only_the_failed_step_loses_mastery(self):
        for node in (self.equation_node, self.constraints_node, self.selection_node):
            set_mastery(self.student, node, 60)

        finish_review(
            self.review, self.expert, {"К1": 1, "К2": 0},
            step_marks=self.mark(solve="done", constraints="done", selection="wrong"),
        )

        # Верно выполненные шаги растут, ошибочный падает — а раньше один
        # вердикт двигал все темы задачи одинаково.
        self.assertGreater(self.mastery(self.equation_node), 60)
        self.assertGreater(self.mastery(self.constraints_node), 60)
        self.assertLess(self.mastery(self.selection_node), 60)

    def test_step_not_attempted_changes_nothing(self):
        set_mastery(self.student, self.constraints_node, 55)

        finish_review(
            self.review, self.expert, {"К1": 1, "К2": 0},
            step_marks=self.mark(solve="done", constraints="missing", selection="wrong"),
        )

        # Нет наблюдаемого действия — нет обновления освоения.
        self.assertEqual(self.mastery(self.constraints_node), 55)

    def test_strong_signal_moves_more_than_weak(self):
        set_mastery(self.student, self.equation_node, 50)
        set_mastery(self.student, self.constraints_node, 50)

        finish_review(
            self.review, self.expert, {"К1": 1, "К2": 1},
            step_marks=self.mark(solve="done", constraints="done"),
        )

        strong_gain = self.mastery(self.equation_node) - 50
        weak_gain = self.mastery(self.constraints_node) - 50
        self.assertGreater(strong_gain, weak_gain)

    def test_failed_step_lands_on_the_backlog_with_its_error_type(self):
        finish_review(
            self.review, self.expert, {"К1": 1, "К2": 0},
            step_marks=self.mark(solve="done", selection="wrong"),
        )

        item = MistakeBacklogItem.objects.get(
            student=self.student, node=self.selection_node
        )
        self.assertEqual(item.error_type, MistakeBacklogItem.ErrorType.WRONG_METHOD)
        self.assertFalse(
            MistakeBacklogItem.objects.filter(
                student=self.student, node=self.equation_node
            ).exists()
        )

    def test_marks_are_stored_for_the_record(self):
        finish_review(
            self.review, self.expert, {"К1": 1, "К2": 0},
            step_marks=self.mark(solve="done", constraints="missing", selection="wrong"),
        )

        self.assertEqual(self.review.step_marks.count(), 3)
        summary = apply_step_marks(self.review)
        self.assertEqual(summary["done"], [self.equation_node.id])
        self.assertEqual(summary["wrong"], [self.selection_node.id])
        self.assertEqual(summary["missing"], [self.constraints_node.id])

    def test_student_sees_which_steps_did_not_add_up(self):
        finish_review(
            self.review, self.expert, {"К1": 1, "К2": 0},
            step_marks=self.mark(solve="done", constraints="missing", selection="wrong"),
        )

        missing = missing_required_steps(self.review)

        self.assertEqual(
            [step.description for step in missing],
            ["Выписать ограничения", "Отобрать корни на дуге"],
        )

    def test_verdict_without_marks_keeps_the_old_behaviour(self):
        self.assignment.skill_tags.create(node=self.equation_node, weight=1.0)
        set_mastery(self.student, self.equation_node, 50)

        finish_review(self.review, self.expert, {"К1": 0, "К2": 0})

        # Разметки шагов может ещё не быть: тогда работает разметка задачи.
        self.assertLess(self.mastery(self.equation_node), 50)


class FinishApiTests(PathFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.expert)

    def finish(self, payload):
        return self.client.post(
            f"/api/expert-reviews/{self.review.id}/finish/",
            payload, content_type="application/json",
        )

    def test_marks_travel_through_the_api(self):
        response = self.finish({
            "score_by_criteria": {"К1": 1, "К2": 0},
            "step_marks": self.mark(solve="done", selection="wrong"),
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            SolutionStepMark.objects.filter(review=self.review).count(), 2
        )
        self.assertEqual(
            response.json()["missing_steps"][0]["description"], "Отобрать корни на дуге"
        )

    def test_step_from_another_task_is_refused(self):
        other = Assignment.objects.create(
            title="Другая задача", statement="",
            exam_part=Assignment.Part.PART2, max_score=2,
        )
        other_path = SolutionPath.objects.create(
            assignment=other, code="path-other", title="Другой путь"
        )
        other_step = SolutionStep.objects.create(
            path=other_path, order=1, node=self.equation_node, description="Чужой шаг"
        )

        response = self.finish({
            "score_by_criteria": {"К1": 1, "К2": 0},
            "step_marks": [{"step_id": other_step.id, "outcome": "done"}],
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(SolutionStepMark.objects.count(), 0)

    def test_the_same_step_cannot_be_marked_twice(self):
        response = self.finish({
            "score_by_criteria": {"К1": 1, "К2": 0},
            "step_marks": [
                {"step_id": self.solve.id, "outcome": "done"},
                {"step_id": self.solve.id, "outcome": "wrong"},
            ],
        })

        self.assertEqual(response.status_code, 400)

    def test_review_stays_open_when_the_payload_is_rejected(self):
        self.finish({
            "score_by_criteria": {"К1": 1},
            "step_marks": [{"step_id": 0, "outcome": "done"}],
        })

        self.review.refresh_from_db()
        self.assertEqual(self.review.status, ExpertReviewRequest.Status.SUBMITTED)
