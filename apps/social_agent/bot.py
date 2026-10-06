from __future__ import annotations

import html
import json
import logging
import re

from django.conf import settings

from .adapters.telegram import Transport, telegram_request
from .models import BotState, Post
from .services import rewrite_post, transition
from .sources import material_for_post

logger = logging.getLogger(__name__)
_CALLBACK = re.compile(r"^sa:(\d+):(approve|rewrite|reject)$")


def _call(method: str, payload: dict, transport: Transport | None = None) -> dict:
    return telegram_request(method, payload, transport=transport)


def _review_text(post: Post) -> str:
    checks = "\n".join(
        f"{'✅' if check.passed else '❌'} {html.escape(check.kind)}: {html.escape(check.detail)}"
        for check in post.checks.all()
    )
    return (
        f"<b>{html.escape(post.rubric.title)}</b>\n"
        f"{html.escape(post.scheduled_for.strftime('%d.%m.%Y %H:%M'))}\n\n"
        f"{html.escape(post.text)}\n\n{checks}"
    )


def send_for_review(post: Post, transport: Transport | None = None) -> int:
    sent = 0
    for chat_id in settings.SOCIAL_AGENT_REVIEW_CHAT_IDS:
        state_key = f"review_sent:{post.pk}:{post.rewrite_count}:{chat_id}"
        if BotState.objects.filter(key=state_key).exists():
            continue
        response = _call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": _review_text(post),
                "parse_mode": "HTML",
                "reply_markup": {
                    "inline_keyboard": [[
                        {"text": "Опубликовать", "callback_data": f"sa:{post.pk}:approve"},
                        {"text": "Переписать", "callback_data": f"sa:{post.pk}:rewrite"},
                        {"text": "Отклонить", "callback_data": f"sa:{post.pk}:reject"},
                    ]]
                },
            },
            transport,
        )
        BotState.objects.create(key=state_key, value=str(response["result"]["message_id"]))
        sent += 1
    return sent


def _edit_callback_message(callback: dict, text: str, transport: Transport | None) -> None:
    message = callback.get("message") or {}
    _call(
        "editMessageText",
        {
            "chat_id": (message.get("chat") or {}).get("id"),
            "message_id": message.get("message_id"),
            "text": html.escape(text),
            "parse_mode": "HTML",
        },
        transport,
    )


def _handle_callback(callback: dict, transport: Transport | None) -> bool:
    match = _CALLBACK.match(callback.get("data", ""))
    if match is None:
        return False
    user_id = (callback.get("from") or {}).get("id")
    message = callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    if user_id not in settings.SOCIAL_AGENT_REVIEWER_USER_IDS or chat_id not in settings.SOCIAL_AGENT_REVIEW_CHAT_IDS:
        logger.warning("Ignored social callback from user=%s chat=%s", user_id, chat_id)
        return False
    post = Post.objects.select_related("rubric").filter(pk=int(match.group(1))).first()
    if post is None or post.status != Post.Status.NEEDS_REVIEW:
        _call("answerCallbackQuery", {"callback_query_id": callback["id"], "text": "Пост уже обработан"}, transport)
        return True
    action = match.group(2)
    outcome = ""
    if action == "approve":
        transition(post, Post.Status.APPROVED)
        transition(post, Post.Status.SCHEDULED)
        outcome = "Одобрено и запланировано"
        if not settings.SOCIAL_AGENT_PUBLISH_ENABLED:
            outcome += " (сухой прогон: публикация выключена)"
    elif action == "reject":
        transition(post, Post.Status.REJECTED, reason="Отклонено в Telegram")
        outcome = "Отклонено"
    else:
        transition(post, Post.Status.REWRITING, reason="Ожидается комментарий")
        response = _call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "Ответьте на это сообщение коротким комментарием для переписывания.",
                "reply_to_message_id": message.get("message_id"),
            },
            transport,
        )
        BotState.objects.update_or_create(
            key=f"rewrite:{chat_id}:{user_id}",
            defaults={"value": json.dumps({
                "post_id": post.pk,
                "prompt_message_id": response["result"]["message_id"],
                "review_message_id": message.get("message_id"),
            })},
        )
        outcome = "Ожидается комментарий для переписывания"
    _call("answerCallbackQuery", {"callback_query_id": callback["id"]}, transport)
    _edit_callback_message(callback, outcome, transport)
    return True


def _handle_rewrite_reply(message: dict, transport: Transport | None) -> bool:
    user_id = (message.get("from") or {}).get("id")
    chat_id = (message.get("chat") or {}).get("id")
    if user_id not in settings.SOCIAL_AGENT_REVIEWER_USER_IDS or chat_id not in settings.SOCIAL_AGENT_REVIEW_CHAT_IDS:
        return False
    state = BotState.objects.filter(key=f"rewrite:{chat_id}:{user_id}").first()
    if state is None:
        return False
    data = json.loads(state.value)
    reply_id = ((message.get("reply_to_message") or {}).get("message_id"))
    if reply_id != data["prompt_message_id"] or not message.get("text", "").strip():
        return False
    post = Post.objects.select_related("rubric", "channel").get(pk=data["post_id"])
    material = material_for_post(post)
    if material is None:
        transition(post, Post.Status.CHECKING)
        transition(post, Post.Status.NEEDS_HUMAN, reason="source_missing")
    else:
        rewrite_post(post, material, message["text"].strip())
    state.delete()
    _call(
        "editMessageText",
        {"chat_id": chat_id, "message_id": data["review_message_id"], "text": "Переписывание обработано"},
        transport,
    )
    return True


def process_updates(transport: Transport | None = None) -> int:
    offset_state, _created = BotState.objects.get_or_create(key="last_update_id", defaults={"value": "0"})
    try:
        last_update_id = int(offset_state.value or 0)
    except ValueError:
        last_update_id = 0
    response = _call("getUpdates", {"offset": last_update_id + 1, "timeout": 25}, transport)
    processed = 0
    for update in response.get("result", []):
        if "callback_query" in update:
            _handle_callback(update["callback_query"], transport)
        elif "message" in update:
            _handle_rewrite_reply(update["message"], transport)
        offset_state.value = str(update["update_id"])
        offset_state.save(update_fields=["value"])
        processed += 1
    return processed
