from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.social_agent import adapters
from apps.social_agent.adapters import ChannelAdapter, PublishResult
from apps.social_agent.models import BrandProfile, Channel, Post, Rubric
from apps.social_agent.services import InvalidTransition, TRANSITIONS, transition


class ModelValidationTests(TestCase):
    def test_brand_profile_is_singleton(self):
        BrandProfile.objects.create(name="Матемация")
        with self.assertRaises(ValidationError):
            BrandProfile.objects.create(name="Другой профиль")

    def test_high_risk_rubric_cannot_autopublish(self):
        rubric = Rubric(slug="risk", title="Риск", audience="both", source_kind="evergreen", risk="high", autopublish_allowed=True)
        with self.assertRaises(ValidationError):
            rubric.clean()

    def test_channel_requires_registered_adapter(self):
        channel = Channel(platform="youtube", title="Канал", external_id="@test", is_active=True)
        with self.assertRaises(ValidationError):
            channel.clean()

        class FakeAdapter(ChannelAdapter):
            capabilities = {"text"}

            def publish(self, post):
                return PublishResult("1")

        adapters.register_adapter("youtube", FakeAdapter)
        try:
            channel.clean()
            self.assertIs(adapters.get_adapter("youtube"), FakeAdapter)
        finally:
            adapters._ADAPTERS.pop("youtube", None)

    def test_telegram_adapter_is_registered_by_app_startup(self):
        self.assertIsNotNone(adapters.get_adapter("telegram"))


class TransitionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.channel = Channel.objects.create(platform="telegram", title="Канал", external_id="@test")
        cls.rubric = Rubric.objects.create(slug="tips", title="Советы", audience="both", source_kind="evergreen", risk="low")

    def make_post(self, status):
        return Post.objects.create(channel=self.channel, rubric=self.rubric, status=status, scheduled_for=timezone.now())

    def test_every_allowed_transition(self):
        for source, targets in TRANSITIONS.items():
            for target in targets:
                with self.subTest(source=source, target=target):
                    post = self.make_post(source)
                    transition(post, target, reason="test")
                    self.assertEqual(post.status, target)

    def test_representative_forbidden_transitions(self):
        for source, target in (("draft", "published"), ("needs_human", "published"), ("published", "scheduled"), ("rejected", "approved")):
            with self.subTest(source=source, target=target):
                with self.assertRaises(InvalidTransition):
                    transition(self.make_post(source), target)
