from django.shortcuts import get_object_or_404
from rest_framework import views
from rest_framework.response import Response

from apps.accounts.api import get_student
from apps.content.models import Assignment
from apps.practice.models import Attempt

from .services import HintNotAllowed, request_hint


class HintView(views.APIView):
    """POST /api/assignments/<id>/hint/ {"question": "...", "context": "lesson"}"""

    def post(self, request, assignment_id):
        student = get_student(request)
        assignment = get_object_or_404(Assignment, pk=assignment_id)
        try:
            result = request_hint(
                student, assignment,
                question=request.data.get("question", ""),
                context=request.data.get("context", Attempt.Context.LESSON),
            )
        except HintNotAllowed as e:
            return Response({"detail": str(e)}, status=403)
        return Response({
            "hint": result["text"],
            "hints_used": result["session"].hints_used,
            "escalated_to_expert": result["escalated"],
        })
