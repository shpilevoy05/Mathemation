from celery import shared_task
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from .models import Post
from .planner import plan_week
from .services import PUBLISH_MAX_ATTEMPTS, PUBLISH_RETRY_SECONDS, publish_attempts, publish_scheduled_post, transition

@shared_task
def plan_week_task():
    if not settings.SOCIAL_AGENT_ENABLED:
        return 0
    return len(plan_week())


@shared_task
def publish_due_posts():
    if not settings.SOCIAL_AGENT_ENABLED or not settings.SOCIAL_AGENT_PUBLISH_ENABLED:
        return 0
    published = 0
    retry_before = timezone.now() - timedelta(seconds=PUBLISH_RETRY_SECONDS)
    failed_posts = Post.objects.filter(
        status=Post.Status.FAILED,
        updated_at__lte=retry_before,
    )
    for post in failed_posts:
        if publish_attempts(post) < PUBLISH_MAX_ATTEMPTS:
            transition(post, Post.Status.SCHEDULED)
    posts = Post.objects.filter(
        status=Post.Status.SCHEDULED,
        scheduled_for__lte=timezone.now(),
    ).select_related("channel")
    for post in posts:
        if publish_scheduled_post(post):
            published += 1
    return published
