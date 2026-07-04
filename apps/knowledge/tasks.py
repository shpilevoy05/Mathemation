from celery import shared_task


@shared_task
def apply_decay_all():
    """Nightly forgetting-curve pass over all students (celery beat)."""
    from apps.accounts.models import StudentProfile

    from .services import apply_decay

    for student in StudentProfile.objects.all():
        apply_decay(student)
