from datetime import timedelta

from django.shortcuts import get_object_or_404
from rest_framework import views
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.api import get_student
from apps.content.models import Assignment

from .models import ExpertReviewRequest
from .services import submit_solution


def _payload(r: ExpertReviewRequest) -> dict:
    return {
        "id": r.id,
        "assignment_id": r.assignment_id,
        "status": r.status,
        "sla_hours": r.sla_hours,
        "total_score": r.total_score,
        "lost_points": r.lost_points,
        "score_by_criteria": r.score_by_criteria,
        "comment": r.comment,
        "error_tags": r.error_tags,
        "created_at": r.created_at,
        "sla_deadline": r.created_at + timedelta(hours=r.sla_hours),
        "reviewed_at": r.reviewed_at,
    }


class ExpertReviewListView(views.APIView):
    def get(self, request):
        student = get_student(request)
        return Response([
            _payload(r)
            for r in ExpertReviewRequest.objects.filter(student=student)
        ])


class SubmitSolutionView(views.APIView):
    """POST multipart: assignment=<id>, file=<решение (фото/PDF)>."""

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        student = get_student(request)
        assignment = get_object_or_404(
            Assignment, pk=request.data.get("assignment"), exam_part=Assignment.Part.PART2
        )
        solution = request.FILES.get("file")
        if solution is None:
            return Response({"detail": "Файл решения обязателен."}, status=400)
        mock_result = None
        if request.data.get("mock_result"):
            from apps.mocks.models import MockExamResult

            mock_result = get_object_or_404(
                MockExamResult, pk=request.data["mock_result"], student=student
            )
        review = submit_solution(student, assignment, solution, mock_result=mock_result)
        return Response(_payload(review), status=201)
