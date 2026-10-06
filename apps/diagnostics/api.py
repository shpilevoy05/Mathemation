from django.shortcuts import get_object_or_404
from rest_framework import views
from rest_framework.response import Response

from apps.accounts.api import get_student
from apps.content.api import AssignmentSerializer
from apps.practice.models import Attempt
from apps.practice.services import submit_attempt

from .models import DiagnosticResult, DiagnosticTest
from .services import complete_diagnostic, start_diagnostic


class DiagnosticListView(views.APIView):
    def get(self, request):
        return Response([
            {"id": t.id, "title": t.title, "assignments_count": t.assignments.count()}
            for t in DiagnosticTest.objects.filter(is_active=True)
        ])


class StartDiagnosticView(views.APIView):
    def post(self, request, test_id):
        student = get_student(request)
        test = get_object_or_404(DiagnosticTest, pk=test_id, is_active=True)
        result = start_diagnostic(student, test)
        return Response({
            "result_id": result.id,
            "assignments": AssignmentSerializer(test.assignments.all(), many=True).data,
        }, status=201)


class SubmitDiagnosticView(views.APIView):
    """POST answers: {"answers": {"<assignment_id>": "ответ", ...}}"""

    def post(self, request, result_id):
        student = get_student(request)
        result = get_object_or_404(
            DiagnosticResult, pk=result_id, student=student,
            status=DiagnosticResult.Status.IN_PROGRESS,
        )
        answers = request.data.get("answers", {})
        for assignment in result.test.assignments.all():
            # Работа сдаётся целиком: переспросить про нечитаемую запись
            # некого, поэтому она засчитывается как неверный ответ.
            submit_attempt(
                student, assignment, str(answers.get(str(assignment.id), "")),
                context=Attempt.Context.DIAGNOSTIC, diagnostic_result=result,
                strict=False,
            )
        complete_diagnostic(result)
        return Response({
            "primary_score": result.primary_score,
            "estimated_score": result.estimated_score,
            "status": result.status,
        })
