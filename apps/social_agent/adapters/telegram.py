"""Telegram Bot API adapter.

Channel post view/reaction metrics could not be verified against live Bot API
documentation in this implementation session. Phase 1 therefore relies only
on the manual ``Post.views`` and ``Post.reactions`` admin fields.
"""

from __future__ import annotations

import html
import json
import time
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from . import ChannelAdapter, PublishResult, register_adapter

Transport = Callable[[str, dict], dict]


class TelegramError(RuntimeError):
    pass


class TelegramRateLimit(TelegramError):
    def __init__(self, retry_after: float):
        super().__init__("Telegram rate limit exceeded")
        self.retry_after = max(float(retry_after), 0.0)


def _urllib_transport(url: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=35) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            return json.loads(error.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise TelegramError(f"Telegram HTTP error {error.code}") from None
    except (URLError, TimeoutError, OSError):
        raise TelegramError("Telegram network error") from None


def telegram_request(method: str, payload: dict, *, transport: Transport | None = None) -> dict:
    token = settings.SOCIAL_AGENT_TELEGRAM_BOT_TOKEN
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        response = (transport or _urllib_transport)(url, payload)
    except TelegramError:
        raise
    except Exception:
        raise TelegramError("Telegram transport error") from None
    if response.get("ok"):
        return response
    if response.get("error_code") == 429:
        retry_after = (response.get("parameters") or {}).get("retry_after", 1)
        raise TelegramRateLimit(retry_after)
    raise TelegramError(f"Telegram API error {response.get('error_code', 'unknown')}")


class TelegramAdapter(ChannelAdapter):
    capabilities = {"text"}

    def __init__(self, transport: Transport | None = None, *, sleep=None, max_retries: int = 2):
        self.transport = transport
        self.sleep = sleep or time.sleep
        self.max_retries = max(0, max_retries)

    def publish(self, post) -> PublishResult:
        payload = {
            "chat_id": post.channel.external_id,
            "text": html.escape(post.text),
            "parse_mode": "HTML",
        }
        for attempt in range(self.max_retries + 1):
            try:
                response = telegram_request("sendMessage", payload, transport=self.transport)
                return PublishResult(str(response["result"]["message_id"]))
            except TelegramRateLimit as error:
                if attempt >= self.max_retries:
                    raise TelegramError("Telegram rate limit retries exhausted") from None
                self.sleep(error.retry_after)
            except TelegramError:
                if attempt >= self.max_retries:
                    raise
                self.sleep(min(2**attempt, 5))
        raise TelegramError("Telegram publish failed")


register_adapter("telegram", TelegramAdapter)
