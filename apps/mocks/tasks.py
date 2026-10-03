from celery import shared_task
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


@shared_task
def finalize_expired_mocks():
    from .models import MockExamResult
    from .services import submit_mock
    for result in MockExamResult.objects.filter(status="in_progress").select_related("exam").iterator():
        if timezone.now() >= result.deadline:
            try:
                submit_mock(result, {})
            except Exception:
                logger.exception("Could not finalize expired mock result %s", result.pk)
