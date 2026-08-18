from django.shortcuts import get_object_or_404
from rest_framework import views
from rest_framework.response import Response

from apps.accounts.api import get_student

from .models import KnowledgeNode, TopicCluster
from .services import apply_decay, node_states


class KnowledgeMapView(views.APIView):
    """Карта знаний: кластеры → созвездия узлов.

    Узел: % освоения, номера ЕГЭ, дата последней практики, индикатор
    забывания, состояние (закрыто/можно начинать/в процессе/освоено/подзабылось).
    ?overlay=ceiling добавляет к узлам флаг «реально успеть до экзамена»
    при текущем темпе (честный механизм: карта не делает вид, что всё достижимо).
    """

    def get(self, request):
        student = get_student(request)
        # Пересчёт забывания при каждом открытии карты (идемпотентно).
        apply_decay(student)
        states = node_states(student)

        unreachable: set[int] = set()
        overlay = request.query_params.get("overlay") == "ceiling"
        if overlay:
            from apps.progress.services import ceiling_forecast

            unreachable = set(ceiling_forecast(student)["unreachable_node_ids"])

        clusters = []
        for cluster in TopicCluster.objects.prefetch_related("nodes"):
            nodes = []
            for node in cluster.nodes.all():
                s = states.get(node.id, {})
                payload = {
                    "id": node.id,
                    "code": node.code,
                    "title": node.title,
                    "node_type": node.node_type,
                    "parent_id": node.parent_id,
                    "exam_part": node.exam_part,
                    "ege_task_numbers": node.ege_task_numbers,
                    "mastery": s.get("mastery", 0),
                    "state": s.get("state", "locked"),
                    "decay_percent": s.get("decay_percent", 0),
                    "last_practiced_at": s.get("last_practiced_at"),
                    "prerequisites": s.get("prerequisites", []),
                    "unmet_conditions": s.get("unmet_conditions", []),
                    # Поддерживающие связи не закрывают тему, поэтому лежат
                    # отдельно от условий открытия.
                    "supporting": s.get("supporting", []),
                }
                if overlay:
                    payload["reachable_by_exam"] = node.id not in unreachable
                nodes.append(payload)
            # Счётчик темы — про навыки: папка не «освоена», она агрегат.
            skills = [n for n in nodes if n["node_type"] != KnowledgeNode.NodeType.GROUP]
            mastered = sum(1 for n in skills if n["state"] == "mastered")
            clusters.append({
                "id": cluster.id,
                "title": cluster.title,
                "color": cluster.color,
                "nodes_total": len(skills),
                "nodes_mastered": mastered,
                "nodes": nodes,
            })
        return Response({"clusters": clusters})


class NodeDetailView(views.APIView):
    """Внутри узла: короткая теория, история ошибок по нему, переход к урокам."""

    def get(self, request, node_id):
        student = get_student(request)
        node = get_object_or_404(
            KnowledgeNode.objects.select_related("cluster"), pk=node_id
        )
        s = node_states(student).get(node.id, {})

        lessons = [
            {"id": lesson.id, "title": lesson.title}
            for lesson in node.lessons.all()
        ]
        theory = []
        for lesson in node.lessons.prefetch_related("theory_blocks"):
            for block in lesson.theory_blocks.all():
                theory.append({"title": block.title, "body": block.body})

        from apps.practice.models import MistakeBacklogItem

        mistakes = [
            {
                "assignment": item.assignment.title,
                "status": item.status,
                "error_count": item.error_count,
                "created_at": item.created_at,
                "resolved_at": item.resolved_at,
            }
            for item in MistakeBacklogItem.objects.filter(
                student=student, node=node
            ).select_related("assignment")
        ]

        return Response({
            "id": node.id,
            "code": node.code,
            "title": node.title,
            "cluster": node.cluster.title,
            "exam_part": node.exam_part,
            "ege_task_numbers": node.ege_task_numbers,
            "mastery": s.get("mastery", 0),
            "state": s.get("state", "locked"),
            "decay_percent": s.get("decay_percent", 0),
            "last_practiced_at": s.get("last_practiced_at"),
            "theory": theory,
            "lessons": lessons,
            "mistake_history": mistakes,
        })
