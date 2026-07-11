from celery import shared_task


@shared_task
def generate_weekly_quests_all():
    """Generate this week's quests for every active student."""
    from apps.accounts.models import StudentProfile

    from .services import generate_weekly_quests

    for student in StudentProfile.objects.filter(user__is_active=True).iterator():
        generate_weekly_quests(student)

