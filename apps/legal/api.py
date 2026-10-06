from rest_framework import permissions, serializers, status, views
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .services import create_feedback


class FeedbackCreateSerializer(serializers.Serializer):
    page_url = serializers.CharField(max_length=500, required=False, allow_blank=True)
    message = serializers.CharField(max_length=2000, allow_blank=False, trim_whitespace=True)


class FeedbackView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "feedback"

    def post(self, request):
        serializer = FeedbackCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        feedback = create_feedback(request.user, **serializer.validated_data)
        return Response({"id": feedback.pk, "status": feedback.status}, status=status.HTTP_201_CREATED)
