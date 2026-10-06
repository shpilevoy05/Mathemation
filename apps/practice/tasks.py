from celery import shared_task


@shared_task
def mark_missed_reviews():
    """Flag overdue spaced-repetition reviews (schedule daily via celery beat)."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import ReviewSchedule

    ReviewSchedule.objects.filter(
        status=ReviewSchedule.Status.PENDING,
        due_date__lt=timezone.localdate() - timedelta(days=1),
    ).update(status=ReviewSchedule.Status.MISSED)
