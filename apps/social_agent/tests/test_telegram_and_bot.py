from datetime import datetime, time, timedelta
from unittest.mock import patch
from urllib.error import URLError
from zoneinfo import ZoneInfo

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.social_agent import adapters
from apps.social_agent.adapters import ChannelAdapter, PublishResult
from apps.social_agent.adapters.telegram import TelegramAdapter, TelegramError
from apps.social_agent.bot import process_updates, send_for_review
from apps.social_agent.models import BrandProfile, BotState, Channel, Post, PostCheck, Rubric, RubricSlot
from apps.social_agent.planner import plan_week
from apps.social_agent.services import publish_scheduled_post


class TelegramAdapterTests(TestCase):
    def make_post(self, text="2 < 3 & всё хорошо"):
        channel = Channel.objects.create(platform="telegram", title="Канал", external_id="@channel")
        rubric = Rubric.objects.create(slug="tg", title="TG", audience="both", source_kind="evergreen")
        return Post.objects.create(channel=channel, rubric=rubric, text=text, scheduled_for=timezone.now())

    @override_settings(SOCIAL_AGENT_TELEGRAM_BOT_TOKEN="top-secret-token")
    def test_429_uses_retry_after_and_escapes_html(self):
        responses = iter([
            {"ok": False, "error_code": 429, "parameters": {"retry_after": 3}},
            {"ok": True, "result": {"message_id": 17}},
        ])
        calls = []
        sleeps = []

        def transport(url, payload):
            calls.append((url, payload))
            return next(responses)

        result = TelegramAdapter(transport, sleep=sleeps.append, max_retries=2).publish(self.make_post())
        self.assertEqual(result.external_message_id, "17")
        self.assertEqual(sleeps, [3.0])
        self.assertEqual(calls[-1][1]["text"], "2 &lt; 3 &amp; всё хорошо")
        self.assertEqual(calls[-1][1]["parse_mode"], "HTML")

    @override_settings(SOCIAL_AGENT_TELEGRAM_BOT_TOKEN="top-secret-token")
    def test_network_errors_have_limited_retries_and_do_not_expose_token(self):
        calls = 0

        def transport(url, payload):
            nonlocal calls
            calls += 1
            raise URLError(f"failed {url}")

        with self.assertRaises(TelegramError) as caught:
            TelegramAdapter(transport, sleep=lambda _seconds: None, max_retries=2).publish(self.make_post())
        self.assertEqual(calls, 3)
        self.assertNotIn("top-secret-token", str(caught.exception))


class PublishingTests(TestCase):
    def setUp(self):
        self.original = adapters.get_adapter("telegram")
        self.calls = []
        calls = self.calls

        class FakeAdapter(ChannelAdapter):
            capabilities = {"text"}

            def publish(self, post):
                calls.append(post.pk)
                return PublishResult("message-1")

        adapters.register_adapter("telegram", FakeAdapter)
        channel = Channel.objects.create(platform="telegram", title="Канал", external_id="@test")
        rubric = Rubric.objects.create(slug="publish", title="Post", audience="both", source_kind="evergreen")
        self.post = Post.objects.create(
            channel=channel,
            rubric=rubric,
            text="Текст",
            status=Post.Status.SCHEDULED,
            scheduled_for=timezone.now() - timedelta(seconds=1),
        )

    def tearDown(self):
        adapters.register_adapter("telegram", self.original)

    @override_settings(SOCIAL_AGENT_ENABLED=True, SOCIAL_AGENT_PUBLISH_ENABLED=True)
    def test_publish_is_exactly_once_on_repeated_call(self):
        self.assertTrue(publish_scheduled_post(self.post))
        self.assertFalse(publish_scheduled_post(self.post))
        self.post.refresh_from_db()
        self.assertEqual(self.calls, [self.post.pk])
        self.assertEqual(self.post.status, Post.Status.PUBLISHED)
        self.assertEqual(self.post.external_message_id, "message-1")
        self.assertIsNotNone(self.post.published_at)

    @override_settings(SOCIAL_AGENT_ENABLED=True, SOCIAL_AGENT_PUBLISH_ENABLED=False)
    def test_publish_flag_off_sends_nothing(self):
        self.assertFalse(publish_scheduled_post(self.post))
        self.assertEqual(self.calls, [])
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, Post.Status.SCHEDULED)


class BotFlowTests(TestCase):
    def setUp(self):
        BrandProfile.objects.create(name="Матемация", evergreen_topics=["Поддержка ребёнка"])
        channel = Channel.objects.create(platform="telegram", title="Канал", external_id="@test")
        rubric = Rubric.objects.create(
            slug="review", title="Совет", audience="parents", source_kind="evergreen"
        )
        self.post = Post.objects.create(
            channel=channel,
            rubric=rubric,
            text="Поддержка ребёнка",
            status=Post.Status.NEEDS_REVIEW,
            source_ref="evergreen:0",
            scheduled_for=timezone.now() + timedelta(days=1),
        )
        PostCheck.objects.create(post=self.post, kind=PostCheck.Kind.LENGTH, passed=True, detail="ok")

    def transport_for(self, updates):
        calls = []

        def transport(url, payload):
            method = url.rsplit("/", 1)[-1]
            calls.append((method, payload))
            if method == "getUpdates":
                return {"ok": True, "result": updates}
            return {"ok": True, "result": {"message_id": 900}}

        return transport, calls

    def callback(self, action, *, user=7, chat=10, update_id=1):
        return {
            "update_id": update_id,
            "callback_query": {
                "id": f"cb-{update_id}",
                "from": {"id": user},
                "data": f"sa:{self.post.pk}:{action}",
                "message": {"message_id": 50, "chat": {"id": chat}},
            },
        }

    @override_settings(SOCIAL_AGENT_REVIEW_CHAT_IDS=[10])
    def test_review_is_sent_once_per_version(self):
        transport, calls = self.transport_for([])
        self.assertEqual(send_for_review(self.post, transport), 1)
        self.assertEqual(send_for_review(self.post, transport), 0)
        self.assertEqual([method for method, _payload in calls], ["sendMessage"])
        self.post.rewrite_count = 1
        self.post.save(update_fields=["rewrite_count"])
        self.assertEqual(send_for_review(self.post, transport), 1)

    @override_settings(
        SOCIAL_AGENT_REVIEWER_USER_IDS=[7],
        SOCIAL_AGENT_REVIEW_CHAT_IDS=[10],
        SOCIAL_AGENT_PUBLISH_ENABLED=False,
        SOCIAL_AGENT_TELEGRAM_BOT_TOKEN="top-secret-token",
    )
    def test_stranger_is_ignored(self):
        transport, calls = self.transport_for([self.callback("approve", user=99)])
        with self.assertLogs("apps.social_agent.bot", level="WARNING") as logs:
            process_updates(transport)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, Post.Status.NEEDS_REVIEW)
        self.assertEqual([method for method, _payload in calls], ["getUpdates"])
        self.assertNotIn(settings.SOCIAL_AGENT_TELEGRAM_BOT_TOKEN, "\n".join(logs.output))

    @override_settings(SOCIAL_AGENT_REVIEWER_USER_IDS=[7], SOCIAL_AGENT_REVIEW_CHAT_IDS=[10], SOCIAL_AGENT_PUBLISH_ENABLED=False)
    def test_approve_and_reject_callbacks(self):
        transport, calls = self.transport_for([self.callback("approve")])
        process_updates(transport)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, Post.Status.SCHEDULED)
        self.assertIn("answerCallbackQuery", [method for method, _payload in calls])
        self.assertIn("сухой прогон", calls[-1][1]["text"])

        second = Post.objects.create(
            channel=self.post.channel,
            rubric=self.post.rubric,
            text="Другой",
            status=Post.Status.NEEDS_REVIEW,
            scheduled_for=self.post.scheduled_for + timedelta(minutes=1),
        )
        self.post = second
        transport, _calls = self.transport_for([self.callback("reject", update_id=2)])
        process_updates(transport)
        second.refresh_from_db()
        self.assertEqual(second.status, Post.Status.REJECTED)

    @override_settings(SOCIAL_AGENT_REVIEWER_USER_IDS=[7], SOCIAL_AGENT_REVIEW_CHAT_IDS=[10], SOCIAL_AGENT_PUBLISH_ENABLED=False, SOCIAL_AGENT_MAX_REWRITES=2)
    def test_rewrite_reply_runs_pipeline(self):
        transport, _calls = self.transport_for([self.callback("rewrite")])
        process_updates(transport)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, Post.Status.REWRITING)
        reply = {
            "update_id": 2,
            "message": {
                "message_id": 51,
                "from": {"id": 7},
                "chat": {"id": 10},
                "text": "короче",
                "reply_to_message": {"message_id": 900},
            },
        }
        transport, _calls = self.transport_for([reply])
        with patch("apps.social_agent.services._send_for_review"):
            process_updates(transport)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, Post.Status.NEEDS_REVIEW)
        self.assertEqual(self.post.rewrite_count, 1)

    @override_settings(SOCIAL_AGENT_REVIEWER_USER_IDS=[7], SOCIAL_AGENT_REVIEW_CHAT_IDS=[10], SOCIAL_AGENT_MAX_REWRITES=1)
    def test_rewrite_limit_needs_human(self):
        self.post.rewrite_count = 1
        self.post.save(update_fields=["rewrite_count"])
        transport, _calls = self.transport_for([self.callback("rewrite")])
        process_updates(transport)
        reply = {
            "update_id": 2,
            "message": {
                "from": {"id": 7}, "chat": {"id": 10}, "text": "ещё раз",
                "reply_to_message": {"message_id": 900},
            },
        }
        transport, _calls = self.transport_for([reply])
        process_updates(transport)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, Post.Status.NEEDS_HUMAN)
        self.assertEqual(self.post.review_notes, "rewrite_limit")


class AcceptanceFlowTests(TestCase):
    @override_settings(
        SOCIAL_AGENT_ENABLED=True,
        SOCIAL_AGENT_PUBLISH_ENABLED=False,
        SOCIAL_AGENT_REVIEW_CHAT_IDS=[10],
        SOCIAL_AGENT_REVIEWER_USER_IDS=[7],
    )
    def test_plan_review_approve_and_single_publish(self):
        BrandProfile.objects.create(name="Матемация", evergreen_topics=["Поддержка ребёнка"])
        channel = Channel.objects.create(
            platform="telegram", title="Канал", external_id="@public", is_active=True
        )
        rubric = Rubric.objects.create(
            slug="e2e", title="Родителям", audience="parents", source_kind="evergreen"
        )
        RubricSlot.objects.create(rubric=rubric, channel=channel, weekday=1, time=time(12))
        telegram_calls = []

        def review_transport(url, payload):
            telegram_calls.append((url.rsplit("/", 1)[-1], payload))
            return {"ok": True, "result": {"message_id": 100}}

        now = datetime(2027, 1, 4, 10, tzinfo=ZoneInfo("Europe/Moscow"))
        with patch("apps.social_agent.bot.telegram_request", side_effect=lambda method, payload, transport=None: review_transport(method, payload)):
            posts = plan_week(now)
        self.assertEqual(len(posts), 1)
        self.assertEqual([name for name, _payload in telegram_calls], ["sendMessage"])

        post = posts[0]
        callback = {
            "update_id": 1,
            "callback_query": {
                "id": "approve",
                "from": {"id": 7},
                "data": f"sa:{post.pk}:approve",
                "message": {"message_id": 100, "chat": {"id": 10}},
            },
        }

        def bot_transport(url, payload):
            method = url.rsplit("/", 1)[-1]
            if method == "getUpdates":
                return {"ok": True, "result": [callback]}
            return {"ok": True, "result": {"message_id": 100}}

        process_updates(bot_transport)
        post.refresh_from_db()
        self.assertEqual(post.status, Post.Status.SCHEDULED)

        published = []

        class FakePlatformAdapter(ChannelAdapter):
            capabilities = {"text"}

            def publish(self, value):
                published.append(value.pk)
                return PublishResult("external-42")

        original = adapters.get_adapter("telegram")
        adapters.register_adapter("telegram", FakePlatformAdapter)
        try:
            post.scheduled_for = timezone.now() - timedelta(seconds=1)
            post.save(update_fields=["scheduled_for"])
            with override_settings(SOCIAL_AGENT_ENABLED=True, SOCIAL_AGENT_PUBLISH_ENABLED=True):
                self.assertTrue(publish_scheduled_post(post))
                self.assertFalse(publish_scheduled_post(post))
        finally:
            adapters.register_adapter("telegram", original)
        post.refresh_from_db()
        self.assertEqual(published, [post.pk])
        self.assertEqual(post.external_message_id, "external-42")

    def test_fake_platform_adapter_plugs_in_without_core_change(self):
        class NewPlatformAdapter(ChannelAdapter):
            capabilities = {"text", "video"}

            def publish(self, post):
                return PublishResult("new")

        adapters.register_adapter("future_platform", NewPlatformAdapter)
        try:
            self.assertIs(adapters.get_adapter("future_platform"), NewPlatformAdapter)
        finally:
            adapters._ADAPTERS.pop("future_platform", None)
