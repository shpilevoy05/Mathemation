from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Post, RubricSlot
from .services import draft_post
from .sources import fetch_source, mark_content_idea_used


def plan_week(now=None) -> list[Post]:
    if not settings.SOCIAL_AGENT_ENABLED:
        return []
    local_tz = ZoneInfo(settings.TIME_ZONE)
    current = now or timezone.now()
    if timezone.is_naive(current):
        current = timezone.make_aware(current, local_tz)
    local_now = current.astimezone(local_tz)
    slots = RubricSlot.objects.select_related("channel", "rubric").filter(
        is_active=True,
        channel__is_active=True,
        rubric__is_active=True,
    )
    created_posts = []
    for offset in range(7):
        on_date = local_now.date() + timedelta(days=offset)
        for slot in slots:
            if slot.weekday != on_date.weekday():
                continue
            scheduled_for = datetime.combine(on_date, slot.time, tzinfo=local_tz)
            if scheduled_for <= current:
                continue
            if Post.objects.filter(
                channel=slot.channel, rubric=slot.rubric, scheduled_for=scheduled_for
            ).exists():
                continue
            material = fetch_source(slot.rubric, on_date)
            if material is None:
                continue
            with transaction.atomic():
                post, created = Post.objects.get_or_create(
                    channel=slot.channel,
                    rubric=slot.rubric,
                    scheduled_for=scheduled_for,
                    defaults={"source_ref": material.source_ref},
                )
                if not created:
                    continue
                mark_content_idea_used(material)
            draft_post(post, material)
            created_posts.append(post)
    return created_posts
