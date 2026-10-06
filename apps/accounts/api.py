from rest_framework import permissions, serializers, views
from rest_framework.response import Response

from .models import StudentProfile


def get_student(request) -> StudentProfile:
    """Resolve the current student profile or raise 404-style error."""
    profile = getattr(request.user, "student_profile", None)
    if profile is None:
        raise serializers.ValidationError("У пользователя нет профиля ученика.")
    return profile


class MeView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        data = {"id": request.user.id, "username": request.user.username,
                "role": request.user.role}
        profile = getattr(request.user, "student_profile", None)
        if profile:
            data["student"] = {
                "target_score": profile.target_score,
                "start_score": profile.start_score,
                "exam_date": profile.exam_date,
            }
        return Response(data)


class TargetScoreSerializer(serializers.Serializer):
    target_score = serializers.IntegerField(
        min_value=40,
        max_value=100,
        error_messages={
            "required": "Укажите целевой балл.",
            "invalid": "Целевой балл должен быть целым числом.",
            "min_value": "Целевой балл должен быть не меньше 40.",
            "max_value": "Целевой балл должен быть не больше 100.",
        },
    )


class TargetScoreView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from apps.planning.services import change_target_score
        from apps.progress.services import ceiling_forecast

        student = get_student(request)
        serializer = TargetScoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = change_target_score(student, serializer.validated_data["target_score"])
        trajectory = result["trajectory"]
        forecast = ceiling_forecast(student)
        return Response({
            "target_score": result["target_score"],
            "trajectory_changed": result["trajectory_changed"],
            "trajectory": {
                "id": trajectory.id,
                "slug": trajectory.slug,
                "title": trajectory.title,
                "target_min": trajectory.target_min,
                "target_max": trajectory.target_max,
                "weekly_load_hours": trajectory.weekly_load_hours,
            },
            "forecast": {
                "current_score": forecast["current_score"],
                "ceiling_score": forecast["ceiling_score"],
            },
        })
