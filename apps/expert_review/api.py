import os
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import permissions, serializers, status
from rest_framework import views
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.api import get_student
from apps.billing.access import Feature
from apps.billing.gate import HasFeature
from apps.content.models import Assignment
from apps.knowledge.models import KnowledgeNode
from apps.practice.models import MistakeBacklogItem
from apps.web.permissions import is_expert

from .models import ExpertReviewRequest
from .permissions import can_view_solution
from .services import finish_review, submit_solution
from .validators import validate_solution_upload


class IsExpert(permissions.BasePermission):
    def has_permission(self, request, view):
        return is_expert(request.user)


class FinishExpertReviewSerializer(serializers.Serializer):
    score_by_criteria = serializers.DictField()
    error_tags = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    related_node_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list
    )
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    needs_resubmission = serializers.BooleanField(required=False, default=False)

    def validate_score_by_criteria(self, scores):
        max_score = self.context["review"].assignment.max_score
        if len(scores) > max_score:
            raise serializers.ValidationError("Критериев больше, чем баллов в задаче.")
        if any(type(name) is not str or type(score) is not int or score not in (0, 1)
               for name, score in scores.items()):
            raise serializers.ValidationError(
                "Критерии должны иметь строковые имена и баллы 0 или 1."
            )
        return scores

    def validate_error_tags(self, tags):
        valid = set(MistakeBacklogItem.ErrorType.values)
        if not set(tags).issubset(valid):
            raise serializers.ValidationError("Неизвестный тип ошибки.")
        return tags

    def validate_related_node_ids(self, node_ids):
        # Папку эксперт отметить не может: ошибка делается в конкретном навыке,
        # а освоение папки считается по детям.
        found = KnowledgeNode.objects.filter(pk__in=node_ids).exclude(
            node_type=KnowledgeNode.NodeType.GROUP
        )
        if found.count() != len(set(node_ids)):
            raise serializers.ValidationError("Одна или несколько тем не найдены.")
        return list(dict.fromkeys(node_ids))


def _payload(r: ExpertReviewRequest) -> dict:
    return {
        "id": r.id,
        "assignment_id": r.assignment_id,
        "status": r.status,
        "sla_hours": r.sla_hours,
        "total_score": r.total_score,
        "lost_points": r.lost_points,
        "score_by_criteria": r.score_by_criteria,
        "comment": r.comment,
        "error_tags": r.error_tags,
        "created_at": r.created_at,
        "sla_deadline": r.created_at + timedelta(hours=r.sla_hours),
        "reviewed_at": r.reviewed_at,
        # Прямой ссылки на файл не существует: только маршрут с проверкой прав.
        "file_url": reverse("expert-review-file", args=[r.id]) if r.solution_file else None,
    }


class ExpertReviewListView(views.APIView):
    def get(self, request):
        student = get_student(request)
        return Response([
            _payload(r)
            for r in ExpertReviewRequest.objects.filter(student=student)
        ])


class SubmitSolutionView(views.APIView):
    # Загрузка файлов — самый дорогой запрос по трафику и диску.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "upload"
    permission_classes = [permissions.IsAuthenticated, HasFeature]
    feature = Feature.EXPERT_REVIEW
    """POST multipart: assignment=<id>, file=<решение (фото/PDF)>."""

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        student = get_student(request)
        assignment = get_object_or_404(
            Assignment, pk=request.data.get("assignment"), exam_part=Assignment.Part.PART2
        )
        solution = request.FILES.get("file")
        if solution is None:
            return Response({"detail": "Файл решения обязателен."}, status=400)
        try:
            validate_solution_upload(solution)
        except DjangoValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=400)
        mock_result = None
        if request.data.get("mock_result"):
            from apps.mocks.models import MockExamResult

            mock_result = get_object_or_404(
                MockExamResult, pk=request.data["mock_result"], student=student
            )
        review = submit_solution(student, assignment, solution, mock_result=mock_result)
        return Response(_payload(review), status=201)


class SolutionFileView(views.APIView):
    """Отдаёт работу ученика только тому, кому она положена.

    GET /api/expert-reviews/<id>/file/

    Доступ проверяется на уровне объекта (`can_view_solution`); всем
    остальным — 404, чтобы не подтверждать существование работы. Если задан
    `PRIVATE_MEDIA_NGINX_LOCATION`, файл отдаёт nginx по X-Accel-Redirect.
    """

    def get(self, request, review_id: int):
        review = ExpertReviewRequest.objects.filter(pk=review_id).first()
        if review is None or not review.solution_file:
            raise Http404
        if not can_view_solution(request.user, review):
            raise Http404

        filename = os.path.basename(review.solution_file.name)
        nginx_location = settings.PRIVATE_MEDIA_NGINX_LOCATION
        if nginx_location:
            response = HttpResponse(status=200)
            response["X-Accel-Redirect"] = "%s/%s" % (
                nginx_location.rstrip("/"), review.solution_file.name
            )
            del response["Content-Type"]  # тип подставит nginx
        else:
            response = FileResponse(
                review.solution_file.open("rb"), as_attachment=False, filename=filename
            )
        response["Content-Disposition"] = 'inline; filename="%s"' % filename
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ExpertReviewFinishView(views.APIView):
    permission_classes = [IsExpert]

    def post(self, request, review_id):
        review = get_object_or_404(ExpertReviewRequest, pk=review_id)
        if review.status in {
            ExpertReviewRequest.Status.REVIEWED,
            ExpertReviewRequest.Status.NEEDS_RESUBMISSION,
        }:
            return Response(
                {"detail": "Проверка уже завершена."},
                status=status.HTTP_409_CONFLICT,
            )
        if review.status != ExpertReviewRequest.Status.SUBMITTED:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = FinishExpertReviewSerializer(
            data=request.data, context={"review": review}
        )
        serializer.is_valid(raise_exception=True)
        finish_review(review, reviewer=request.user, **serializer.validated_data)
        return Response(_payload(review))
