from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, views
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.api import get_student
from apps.billing.access import Feature
from apps.billing.gate import HasFeature
from apps.content.models import Assignment

from .models import Attempt, MistakeBacklogItem, ReviewSchedule
from .services import (
    AnswerNotUnderstood,
    complete_review,
    due_reviews,
    practice_queue,
    submit_attempt,
)


class AttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attempt
        fields = ["id", "assignment", "context", "submitted_answer", "is_correct", "created_at"]


class SubmitAttemptView(views.APIView):
    """POST /api/assignments/<id>/attempt/ {"answer": "...", "context": "lesson"}"""
    # Ответы идут в append-only лог и двигают mastery: поток ограничиваем.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "attempt"
    permission_classes = [permissions.IsAuthenticated, HasFeature]
    feature = Feature.PRACTICE

    def post(self, request, assignment_id):
        student = get_student(request)
        assignment = get_object_or_404(Assignment, pk=assignment_id)
        context = request.data.get("context", Attempt.Context.LESSON)
        if context not in Attempt.Context.values:
            return Response({"detail": "Неизвестный контекст."}, status=400)
        # Награда за ответ показывается ученику числом, поэтому её измеряем
        # до и после попытки: XP и сигмы начисляются глубоко в домене, и
        # собирать их по кускам в интерфейсе было бы враньём.
        before = _reward_state(student)
        try:
            attempt = submit_attempt(
                student, assignment, request.data.get("answer", ""), context
            )
        except AnswerNotUnderstood as error:
            # 422: ответ дошёл, но прочитать его не удалось. Не 400 — с формой
            # запроса всё в порядке, и не «неверно» — ученик не ошибся в теме.
            return Response({"detail": str(error), "code": "answer_not_understood"}, status=422)
        payload = AttemptSerializer(attempt).data
        # Ученик должен видеть, что ответ что-то изменил: рост освоения темы,
        # закрытые пункты плана и прогресс по задачам узла.
        payload["progress"] = attempt_progress(student, assignment)
        payload["rewards"] = _rewards_since(student, before)
        return Response(payload, status=201)


def _reward_state(student) -> dict:
    """Снимок наград до действия: XP, сигмы и освоение тем задачи."""
    from apps.economy.services import get_wallet
    from apps.gamification.models import GamificationProfile
    from apps.knowledge.models import SkillMastery

    profile, _ = GamificationProfile.objects.get_or_create(student=student)
    return {
        "xp": profile.xp,
        "level": profile.level,
        "coins": get_wallet(student).balance,
        "mastery": {
            mastery.node_id: float(mastery.mastery)
            for mastery in SkillMastery.objects.filter(student=student)
        },
    }


def _rewards_since(student, before: dict) -> dict:
    """Насколько выросли XP, сигмы и освоение после действия."""
    after = _reward_state(student)
    mastery_gain = [
        {
            "node_id": node_id,
            "from": round(before["mastery"].get(node_id, 0.0), 1),
            "to": round(value, 1),
            "delta": round(value - before["mastery"].get(node_id, 0.0), 1),
        }
        for node_id, value in after["mastery"].items()
        if round(value - before["mastery"].get(node_id, 0.0), 1) > 0
    ]
    return {
        "xp": after["xp"] - before["xp"],
        "coins": after["coins"] - before["coins"],
        "level_up": after["level"] > before["level"],
        "level": after["level"],
        "mastery": mastery_gain,
    }


def attempt_progress(student, assignment) -> list[dict]:
    """Прогресс по темам задачи: освоение, статус и решённые задачи узла."""
    from apps.knowledge.models import SkillMastery
    from apps.planning.models import StudyPlanItem
    from apps.planning.services import get_active_plan

    plan = get_active_plan(student)
    progress = []
    for tag in assignment.skill_tags.select_related("node"):
        node = tag.node
        mastery = SkillMastery.objects.filter(student=student, node=node).first()
        solved = (
            Attempt.objects.filter(
                student=student, assignment__skill_tags__node=node, is_correct=True
            )
            .values("assignment_id")
            .distinct()
            .count()
        )
        total = Assignment.objects.filter(skill_tags__node=node).distinct().count()
        completed_items = (
            list(
                plan.items.filter(
                    node=node, status=StudyPlanItem.Status.DONE
                ).values_list("item_type", flat=True)
            )
            if plan
            else []
        )
        progress.append({
            "node_id": node.id,
            "node": node.title,
            "mastery": round(float(mastery.mastery), 1) if mastery else 0.0,
            "status": mastery.status if mastery else "not_started",
            "solved": solved,
            "total": total,
            "completed_plan_items": completed_items,
        })
    return progress


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
                "error_type": i.error_type,
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
    permission_classes = [permissions.IsAuthenticated, HasFeature]
    feature = Feature.PRACTICE

    def post(self, request, review_id):
        student = get_student(request)
        review = get_object_or_404(
            ReviewSchedule, pk=review_id, backlog_item__student=student
        )
        before = _reward_state(student)
        complete_review(review, success=bool(request.data.get("success")))
        item = review.backlog_item
        resolved = item.status == MistakeBacklogItem.Status.RESOLVED
        payload = {
            "status": review.status,
            "mistake_resolved": resolved,
            "rewards": _rewards_since(student, before),
        }
        if resolved:
            # Закрытие петли мотивирует.
            payload["message"] = f"Эту ошибку ты уже не делаешь: «{item.node.title}» ✅"
        return Response(payload)


class NodePracticeView(views.APIView):
    """GET /api/nodes/<id>/practice/ — очередь занятия: сначала 1-2 задачи
    на старые слабые места, затем задачи новой темы."""

    permission_classes = [permissions.IsAuthenticated, HasFeature]
    feature = Feature.PRACTICE

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
