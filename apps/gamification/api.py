from rest_framework import views
from rest_framework.response import Response

from apps.accounts.api import get_student

from .services import gamification_snapshot


class GamificationView(views.APIView):
    """Current XP, streak and this week's quests."""

    def get(self, request):
        return Response(gamification_snapshot(get_student(request)))

