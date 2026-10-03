"""Видео занятия: подписанная ссылка, срок жизни и разрешённые хосты."""

import base64
import hashlib
import hmac
import json
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.access import Feature
from apps.knowledge.tests import make_node, make_student

from .models import Lesson
from .video import playback_link, validate_video_url

SIGNED = override_settings(
    KINESCOPE_SIGNING_KEY="video-secret", KINESCOPE_KEY_ID="key-1",
    VIDEO_LINK_TTL_SECONDS=600,
)


def decode_segment(segment: str) -> dict:
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


_node_counter = 0


def make_lesson(url="abc123", provider=Lesson.VideoProvider.KINESCOPE) -> Lesson:
    global _node_counter
    _node_counter += 1
    return Lesson.objects.create(
        node=make_node(f"video-node-{_node_counter}"), title="Урок с видео",
        video_url=url, video_provider=provider,
        status=Lesson.Status.PUBLISHED,
    )


class PlaybackLinkTests(TestCase):
    def setUp(self):
        self.student = make_student("video-student")

    def test_public_link_without_signing_key(self):
        link = playback_link(make_lesson(), self.student)

        self.assertEqual(link.url, "https://kinescope.io/embed/abc123")
        # Ключа нет — ролик публичный, и ответ обязан это признавать.
        self.assertFalse(link.is_private)

    @SIGNED
    def test_signed_link_carries_a_verifiable_token(self):
        link = playback_link(make_lesson(), self.student)

        self.assertTrue(link.is_private)
        token = parse_qs(urlsplit(link.url).query)["token"][0]
        header, payload, signature = token.split(".")
        expected = hmac.new(
            b"video-secret", f"{header}.{payload}".encode(), hashlib.sha256
        ).digest()
        self.assertEqual(
            signature,
            base64.urlsafe_b64encode(expected).rstrip(b"=").decode(),
        )
        self.assertEqual(decode_segment(header)["kid"], "key-1")

    @SIGNED
    def test_token_expires_and_names_the_viewer(self):
        link = playback_link(make_lesson(), self.student)

        claims = decode_segment(parse_qs(urlsplit(link.url).query)["token"][0].split(".")[1])
        self.assertEqual(claims["video_id"], "abc123")
        self.assertEqual(claims["sub"], str(self.student.pk))
        self.assertLessEqual(claims["exp"] - int(timezone.now().timestamp()), 600)
        self.assertGreater(claims["exp"], int(timezone.now().timestamp()))

    @SIGNED
    def test_two_issues_differ(self):
        first = playback_link(make_lesson(), self.student).url
        second = playback_link(make_lesson("abc123"), self.student).url

        # Одноразовый nonce: по нему выдача находится в логах.
        self.assertNotEqual(first, second)

    @SIGNED
    @override_settings(KINESCOPE_TOKEN_CLAIMS={"video": "vid", "expires": "expires_at"})
    def test_claim_names_follow_the_setting(self):
        link = playback_link(make_lesson(), self.student)

        claims = decode_segment(parse_qs(urlsplit(link.url).query)["token"][0].split(".")[1])
        self.assertIn("vid", claims)
        self.assertIn("expires_at", claims)

    def test_other_provider_is_used_as_is(self):
        lesson = make_lesson("https://rutube.ru/video/abc123/", Lesson.VideoProvider.RUTUBE)

        link = playback_link(lesson, self.student)

        self.assertEqual(link.url, "https://rutube.ru/video/abc123/")
        self.assertTrue(link.can_embed)

    def test_foreign_host_is_not_embeddable(self):
        lesson = make_lesson("https://evil.example/player", Lesson.VideoProvider.OTHER)

        self.assertFalse(playback_link(lesson, self.student).can_embed)


class VideoUrlValidationTests(TestCase):
    def test_foreign_host_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_video_url("https://evil.example/player")

    def test_plain_http_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_video_url("http://kinescope.io/embed/abc123")

    def test_known_host_and_bare_identifier_pass(self):
        validate_video_url("https://kinescope.io/embed/abc123")
        validate_video_url("abc123")
        validate_video_url("")

    def test_subdomain_of_allowed_host_passes(self):
        validate_video_url("https://player.kinescope.io/abc123")

    def test_lesson_clean_applies_the_rule(self):
        lesson = make_lesson("https://evil.example/player", Lesson.VideoProvider.OTHER)

        with self.assertRaises(ValidationError):
            lesson.full_clean()


class PlaybackEndpointTests(TestCase):
    def setUp(self):
        self.student = make_student("playback-student")
        self.client.force_login(self.student.user)
        self.lesson = make_lesson()

    def test_link_is_issued_to_the_student(self):
        response = self.client.get(f"/api/lessons/{self.lesson.id}/playback/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "kinescope")

    def test_draft_lesson_is_not_served(self):
        self.lesson.status = Lesson.Status.DRAFT
        self.lesson.save(update_fields=["status"])

        self.assertEqual(
            self.client.get(f"/api/lessons/{self.lesson.id}/playback/").status_code, 404
        )

    def test_lesson_without_video_is_not_served(self):
        self.lesson.video_url = ""
        self.lesson.save(update_fields=["video_url"])

        self.assertEqual(
            self.client.get(f"/api/lessons/{self.lesson.id}/playback/").status_code, 404
        )

    def test_anonymous_gets_nothing(self):
        self.client.logout()

        self.assertEqual(
            self.client.get(f"/api/lessons/{self.lesson.id}/playback/").status_code, 403
        )

    @override_settings(BILLING_ENFORCED=True, TRIAL_DAYS=0, FREE_FEATURES=[])
    def test_link_is_refused_without_subscription(self):
        response = self.client.get(f"/api/lessons/{self.lesson.id}/playback/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["feature"], Feature.LESSONS)

    def test_page_does_not_leak_the_url(self):
        response = self.client.get(f"/lesson/{self.lesson.node_id}/")

        self.assertNotContains(response, "kinescope.io")
        self.assertContains(response, f"/api/lessons/{self.lesson.id}/playback/")
