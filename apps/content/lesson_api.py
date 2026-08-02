"""Этапы занятия и конспект для скачивания."""

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import views
from rest_framework.response import Response

from apps.accounts.api import get_student
from apps.knowledge.models import KnowledgeNode

from .lessons import (
    lesson_stages,
    lesson_summary_text,
    mark_material_viewed,
    mark_summary_downloaded,
)


def _stage_payload(student, node) -> dict:
    stages = lesson_stages(student, node)
    return {
        "node_id": node.id,
        "stages": [
            {key: value for key, value in stage.items() if key != "detail"}
            for stage in stages
        ],
        "is_complete": all(stage["is_done"] for stage in stages),
    }


class LessonStageView(views.APIView):
    """GET — состояние этапов, POST — отметить материал просмотренным."""

    def get(self, request, node_id: int):
        student = get_student(request)
        node = get_object_or_404(KnowledgeNode, pk=node_id)
        return Response(_stage_payload(student, node))

    def post(self, request, node_id: int):
        student = get_student(request)
        node = get_object_or_404(KnowledgeNode, pk=node_id)
        mark_material_viewed(student, node)
        return Response(_stage_payload(student, node))


@login_required
def lesson_summary(request, node_id: int):
    """Конспект занятия файлом.

    Доступ только ученику: конспект — часть оплаченного продукта, и раздавать
    его анонимно нельзя.
    """
    student = getattr(request.user, "student_profile", None)
    if student is None:
        raise Http404
    node = get_object_or_404(KnowledgeNode, pk=node_id)
    mark_summary_downloaded(student, node)
    filename = f"konspekt-{slugify(node.code or node.title) or node.id}.md"
    response = HttpResponse(
        lesson_summary_text(node), content_type="text/markdown; charset=utf-8"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
