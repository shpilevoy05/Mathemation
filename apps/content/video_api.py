"""Выдача ссылки на плеер занятия.

Отдельная точка входа нужна ровно затем, чтобы ссылка на видео не лежала в
HTML: страницу можно сохранить, отправить, показать через плечо. Здесь же
единственное место, где проверяется право смотреть, и единственное, что видно
в логах при разборе утечки.
"""

from __future__ import annotations

import logging

from django.shortcuts import get_object_or_404
from rest_framework import permissions, views
from rest_framework.response import Response

from apps.billing.access import Feature
from apps.billing.gate import HasFeature

from .lessons import mark_material_viewed
from .models import Lesson
from .video import playback_link

logger = logging.getLogger("matemacia.integrations")


class LessonPlaybackView(views.APIView):
    """GET /api/lessons/<id>/playback/ — короткоживущая ссылка на видео."""

    permission_classes = [permissions.IsAuthenticated, HasFeature]
    feature = Feature.LESSONS

    def get(self, request, lesson_id: int):
        lesson = get_object_or_404(
            Lesson, pk=lesson_id, status=Lesson.Status.PUBLISHED
        )
        if not lesson.has_video:
            return Response({"detail": "К занятию не приложено видео."}, status=404)

        student = getattr(request.user, "student_profile", None)
        link = playback_link(lesson, student)
        if not link.url:
            return Response({"detail": "Ссылка на видео не собрана."}, status=404)
        # Открытие материала — часть первого этапа занятия: ученик посмотрел
        # видео, значит этап начат.
        if student is not None:
            mark_material_viewed(student, lesson.node)
        logger.info(
            "video.playback lesson=%s provider=%s private=%s student=%s",
            lesson.pk, link.provider, link.is_private,
            student.pk if student is not None else "-",
        )
        return Response(link.as_dict())
