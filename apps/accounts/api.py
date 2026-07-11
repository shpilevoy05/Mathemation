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
