from django.shortcuts import get_object_or_404
from rest_framework import serializers, views
from rest_framework.response import Response

from apps.accounts.api import get_student
from apps.content.models import Assignment

from .models import Attempt, MistakeBacklogItem, ReviewSchedule
from .services import complete_review, due_reviews, practice_queue, submit_attempt


class AttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attempt
        fields = ["id", "assignment", "context", "submitted_answer", "is_correct", "created_at"]


class SubmitAttemptView(views.APIView):
    """POST /api/assignments/<id>/attempt/ {"answer": "...", "context": "lesson"}"""

    def post(self, request, assignment_id):
        student = get_student(request)
        assignment = get_object_or_404(Assignment, pk=assignment_id)
        context = request.data.get("context", Attempt.Context.LESSON)
        if context not in Attempt.Context.values:
            return Response({"detail": "Неизвестный контекст."}, status=400)
        attempt = submit_attempt(
            student, assignment, request.data.get("answer", ""), context
        )
        return Response(AttemptSerializer(attempt).data, status=201)


class BacklogView(views.APIView):
    def get(self, request):
        student = get_student(request)
        items = (
            MistakeBacklogItem.objects.filter(student=student)
            .exclude(status=MistakeBacklogItem.Status.RESOLVED)
            .select_related("assignment", "node")
        )
        return Response([
            {
                "id": i.id,
                "assignment_id": i.assignment_id,
                "assignment": i.assignment.title,
                "node": i.node.title,
                "status": i.status,
                "error_count": i.error_count,
            }
            for i in items
        ])


class DueReviewsView(views.APIView):
    """GET — отработки на сегодня; POST /reviews/<id>/complete/ — результат."""

    def get(self, request):
        student = get_student(request)
        return Response([
            {
                "id": r.id,
                "due_date": r.due_date,
                "interval_days": r.interval_days,
                "assignment_id": r.backlog_item.assignment_id,
                "assignment": r.backlog_item.assignment.title,
                "node": r.backlog_item.node.title,
            }
            for r in due_reviews(student)
        ])


class CompleteReviewView(views.APIView):
    def post(self, request, review_id):
        student = get_student(request)
        review = get_object_or_404(
            ReviewSchedule, pk=review_id, backlog_item__student=student
        )
        complete_review(review, success=bool(request.data.get("success")))
        item = review.backlog_item
        resolved = item.status == MistakeBacklogItem.Status.RESOLVED
        payload = {"status": review.status, "mistake_resolved": resolved}
        if resolved:
            # Закрытие петли мотивирует.
            payload["message"] = f"Эту ошибку ты уже не делаешь: «{item.node.title}» ✅"
        return Response(payload)


class NodePracticeView(views.APIView):
    """GET /api/nodes/<id>/practice/ — очередь занятия: сначала 1-2 задачи
    на старые слабые места, затем задачи новой темы."""

    def get(self, request, node_id):
        from apps.content.api import AssignmentSerializer
        from apps.knowledge.models import KnowledgeNode

        student = get_student(request)
        node = get_object_or_404(KnowledgeNode, pk=node_id)
        queue = practice_queue(student, node)
        return Response({
            "warmup": AssignmentSerializer(queue["warmup"], many=True).data,
            "new": AssignmentSerializer(queue["new"], many=True).data,
        })
