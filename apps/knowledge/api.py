from rest_framework import serializers, views
from rest_framework.response import Response

from apps.accounts.api import get_student

from .models import KnowledgeNode, SkillMastery


class KnowledgeMapView(views.APIView):
    """Карта знаний ученика: узлы, зависимости, mastery и статусы."""

    def get(self, request):
        student = get_student(request)
        masteries = {
            m.node_id: m
            for m in SkillMastery.objects.filter(student=student)
        }
        nodes = []
        for node in KnowledgeNode.objects.select_related("cluster").prefetch_related(
            "dependencies"
        ):
            m = masteries.get(node.id)
            nodes.append({
                "id": node.id,
                "code": node.code,
                "title": node.title,
                "cluster": node.cluster.title,
                "exam_part": node.exam_part,
                "mastery": m.mastery if m else 0,
                "status": m.status if m else SkillMastery.Status.NOT_STARTED,
                "prerequisites": [d.prerequisite_id for d in node.dependencies.all()],
            })
        return Response({"nodes": nodes})
