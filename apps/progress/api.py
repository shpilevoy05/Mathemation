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
        # Шкала на странице должна двигаться вместе с ползунком: без этих
        # процентов она оставалась в исходном положении и выглядела сломанной.
        from apps.web.services import primary_gauge

        gauge = primary_gauge(student)
        forecast["gauge"] = {
            "now_percent": gauge["now_percent"],
            "target_percent": gauge["target_percent"],
            "band_left_percent": gauge["band_left_percent"],
            "band_width_percent": gauge["band_width_percent"],
            "ceiling_percent": _ceiling_percent(gauge, forecast),
            "ceiling_primary": _ceiling_primary(forecast),
            "primary": gauge["primary"],
        }
        return Response(forecast)


def _ceiling_primary(forecast: dict) -> float | None:
    """Потолок в первичных баллах при выбранных условиях."""
    from apps.progress.services import primary_for_scaled

    ceiling = forecast.get("ceiling_score")
    return None if ceiling is None else primary_for_scaled(ceiling)


def _ceiling_percent(gauge: dict, forecast: dict) -> float | None:
    """Где на шкале стоит потолок при выбранных условиях."""
    from apps.progress.services import primary_for_scaled

    maximum = gauge["max_primary"] or 1
    ceiling = forecast.get("ceiling_score")
    if ceiling is None:
        return None
    return round(min(max(primary_for_scaled(ceiling) / maximum, 0), 1) * 100, 2)


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
