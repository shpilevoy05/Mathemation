from __future__ import annotations

import logging
import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .adapters import get_adapter
from .checks import all_passed, number_whitelist, run_checks
from .formulas import FormulaRenderError, to_telegram_text
from .models import BrandProfile, LlmCall, Post, PostCheck
from .providers import get_provider, record_llm_call
from .sources import SourceMaterial

logger = logging.getLogger(__name__)
PUBLISH_MAX_ATTEMPTS = 3
PUBLISH_RETRY_SECONDS = 60


class InvalidTransition(ValueError):
    pass


TRANSITIONS = {
    Post.Status.DRAFT: {Post.Status.CHECKING},
    Post.Status.CHECKING: {Post.Status.NEEDS_REVIEW, Post.Status.NEEDS_HUMAN},
    Post.Status.NEEDS_REVIEW: {Post.Status.APPROVED, Post.Status.REJECTED, Post.Status.REWRITING},
    Post.Status.REWRITING: {Post.Status.CHECKING},
    Post.Status.APPROVED: {Post.Status.SCHEDULED},
    Post.Status.SCHEDULED: {Post.Status.PUBLISHED, Post.Status.FAILED},
    Post.Status.FAILED: {Post.Status.SCHEDULED},
}


@transaction.atomic
def transition(post: Post, to_status: str, *, reason: str = "") -> Post:
    locked = Post.objects.select_for_update().get(pk=post.pk)
    if to_status not in TRANSITIONS.get(locked.status, set()):
        raise InvalidTransition(f"Недопустимый переход: {locked.status} -> {to_status}")
    locked.status = to_status
    fields = ["status", "updated_at"]
    if reason and to_status == Post.Status.FAILED:
        locked.failure_reason = reason
        fields.append("failure_reason")
    elif reason and to_status in {Post.Status.NEEDS_HUMAN, Post.Status.REJECTED, Post.Status.REWRITING}:
        locked.review_notes = reason
        fields.append("review_notes")
    locked.save(update_fields=fields)
    post.refresh_from_db()
    return post


def approve_post(post: Post, *, reason: str = "") -> Post:
    return transition(post, Post.Status.APPROVED, reason=reason)


def reject_post(post: Post, *, reason: str = "") -> Post:
    return transition(post, Post.Status.REJECTED, reason=reason)


def _prompt(post: Post, material: SourceMaterial, *, failed_details: str = "") -> list[dict]:
    profile = BrandProfile.objects.first()
    safe_draft = material.facts.get("statement") if material.assignment_id else material.reference_text
    safe_draft = safe_draft if isinstance(safe_draft, str) else material.reference_text
    brand = profile or BrandProfile()
    instruction = (
        f"Бренд: {brand.name or 'Матемация'}\n"
        f"Тон: {brand.tone_of_voice}\n"
        f"Примеры: {brand.good_post_examples}\n"
        f"Запрещено: {brand.forbidden_phrases}\n"
        f"Подпись: {brand.signature}\n"
        f"Хэштеги: {brand.hashtags}\n"
        f"Рубрика: {post.rubric.title}\n"
        f"Подсказка: {post.rubric.prompt_hint}\n"
        f"Проверенные факты: {material.facts}\n"
        f"Исходный материал: {material.reference_text}\n"
    )
    if failed_details:
        instruction += f"Исправь нарушения предыдущей версии:\n{failed_details}\n"
    instruction += f"<safe-draft>\n{safe_draft}\n</safe-draft>"
    return [
        {"role": "system", "content": "Напиши только текст поста, не добавляя неподтверждённых фактов и чисел."},
        {"role": "user", "content": instruction},
    ]


def _generate(post: Post, material: SourceMaterial, *, purpose: str, failed_details: str = "") -> str:
    result = get_provider().generate(_prompt(post, material, failed_details=failed_details), purpose=purpose, post=post)
    record_llm_call(result, purpose=purpose, post=post)
    return to_telegram_text(result.text)


def _failed_details(checks: list[PostCheck]) -> str:
    return "\n".join(f"{check.kind}: {check.detail}" for check in checks if not check.passed)


def _send_for_review(post: Post) -> None:
    try:
        from .bot import send_for_review

        send_for_review(post)
    except Exception as error:
        logger.warning("Could not send social post %s for review (%s)", post.pk, type(error).__name__)


def can_autopublish(post: Post, checks: list[PostCheck], material: SourceMaterial) -> tuple[bool, str]:
    if not settings.SOCIAL_AGENT_PUBLISH_ENABLED:
        return False, "publish_disabled"
    if post.channel.mode != post.channel.Mode.AUTO_SAFE:
        return False, "channel_manual"
    if post.rubric.risk != post.rubric.Risk.LOW or not post.rubric.autopublish_allowed:
        return False, "rubric_not_safe"
    if not checks or not all_passed(checks):
        return False, "checks_failed"
    if not number_whitelist(post.text, material, post.scheduled_for).passed:
        return False, "number_whitelist"
    return True, ""


def _run_drafting(post: Post, material: SourceMaterial, *, purpose: str, failed_details: str = "") -> Post:
    while True:
        try:
            post.text = _generate(post, material, purpose=purpose, failed_details=failed_details)
        except FormulaRenderError:
            transition(post, Post.Status.NEEDS_HUMAN, reason="formula_render")
            return post
        post.save(update_fields=["text", "updated_at"])
        checks = run_checks(post, material)
        if all_passed(checks):
            transition(post, Post.Status.NEEDS_REVIEW)
            allowed, _reason = can_autopublish(post, checks, material)
            if allowed:
                transition(post, Post.Status.APPROVED)
                transition(post, Post.Status.SCHEDULED)
            else:
                _send_for_review(post)
            return post
        failed_details = _failed_details(checks)
        if post.rewrite_count >= settings.SOCIAL_AGENT_MAX_REWRITES:
            transition(post, Post.Status.NEEDS_HUMAN, reason=failed_details)
            return post
        post.rewrite_count += 1
        post.save(update_fields=["rewrite_count", "updated_at"])
        purpose = LlmCall.Purpose.REWRITE


def draft_post(post: Post, material: SourceMaterial) -> Post:
    if post.status != Post.Status.DRAFT:
        return post
    transition(post, Post.Status.CHECKING)
    return _run_drafting(post, material, purpose=LlmCall.Purpose.DRAFT)


def rewrite_post(post: Post, material: SourceMaterial, instruction: str) -> Post:
    if post.status != Post.Status.REWRITING:
        return post
    transition(post, Post.Status.CHECKING)
    if post.rewrite_count >= settings.SOCIAL_AGENT_MAX_REWRITES:
        transition(post, Post.Status.NEEDS_HUMAN, reason="rewrite_limit")
        return post
    post.rewrite_count += 1
    post.save(update_fields=["rewrite_count", "updated_at"])
    return _run_drafting(
        post,
        material,
        purpose=LlmCall.Purpose.REWRITE,
        failed_details=f"Комментарий проверяющего: {instruction}",
    )


@transaction.atomic
def publish_scheduled_post(post: Post) -> bool:
    if not settings.SOCIAL_AGENT_ENABLED or not settings.SOCIAL_AGENT_PUBLISH_ENABLED:
        return False
    locked = Post.objects.select_for_update().select_related("channel").get(pk=post.pk)
    if locked.status != Post.Status.SCHEDULED or locked.scheduled_for > timezone.now():
        return False
    adapter_class = get_adapter(locked.channel.platform)
    if adapter_class is None:
        logger.info("No social adapter registered for platform %s", locked.channel.platform)
        return False
    previous = re.match(r"publish attempt (\d+)/", locked.failure_reason or "")
    attempt = (int(previous.group(1)) if previous else 0) + 1
    try:
        result = adapter_class().publish(locked)
    except Exception as error:
        safe_error = str(error)
        token = settings.SOCIAL_AGENT_TELEGRAM_BOT_TOKEN
        if token:
            safe_error = safe_error.replace(token, "[redacted]")
        locked.status = Post.Status.FAILED
        locked.failure_reason = f"publish attempt {attempt}/{PUBLISH_MAX_ATTEMPTS}: {safe_error}"
        locked.save(update_fields=["status", "failure_reason", "updated_at"])
        logger.warning("Social post %s publish failed (%s)", locked.pk, type(error).__name__)
        return False
    locked.external_message_id = result.external_message_id
    locked.published_at = timezone.now()
    locked.status = Post.Status.PUBLISHED
    locked.failure_reason = ""
    locked.save(
        update_fields=[
            "external_message_id",
            "published_at",
            "status",
            "failure_reason",
            "updated_at",
        ]
    )
    post.refresh_from_db()
    return True


def publish_attempts(post: Post) -> int:
    match = re.match(r"publish attempt (\d+)/", post.failure_reason or "")
    return int(match.group(1)) if match else 0
