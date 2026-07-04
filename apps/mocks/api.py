from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import views
from rest_framework.response import Response

from apps.accounts.api import get_student
from apps.content.api import AssignmentSerializer
from apps.content.models import Assignment
from apps.practice.models import Attempt
from apps.practice.services import submit_attempt

from .models import MockExam, MockExamResult
from .services import complete_mock_part1


class MockListView(views.APIView):
    def get(self, request):
        return Response([
            {"id": m.id, "title": m.title, "duration_minutes": m.duration_minutes}
            for m in MockExam.objects.filter(is_active=True)
        ])


class StartMockView(views.APIView):
    def post(self, request, exam_id):
        student = get_student(request)
        exam = get_object_or_404(MockExam, pk=exam_id, is_active=True)
        result = MockExamResult.objects.create(student=student, exam=exam)
        return Response({
            "result_id": result.id,
            "duration_minutes": exam.duration_minutes,
            "deadline": result.deadline,
            "assignments": AssignmentSerializer(exam.assignments.all(), many=True).data,
        }, status=201)


class SubmitMockView(views.APIView):
    """POST {"answers": {"<assignment_id>": "ответ"}} — auto-checks part 1.

    Part-2 solutions go separately through /api/expert-reviews/.
    """

    def post(self, request, result_id):
        student = get_student(request)
        result = get_object_or_404(
            MockExamResult, pk=result_id, student=student,
            status=MockExamResult.Status.IN_PROGRESS,
        )
        if timezone.now() > result.deadline:
            # Время вышло — фиксируем как в реальном ЕГЭ, работу принимаем.
            result.time_expired = True
            result.save(update_fields=["time_expired"])
        answers = request.data.get("answers", {})
        for assignment in result.exam.assignments.filter(exam_part=Assignment.Part.PART1):
            submit_attempt(
                student, assignment, str(answers.get(str(assignment.id), "")),
                context=Attempt.Context.MOCK, mock_result=result,
            )
        complete_mock_part1(result)
        return Response({
            "primary_score": result.primary_score,
            "scaled_score": result.scaled_score,
            "status": result.status,
            "time_expired": result.time_expired,
        })
