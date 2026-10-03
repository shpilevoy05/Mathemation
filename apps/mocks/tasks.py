from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def finalize_expired_mocks():
    from .services import finalize_expired_mocks_for

    try:
        return finalize_expired_mocks_for()
    except Exception:
        logger.exception("Could not finalize expired mock results")
        raise
