"""Версионирование заданий, домашки и задание дня."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.practice.models import Attempt

from .models import AssignmentVersion, DailyChallenge, Homework, HomeworkSubmission


def current_version(assignment) -> AssignmentVersion:
    """Текущая версия задания; первая создаётся лениво из его полей."""
    version = assignment.versions.order_by("-number").first()
    if version is not None:
        return version
    return AssignmentVersion.objects.create(
        assignment=assignment, number=1,
        statement=assignment.statement, correct_answer=assignment.correct_answer,
        reference_solution=assignment.reference_solution,
        max_score=assignment.max_score, difficulty=assignment.difficulty,
        change_note="Первая версия",
    )


def publish_assignment_version(assignment, *, change_note: str = "",
                               created_by=None, **changes) -> AssignmentVersion:
    """Изменить задание новой версией, а не правкой на месте.

    Поля самого задания тоже обновляются: они хранят текущую версию, чтобы
    списки, дорожка и проверка ответа не делали лишний джойн. История живёт
    в версиях.
    """
    previous = current_version(assignment)
    fields = {
        "statement": changes.get("statement", previous.statement),
        "correct_answer": changes.get("correct_answer", previous.correct_answer),
        "reference_solution": changes.get("reference_solution", previous.reference_solution),
        "max_score": changes.get("max_score", previous.max_score),
        "difficulty": changes.get("difficulty", previous.difficulty),
    }
    if all(getattr(previous, name) == value for name, value in fields.items()):
        raise ValidationError("Новая версия не отличается от текущей.")

    version = AssignmentVersion.objects.create(
        assignment=assignment, number=previous.number + 1,
        change_note=change_note, created_by=created_by, **fields,
    )
    for name, value in fields.items():
        setattr(assignment, name, value)
    assignment.save(update_fields=list(fields))
    return version


def assign_homework(homework: Homework, students) -> list[HomeworkSubmission]:
    """Выдать домашку списку учеников. Повторная выдача не плодит записи.

    Черновик выдавать нельзя: ученик увидел бы задание, которое методист ещё
    собирает.
    """
    if not homework.is_published:
        raise ValidationError("Домашку можно выдать только после публикации.")
    if not homework.tasks.exists():
        raise ValidationError("В домашке нет ни одного задания.")

    submissions = []
    for student in students:
        submission, _ = HomeworkSubmission.objects.get_or_create(
            homework=homework, student=student
        )
        submissions.append(submission)
    return submissions


def assign_homework_to_group(homework: Homework, group) -> list[HomeworkSubmission]:
    """Выдать домашку группе — только активным ученикам."""
    return assign_homework(homework, list(group.students.filter(user__is_active=True)))


def homework_progress(submission: HomeworkSubmission) -> dict:
    """Прогресс: сколько заданий решено верно.

    Считается по обычным попыткам, поэтому задача, решённая в другом месте,
    засчитывается — домашка не заставляет решать одно и то же дважды.
    """
    assignment_ids = list(submission.homework.tasks.values_list("assignment_id", flat=True))
    solved = (
        Attempt.objects.filter(
            student=submission.student, assignment_id__in=assignment_ids, is_correct=True
        )
        .values("assignment_id")
        .distinct()
        .count()
    )
    attempted = (
        Attempt.objects.filter(
            student=submission.student, assignment_id__in=assignment_ids
        )
        .values("assignment_id")
        .distinct()
        .count()
    )
    total = len(assignment_ids)
    return {
        "total": total,
        "solved": solved,
        "attempted": attempted,
        "is_complete": total > 0 and solved == total,
    }


def submit_homework(submission: HomeworkSubmission) -> HomeworkSubmission:
    """Ученик сдал домашку. Идемпотентно: повторная сдача не меняет время."""
    if submission.status in (
        HomeworkSubmission.Status.SUBMITTED, HomeworkSubmission.Status.CHECKED
    ):
        return submission
    submission.status = HomeworkSubmission.Status.SUBMITTED
    submission.submitted_at = timezone.now()
    submission.save(update_fields=["status", "submitted_at"])
    return submission


def is_overdue(submission: HomeworkSubmission, now=None) -> bool:
    due = submission.homework.due_at
    if due is None or submission.status in (
        HomeworkSubmission.Status.SUBMITTED, HomeworkSubmission.Status.CHECKED
    ):
        return False
    return (now or timezone.now()) > due


def challenge_for(date=None) -> DailyChallenge | None:
    """Активное задание дня на дату (по умолчанию — сегодня)."""
    return DailyChallenge.objects.filter(
        date=date or timezone.localdate(), is_active=True
    ).first()


def challenge_state(student, date=None) -> dict:
    """Состояние задания дня: решено или нет.

    Засчитывается верная попытка того же дня — иначе вчерашнее решение
    закрывало бы сегодняшнее задание.
    """
    challenge = challenge_for(date)
    if challenge is None:
        return {"challenge": None}
    solved = Attempt.objects.filter(
        student=student, assignment=challenge.assignment,
        is_correct=True, created_at__date=challenge.date,
    ).exists()
    return {"challenge": challenge, "solved": solved, "reward_xp": challenge.reward_xp}


def close_completed_homework(attempt) -> None:
    """После верной попытки закрыть домашки, где решены все задачи.

    Вызывается из обработки попытки и обязана быть идемпотентной.
    """
    open_submissions = (
        HomeworkSubmission.objects.filter(
            student=attempt.student, homework__tasks__assignment_id=attempt.assignment_id
        )
        .exclude(status=HomeworkSubmission.Status.CHECKED)
        .distinct()
    )
    for submission in open_submissions:
        if not homework_progress(submission)["is_complete"]:
            continue
        submission.status = HomeworkSubmission.Status.CHECKED
        submission.submitted_at = submission.submitted_at or timezone.now()
        submission.checked_at = timezone.now()
        submission.save(update_fields=["status", "submitted_at", "checked_at"])
