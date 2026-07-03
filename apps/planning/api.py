from datetime import timedelta

from django.utils import timezone
from rest_framework import views
from rest_framework.response import Response

from apps.accounts.api import get_student

from .services import get_active_plan, items_for_period


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
