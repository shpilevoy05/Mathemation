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


class ParentAiLogView(views.APIView):
    """Родительский контур: детальный лог общения ребёнка с ИИ.

    GET ?student=<id> — список сессий (тема, задача, число подсказок);
    GET ?student=<id>&session=<id> — переписка внутри одной сессии.
    """

    def get(self, request):
        parent = getattr(request.user, "parent_profile", None)
        if parent is None:
            return Response({"detail": "Нет профиля родителя."}, status=403)
        student_id = request.query_params.get("student")
        children = parent.children.all()
        student = children.filter(pk=student_id).first() if student_id else children.first()
        if student is None:
            return Response({"detail": "Ученик не найден."}, status=404)

        from .models import AiHintSession

        session_id = request.query_params.get("session")
        if session_id:
            session = get_object_or_404(AiHintSession, pk=session_id, student=student)
            return Response({
                "assignment": session.assignment.title,
                "node": session.node.title if session.node else None,
                "hints_used": session.hints_used,
                "escalated_to_expert": session.escalated_to_expert,
                "messages": [
                    {"role": m.role, "text": m.text, "created_at": m.created_at}
                    for m in session.messages.filter(is_blocked=False)
                ],
            })
        return Response([
            {
                "id": s.id,
                "assignment": s.assignment.title,
                "node": s.node.title if s.node else None,
                "hints_used": s.hints_used,
                "escalated_to_expert": s.escalated_to_expert,
                "created_at": s.created_at,
            }
            for s in AiHintSession.objects.filter(student=student)
            .select_related("assignment", "node")
            .order_by("-created_at")
        ])
