"""Версионирование заданий: правка не переписывает историю попыток."""
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.knowledge.tests import make_node, make_student
from apps.practice.models import Attempt
from apps.practice.services import submit_attempt
from apps.practice.tests import make_assignment

from .services import current_version, publish_assignment_version


class AssignmentVersionTests(TestCase):
    def setUp(self):
        self.student = make_student("version-student")
        self.node = make_node("version-node")
        self.assignment = make_assignment(self.node, answer="42")

    def test_first_version_is_created_lazily(self):
        version = current_version(self.assignment)
        self.assertEqual(version.number, 1)
        self.assertEqual(version.statement, self.assignment.statement)
        self.assertEqual(current_version(self.assignment).pk, version.pk)

    def test_new_version_updates_assignment_and_keeps_history(self):
        first = current_version(self.assignment)
        second = publish_assignment_version(
            self.assignment, statement="Новое условие", change_note="Опечатка"
        )
        self.assignment.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual(second.number, 2)
        self.assertEqual(self.assignment.statement, "Новое условие")
        self.assertNotEqual(first.statement, second.statement)
        self.assertEqual(self.assignment.versions.count(), 2)

    def test_version_without_changes_is_rejected(self):
        current_version(self.assignment)
        with self.assertRaises(ValidationError):
            publish_assignment_version(self.assignment, statement=self.assignment.statement)

    def test_attempt_keeps_the_version_the_student_saw(self):
        submit_attempt(self.student, self.assignment, "42", Attempt.Context.LESSON)
        publish_assignment_version(self.assignment, statement="Условие 2", correct_answer="7")
        submit_attempt(self.student, self.assignment, "7", Attempt.Context.LESSON)

        attempts = list(Attempt.objects.order_by("id"))
        self.assertEqual(attempts[0].assignment_version.number, 1)
        self.assertEqual(attempts[1].assignment_version.number, 2)

    def test_answer_change_affects_only_new_attempts(self):
        submit_attempt(self.student, self.assignment, "42", Attempt.Context.LESSON)
        publish_assignment_version(self.assignment, correct_answer="7")
        submit_attempt(self.student, self.assignment, "42", Attempt.Context.LESSON)
        attempts = list(Attempt.objects.order_by("id"))
        self.assertTrue(attempts[0].is_correct)
        self.assertFalse(attempts[1].is_correct)

    def test_version_in_use_cannot_be_deleted(self):
        submit_attempt(self.student, self.assignment, "42", Attempt.Context.LESSON)
        version = Attempt.objects.get().assignment_version
        with self.assertRaises(Exception):
            version.delete()


class HomeworkTests(TestCase):
    def setUp(self):
        from apps.content.models import Homework
        from apps.content.services import assign_homework

        self.student = make_student("hw-student")
        self.other = make_student("hw-other")
        self.node = make_node("hw-node")
        self.first = make_assignment(self.node, answer="1")
        self.second = make_assignment(self.node, answer="2")
        self.homework = Homework.objects.create(
            title="Домашка 1", status=Homework.Status.PUBLISHED
        )
        self.homework.tasks.create(assignment=self.first, order=0)
        self.homework.tasks.create(assignment=self.second, order=1)
        self.assign = assign_homework

    def test_draft_homework_cannot_be_assigned(self):
        from apps.content.models import Homework

        draft = Homework.objects.create(title="Черновик")
        draft.tasks.create(assignment=self.first)
        with self.assertRaises(ValidationError):
            self.assign(draft, [self.student])

    def test_assignment_is_idempotent(self):
        self.assign(self.homework, [self.student, self.other])
        self.assign(self.homework, [self.student])
        self.assertEqual(self.homework.submissions.count(), 2)

    def test_completion_closes_submission_by_itself(self):
        from apps.content.models import HomeworkSubmission
        from apps.content.services import homework_progress

        submission = self.assign(self.homework, [self.student])[0]
        submit_attempt(self.student, self.first, "1", Attempt.Context.LESSON)
        submission.refresh_from_db()
        self.assertEqual(submission.status, HomeworkSubmission.Status.ASSIGNED)
        self.assertEqual(homework_progress(submission)["solved"], 1)

        submit_attempt(self.student, self.second, "2", Attempt.Context.LESSON)
        submission.refresh_from_db()
        self.assertEqual(submission.status, HomeworkSubmission.Status.CHECKED)
        self.assertTrue(homework_progress(submission)["is_complete"])

    def test_overdue_only_for_unsubmitted(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.content.services import is_overdue, submit_homework

        self.homework.due_at = timezone.now() - timedelta(hours=1)
        self.homework.save(update_fields=["due_at"])
        submission = self.assign(self.homework, [self.student])[0]
        self.assertTrue(is_overdue(submission))
        submit_homework(submission)
        self.assertFalse(is_overdue(submission))

    def test_group_assignment_skips_deactivated_students(self):
        from apps.accounts.models import StudentGroup
        from apps.accounts.services import deactivate_student
        from apps.content.services import assign_homework_to_group

        group = StudentGroup.objects.create(title="Поток")
        group.students.add(self.student, self.other)
        deactivate_student(self.other)
        submissions = assign_homework_to_group(self.homework, group)
        self.assertEqual([s.student for s in submissions], [self.student])

    def test_student_sees_only_own_homework(self):
        self.assign(self.homework, [self.other])
        self.client.force_login(self.student.user)
        self.assertEqual(self.client.get("/api/homework/").json(), [])


class DailyChallengeTests(TestCase):
    def setUp(self):
        from django.utils import timezone

        from apps.content.models import DailyChallenge

        self.student = make_student("daily-student")
        self.node = make_node("daily-node")
        self.assignment = make_assignment(self.node, answer="7")
        self.challenge = DailyChallenge.objects.create(
            date=timezone.localdate(), assignment=self.assignment, reward_xp=15
        )

    def test_state_flips_after_correct_attempt(self):
        from apps.content.services import challenge_state

        self.assertFalse(challenge_state(self.student)["solved"])
        submit_attempt(self.student, self.assignment, "7", Attempt.Context.LESSON)
        self.assertTrue(challenge_state(self.student)["solved"])

    def test_wrong_answer_does_not_close_challenge(self):
        from apps.content.services import challenge_state

        submit_attempt(self.student, self.assignment, "0", Attempt.Context.LESSON)
        self.assertFalse(challenge_state(self.student)["solved"])

    def test_api_reports_reward(self):
        self.client.force_login(self.student.user)
        payload = self.client.get("/api/daily/").json()
        self.assertEqual(payload["reward_xp"], 15)
        self.assertFalse(payload["solved"])
