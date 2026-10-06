from datetime import datetime, time, timedelta
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.content.models import Assignment
from apps.social_agent import adapters
from apps.social_agent.adapters import ChannelAdapter, PublishResult
from apps.social_agent.checks import CheckResult
from apps.social_agent.models import (
    BrandProfile,
    Channel,
    ContentIdea,
    LlmCall,
    Post,
    PostCheck,
    Rubric,
    RubricSlot,
)
from apps.social_agent.planner import plan_week
from apps.social_agent.providers import LlmResult
from apps.social_agent.services import can_autopublish, draft_post
from apps.social_agent.sources import SourceMaterial
from apps.social_agent.tasks import publish_due_posts


class FixedProvider:
    def __init__(self, *texts):
        self.texts = iter(texts)
        self.calls = 0

    def generate(self, messages, *, purpose, post=None):
        self.calls += 1
        return LlmResult(next(self.texts), model="fixed")


class PlannerTests(TestCase):
    def setUp(self):
        BrandProfile.objects.create(name="Матемация", evergreen_topics=["Поддерживайте ребёнка"])
        self.channel = Channel.objects.create(
            platform=Channel.Platform.TELEGRAM,
            title="Канал",
            external_id="@test",
            is_active=True,
        )

    def add_slot(self, source_kind=Rubric.SourceKind.EVERGREEN, *, slug="rubric", audience=Rubric.Audience.PARENTS):
        rubric = Rubric.objects.create(
            slug=slug,
            title="Рубрика",
            audience=audience,
            source_kind=source_kind,
            is_active=True,
        )
        RubricSlot.objects.create(
            rubric=rubric,
            channel=self.channel,
            weekday=1,
            time=time(12, 0),
        )
        return rubric

    @override_settings(SOCIAL_AGENT_ENABLED=True, SOCIAL_AGENT_PUBLISH_ENABLED=False)
    def test_plan_week_is_idempotent(self):
        self.add_slot()
        now = datetime(2027, 1, 4, 10, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        first = plan_week(now)
        second = plan_week(now)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(Post.objects.count(), 1)
        self.assertEqual(first[0].status, Post.Status.NEEDS_REVIEW)
        self.assertEqual(first[0].llm_calls.count(), 1)

    @override_settings(SOCIAL_AGENT_ENABLED=True, SOCIAL_AGENT_PUBLISH_ENABLED=False)
    def test_planner_skips_none_source_and_unpermitted_assignment(self):
        self.add_slot(
            Rubric.SourceKind.ASSIGNMENT_OF_DAY,
            slug="assignment",
            audience=Rubric.Audience.STUDENTS,
        )
        Assignment.objects.create(
            title="Без разрешения",
            statement="Условие",
            correct_answer="1",
            reference_solution="Решение",
            exam_part=Assignment.Part.PART1,
        )
        now = datetime(2027, 1, 4, 10, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        self.assertEqual(plan_week(now), [])
        self.assertFalse(Post.objects.exists())

    @override_settings(SOCIAL_AGENT_ENABLED=False)
    def test_disabled_agent_creates_nothing(self):
        self.add_slot()
        now = datetime(2027, 1, 4, 10, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        self.assertEqual(plan_week(now), [])
        self.assertFalse(Post.objects.exists())

    @override_settings(SOCIAL_AGENT_ENABLED=True, SOCIAL_AGENT_PUBLISH_ENABLED=False)
    def test_staff_idea_is_marked_used_when_post_is_created(self):
        rubric = self.add_slot(
            Rubric.SourceKind.STAFF_IDEA,
            slug="idea",
            audience=Rubric.Audience.PARENTS,
        )
        idea = ContentIdea.objects.create(
            title="Поддержка",
            body="Обсудите план занятий",
            audience=Rubric.Audience.PARENTS,
            rubric=rubric,
        )
        now = datetime(2027, 1, 4, 10, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        plan_week(now)
        idea.refresh_from_db()
        self.assertIsNotNone(idea.used_at)


class DraftPipelineTests(TestCase):
    def setUp(self):
        self.profile = BrandProfile.objects.create(name="Матемация", competitors=["Конкурент"])
        self.channel = Channel.objects.create(platform="telegram", title="Канал", external_id="@test")
        self.rubric = Rubric.objects.create(
            slug="tip",
            title="Совет",
            audience=Rubric.Audience.BOTH,
            source_kind=Rubric.SourceKind.LESSON_TIP,
        )
        self.material = SourceMaterial(facts={}, reference_text="Полезный совет", source_ref="test")

    def post(self):
        return Post.objects.create(
            channel=self.channel,
            rubric=self.rubric,
            scheduled_for=timezone.now() + timedelta(days=1),
        )

    @override_settings(SOCIAL_AGENT_MAX_REWRITES=2, SOCIAL_AGENT_PUBLISH_ENABLED=False)
    def test_failed_checks_rewrite_to_limit_then_need_human(self):
        for bad_text in ("Число 99", "Гарантируем успех", "Наш Конкурент"):
            with self.subTest(text=bad_text):
                post = self.post()
                provider = FixedProvider(bad_text, bad_text, bad_text)
                with patch("apps.social_agent.services.get_provider", return_value=provider):
                    draft_post(post, self.material)
                post.refresh_from_db()
                self.assertEqual(post.status, Post.Status.NEEDS_HUMAN)
                self.assertEqual(post.rewrite_count, 2)
                self.assertEqual(provider.calls, 3)
                self.assertEqual(post.llm_calls.filter(purpose=LlmCall.Purpose.REWRITE).count(), 2)

    @override_settings(SOCIAL_AGENT_MAX_REWRITES=2, SOCIAL_AGENT_PUBLISH_ENABLED=False)
    def test_formula_error_needs_human_without_checks(self):
        post = self.post()
        with patch("apps.social_agent.services.get_provider", return_value=FixedProvider(r"$\int_0^1 x dx$")):
            draft_post(post, self.material)
        post.refresh_from_db()
        self.assertEqual(post.status, Post.Status.NEEDS_HUMAN)
        self.assertEqual(post.review_notes, "formula_render")
        self.assertEqual(post.llm_calls.count(), 1)


class AutopublishTests(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(
            platform="telegram", title="Канал", external_id="@test", mode=Channel.Mode.AUTO_SAFE
        )
        self.rubric = Rubric.objects.create(
            slug="safe",
            title="Безопасная",
            audience=Rubric.Audience.BOTH,
            source_kind=Rubric.SourceKind.EVERGREEN,
            risk=Rubric.Risk.LOW,
            autopublish_allowed=True,
        )
        self.post = Post.objects.create(
            channel=self.channel,
            rubric=self.rubric,
            text="Полезный совет",
            scheduled_for=timezone.now() + timedelta(days=1),
        )
        self.material = SourceMaterial(facts={}, reference_text="Полезный совет", source_ref="test")
        self.checks = [CheckResult(PostCheck.Kind.LENGTH, True)]

    @override_settings(SOCIAL_AGENT_PUBLISH_ENABLED=True)
    def test_all_conditions_allow_autopublish(self):
        self.assertEqual(can_autopublish(self.post, self.checks, self.material), (True, ""))

    @override_settings(SOCIAL_AGENT_PUBLISH_ENABLED=False)
    def test_publish_flag_is_required(self):
        self.assertEqual(can_autopublish(self.post, self.checks, self.material)[1], "publish_disabled")

    @override_settings(SOCIAL_AGENT_PUBLISH_ENABLED=True)
    def test_auto_safe_channel_is_required(self):
        self.channel.mode = Channel.Mode.MANUAL
        self.assertEqual(can_autopublish(self.post, self.checks, self.material)[1], "channel_manual")

    @override_settings(SOCIAL_AGENT_PUBLISH_ENABLED=True)
    def test_safe_allowed_rubric_is_required(self):
        self.rubric.autopublish_allowed = False
        self.assertEqual(can_autopublish(self.post, self.checks, self.material)[1], "rubric_not_safe")

    @override_settings(SOCIAL_AGENT_PUBLISH_ENABLED=True)
    def test_all_checks_are_required(self):
        checks = [CheckResult(PostCheck.Kind.COMPETITOR, False)]
        self.assertEqual(can_autopublish(self.post, checks, self.material)[1], "checks_failed")

    @override_settings(SOCIAL_AGENT_PUBLISH_ENABLED=True)
    def test_number_whitelist_is_rechecked(self):
        self.post.text = "Полезный совет 42"
        self.assertEqual(can_autopublish(self.post, self.checks, self.material)[1], "number_whitelist")


class TaskAndConfigurationTests(TestCase):
    @override_settings(SOCIAL_AGENT_ENABLED=True, SOCIAL_AGENT_PUBLISH_ENABLED=False)
    def test_publish_disabled_calls_no_adapter(self):
        calls = Mock()

        class FakeAdapter(ChannelAdapter):
            capabilities = {"text"}

            def publish(self, post):
                calls(post)
                return PublishResult("1")

        adapters.register_adapter("telegram", FakeAdapter)
        try:
            channel = Channel.objects.create(platform="telegram", title="Канал", external_id="@test")
            rubric = Rubric.objects.create(
                slug="due", title="Due", audience="both", source_kind=Rubric.SourceKind.EVERGREEN
            )
            Post.objects.create(
                channel=channel,
                rubric=rubric,
                status=Post.Status.SCHEDULED,
                scheduled_for=timezone.now() - timedelta(minutes=1),
            )
            self.assertEqual(publish_due_posts(), 0)
            calls.assert_not_called()
        finally:
            adapters._ADAPTERS.pop("telegram", None)

    def test_beat_entries_and_routes_use_social_queue(self):
        from django.conf import settings

        self.assertEqual(
            settings.CELERY_BEAT_SCHEDULE["social-agent-plan-week"]["task"],
            "apps.social_agent.tasks.plan_week_task",
        )
        self.assertEqual(
            settings.CELERY_BEAT_SCHEDULE["social-agent-publish-due"]["schedule"], 60.0
        )
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["apps.social_agent.tasks.plan_week_task"]["queue"], "social"
        )
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["apps.social_agent.tasks.publish_due_posts"]["queue"], "social"
        )
