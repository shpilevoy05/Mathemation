from rest_framework import serializers, views, viewsets
from rest_framework.response import Response

from .models import Assignment, Lesson, TheoryBlock


class TheoryBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = TheoryBlock
        fields = ["id", "title", "body", "order"]


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assignment
        # correct_answer intentionally excluded from API output.
        fields = ["id", "title", "statement", "exam_part", "difficulty", "max_score", "lesson"]


class LessonSerializer(serializers.ModelSerializer):
    theory_blocks = TheoryBlockSerializer(many=True, read_only=True)
    assignments = AssignmentSerializer(many=True, read_only=True)

    class Meta:
        model = Lesson
        fields = ["id", "title", "order", "node", "theory_blocks", "assignments"]


class LessonViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Lesson.objects.prefetch_related("theory_blocks", "assignments")
    serializer_class = LessonSerializer


class AssignmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Assignment.objects.all()
    serializer_class = AssignmentSerializer


class TrackView(views.APIView):
    """«Дорожка» как в Дуолинго: темы разделены цветами, внутри — точки
    уроков и практики, отдельные точки отработки в конце темы и пробников."""

    def get(self, request):
        from apps.accounts.api import get_student
        from apps.knowledge.models import TopicCluster
        from apps.knowledge.services import node_states
        from apps.mocks.models import MockExam
        from apps.practice.models import MistakeBacklogItem

        student = get_student(request)
        states = node_states(student)
        open_mistake_nodes = set(
            MistakeBacklogItem.objects.filter(student=student)
            .exclude(status=MistakeBacklogItem.Status.RESOLVED)
            .values_list("node_id", flat=True)
        )

        track = []
        for cluster in TopicCluster.objects.prefetch_related("nodes__lessons"):
            points = []
            cluster_has_mistakes = False
            for node in cluster.nodes.all():
                s = states.get(node.id, {})
                state = s.get("state", "locked")
                for lesson in node.lessons.all():
                    points.append({
                        "type": "lesson",
                        "lesson_id": lesson.id,
                        "node_id": node.id,
                        "title": lesson.title,
                        "state": state,
                    })
                points.append({
                    "type": "practice",
                    "node_id": node.id,
                    "title": f"Практика: {node.title}",
                    "state": state,
                })
                if node.id in open_mistake_nodes:
                    cluster_has_mistakes = True
            if cluster_has_mistakes:
                points.append({
                    "type": "review",
                    "title": f"Отработка ошибок: {cluster.title}",
                    "state": "available",
                })
            track.append({
                "cluster_id": cluster.id,
                "title": cluster.title,
                "color": cluster.color,
                "points": points,
            })

        mocks = [
            {"type": "mock", "mock_id": m.id, "title": m.title}
            for m in MockExam.objects.filter(is_active=True)
        ]
        return Response({"track": track, "mock_points": mocks})
