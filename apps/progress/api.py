from datetime import date

from rest_framework import views
from rest_framework.response import Response

from apps.accounts.api import get_student
from apps.accounts.models import ParentProfile, StudentProfile

from .models import ParentReport, ProgressSnapshot
from .services import (
    build_parent_report,
    calibration_report,
    ceiling_forecast,
    forecast_breakdown,
    forecast_interval,
    profile_coverage,
)


class ForecastView(views.APIView):
    """Прогноз балла с «рычагами»: текущий балл и потолок при заданном темпе.

    GET /api/forecast/?weekly_hours=10&exam_date=2027-06-01 — ученик «играет»
    ползунком темпа и датой и видит, как двигается потолок.
    """

    def get(self, request):
        student = get_student(request)
        weekly_hours = None
        if request.query_params.get("weekly_hours"):
            try:
                weekly_hours = max(1, int(request.query_params["weekly_hours"]))
            except ValueError:
                return Response({"detail": "weekly_hours должен быть числом."}, status=400)
        exam_date = None
        if request.query_params.get("exam_date"):
            try:
                exam_date = date.fromisoformat(request.query_params["exam_date"])
            except ValueError:
                return Response({"detail": "exam_date в формате YYYY-MM-DD."}, status=400)
        forecast = ceiling_forecast(student, weekly_hours=weekly_hours, exam_date=exam_date)
        forecast["target_score"] = student.target_score
        # Интервал: ученику честнее видеть «68–74», чем «71».
        forecast["interval"] = forecast_interval(student)
        forecast["calibration"] = calibration_report(student, limit=5)
        # Разбор по заданиям: «задача 13 даёт +0.8 балла при p=0.4».
        forecast["tasks"] = forecast_breakdown(student)
        # Недоразмеченный профиль занижает прогноз — это видно явно.
        forecast["exam_profile_coverage"] = profile_coverage()
        return Response(forecast)


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
