from rest_framework import views
from rest_framework.response import Response

from apps.accounts.api import get_student
from apps.accounts.models import ParentProfile, StudentProfile

from .models import ParentReport, ProgressSnapshot
from .services import build_parent_report


class ProgressView(views.APIView):
    """Стартовый балл, текущий прогноз, целевой балл, слабые темы."""

    def get(self, request):
        student = get_student(request)
        snapshot = ProgressSnapshot.objects.filter(student=student).first()
        if snapshot is None:
            return Response({"detail": "Нет данных — пройдите диагностику."}, status=404)
        return Response({
            "start_score": snapshot.start_score,
            "predicted_score": snapshot.predicted_score,
            "target_score": snapshot.target_score,
            "average_mastery": snapshot.average_mastery,
            "weak_topics": snapshot.weak_topics,
            "created_at": snapshot.created_at,
        })


class ParentReportView(views.APIView):
    """Weekly pulse для родителя по его ребёнку."""

    def get(self, request):
        parent = getattr(request.user, "parent_profile", None)
        if parent is None:
            return Response({"detail": "Нет профиля родителя."}, status=403)
        student_id = request.query_params.get("student")
        children = parent.children.all()
        student = children.filter(pk=student_id).first() if student_id else children.first()
        if student is None:
            return Response({"detail": "Ученик не найден."}, status=404)
        report = ParentReport.objects.filter(student=student).first()
        if report is None:
            report = build_parent_report(student)
        return Response({
            "student": student.user.username,
            "week_start": report.week_start,
            **report.payload,
        })
