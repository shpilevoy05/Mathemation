from django.db import transaction

from .models import Post


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
