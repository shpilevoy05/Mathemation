from datetime import date, timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import views
from rest_framework.response import Response

from apps.accounts.api import get_student

from .models import PlanChangeLog, StudyPlanItem, TrajectoryTransition
from .services import (
    PlanItemMoveRefused,
    acknowledge_trajectory_transition,
    complete_item,
    get_active_plan,
    items_for_period,
    move_item,
)


def _transition_payload(transition: TrajectoryTransition) -> dict:
    return {
        "id": transition.id,
        "from_trajectory": (
            transition.from_trajectory.slug if transition.from_trajectory else None
        ),
        "to_trajectory": transition.to_trajectory.slug,
        "reasons": transition.reasons,
        "recovery_actions": transition.recovery_actions,
        "acknowledged": transition.acknowledged,
        "created_at": transition.created_at,
    }


class TrajectoryView(views.APIView):
    def get(self, request):
        student = get_student(request)
        plan = get_active_plan(student)
        if plan is None or plan.trajectory is None:
            return Response({"detail": "Траектория ещё не назначена."}, status=404)
        trajectory = plan.trajectory
        transitions = (
            TrajectoryTransition.objects.filter(student=student, acknowledged=False)
            .select_related("from_trajectory", "to_trajectory")
        )
        return Response({
            "slug": trajectory.slug,
            "title": trajectory.title,
            "target_min": trajectory.target_min,
            "target_max": trajectory.target_max,
            "weekly_load_hours": trajectory.weekly_load_hours,
            "message": "Траектория рассчитана при текущем темпе подготовки.",
            "unacknowledged_transitions": [
                _transition_payload(transition) for transition in transitions
            ],
        })


class AcknowledgeTrajectoryTransitionView(views.APIView):
    def post(self, request, transition_id):
        student = get_student(request)
        try:
            transition = acknowledge_trajectory_transition(student, transition_id)
        except TrajectoryTransition.DoesNotExist:
            return Response({"detail": "Переход не найден."}, status=404)
        return Response(_transition_payload(transition))


def _item_payload(item):
    return {
        "id": item.id,
        "type": item.item_type,
        "node": item.node.title if item.node else None,
        "node_id": item.node_id,
        "week_index": item.week_index,
        "due_date": item.due_date,
        "status": item.status,
    }


class PlanView(views.APIView):
    def get(self, request):
        student = get_student(request)
        plan = get_active_plan(student)
        if plan is None:
            return Response({"detail": "План ещё не построен — пройдите диагностику."}, status=404)
        return Response({
            "id": plan.id,
            "target_score": plan.target_score,
            "created_at": plan.created_at,
            "items": [_item_payload(i) for i in plan.items.select_related("node")],
        })


class TodayPlanView(views.APIView):
    def get(self, request):
        student = get_student(request)
        today = timezone.localdate()
        return Response([_item_payload(i) for i in items_for_period(student, today, today)])


class WeekPlanView(views.APIView):
    def get(self, request):
        student = get_student(request)
        today = timezone.localdate()
        start = today - timedelta(days=today.weekday())
        return Response([
            _item_payload(i)
            for i in items_for_period(student, start, start + timedelta(days=6))
        ])


class CompleteItemView(views.APIView):
    """POST /api/plan/items/<id>/complete/ — отметить пункт чек-листа сделанным."""

    def post(self, request, item_id):
        student = get_student(request)
        item = get_object_or_404(
            StudyPlanItem, pk=item_id, plan__student=student
        )
        complete_item(item)
        return Response(_item_payload(item))


class MoveItemView(views.APIView):
    """POST /api/plan/items/<id>/move/ {"due_date": "2026-09-01"} — перенести пункт."""

    def post(self, request, item_id):
        student = get_student(request)
        item = get_object_or_404(StudyPlanItem, pk=item_id, plan__student=student)
        raw = request.data.get("due_date", "")
        try:
            new_date = date.fromisoformat(str(raw))
        except ValueError:
            return Response({"detail": "Дата в формате ГГГГ-ММ-ДД."}, status=400)
        try:
            move_item(item, new_date)
        except PlanItemMoveRefused as error:
            # 409: запрос понятен, но противоречит правилам плана.
            return Response({"detail": str(error)}, status=409)
        return Response(_item_payload(item))


def _change_payload(c: PlanChangeLog) -> dict:
    return {
        "id": c.id,
        "reason": c.reason,
        "description": c.description,
        "is_major": c.is_major,
        "acknowledged": c.acknowledged,
        "created_at": c.created_at,
    }


class PlanChangesView(views.APIView):
    """«Карточка изменений плана» — лог того, что поменялось, когда и почему.

    ?major=1&unacknowledged=1 — резкие изменения для большого всплывающего окна.
    """

    def get(self, request):
        student = get_student(request)
        plan = get_active_plan(student)
        if plan is None:
            return Response([])
        qs = plan.change_logs.all()
        if request.query_params.get("major"):
            qs = qs.filter(is_major=True)
        if request.query_params.get("unacknowledged"):
            qs = qs.filter(acknowledged=False)
        return Response([_change_payload(c) for c in qs[:50]])


class AcknowledgeChangeView(views.APIView):
    """POST — ученик закрыл всплывающее окно с изменением плана."""

    def post(self, request, change_id):
        student = get_student(request)
        change = get_object_or_404(
            PlanChangeLog, pk=change_id, plan__student=student
        )
        change.acknowledged = True
        change.save(update_fields=["acknowledged"])
        return Response(_change_payload(change))
