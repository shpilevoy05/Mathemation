from rest_framework import serializers, viewsets

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
