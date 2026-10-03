"""Кабинет ученика: домашки и задание дня."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import views
from rest_framework.response import Response

from apps.accounts.api import get_student

from .models import HomeworkSubmission
from .services import challenge_state, homework_progress, is_overdue, submit_homework


def _submission_payload(submission: HomeworkSubmission) -> dict:
    homework = submission.homework
    return {
        "id": submission.id,
        "homework_id": homework.id,
        "title": homework.title,
        "description": homework.description,
        "lesson_id": homework.lesson_id,
        "due_at": homework.due_at,
        "status": submission.status,
        "is_overdue": is_overdue(submission),
        "progress": homework_progress(submission),
        "tasks": [
            {
                "assignment_id": task.assignment_id,
                "title": task.assignment.title,
                "exam_part": task.assignment.exam_part,
            }
            for task in homework.tasks.select_related("assignment").all()
        ],
    }


class MyHomeworkView(views.APIView):
    """GET /api/homework/ — выданные домашки ученика с прогрессом."""

    def get(self, request):
        student = get_student(request)
        submissions = (
            HomeworkSubmission.objects.filter(student=student)
            .select_related("homework")
            .prefetch_related("homework__tasks__assignment")
        )
        return Response([_submission_payload(s) for s in submissions])


class SubmitHomeworkView(views.APIView):
    """POST /api/homework/<id>/submit/ — сдать домашку."""

    def post(self, request, submission_id: int):
        student = get_student(request)
        submission = get_object_or_404(
            HomeworkSubmission, pk=submission_id, student=student
        )
        return Response(_submission_payload(submit_homework(submission)))


class DailyChallengeView(views.APIView):
    """GET /api/daily/ — задание дня и его состояние."""

    def get(self, request):
        student = get_student(request)
        state = challenge_state(student)
        challenge = state.get("challenge")
        if challenge is None:
            return Response({"challenge": None})
        return Response({
            "challenge": {
                "date": challenge.date,
                "title": challenge.title or challenge.assignment.title,
                "description": challenge.description,
                "assignment_id": challenge.assignment_id,
                "statement": challenge.assignment.statement,
            },
            "solved": state["solved"],
            "reward_xp": state["reward_xp"],
        })
