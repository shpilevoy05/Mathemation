from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.content.models import Assignment, Lesson, TheoryBlock
from apps.social_agent.models import (
    BrandProfile,
    Channel,
    ContentIdea,
    Post,
    Rubric,
    SocialLessonPermission,
    SocialTaskPermission,
)
from apps.social_agent.sources import fetch_source, mark_content_idea_used


class ContentSourceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        knowledge_node = Lesson._meta.get_field("node").remote_field.model
        topic_cluster = knowledge_node._meta.get_field("cluster").remote_field.model
        cluster = topic_cluster.objects.create(title="Алгебра")
        cls.node = knowledge_node.objects.create(code="source-node", title="Тема", cluster=cluster)
        cls.channel = Channel.objects.create(platform="telegram", title="Канал", external_id="@test")

    def rubric(self, source_kind, audience=Rubric.Audience.STUDENTS, slug=None):
        return Rubric.objects.create(
            slug=slug or source_kind,
            title=source_kind,
            audience=audience,
            source_kind=source_kind,
        )

    def assignment(self, title, **overrides):
        values = {
            "title": title,
            "statement": "Сколько будет 2 + 2?",
            "correct_answer": "4",
            "reference_solution": "Складываем два слагаемых.",
            "exam_part": Assignment.Part.PART1,
        }
        values.update(overrides)
        return Assignment.objects.create(**values)

    def test_assignment_requires_permission_and_skips_recently_used(self):
        unpermitted = self.assignment("Без разрешения")
        used = self.assignment("Недавно использована")
        eligible = self.assignment("Подходит")
        SocialTaskPermission.objects.create(assignment=used)
        SocialTaskPermission.objects.create(assignment=eligible)
        rubric = self.rubric(Rubric.SourceKind.ASSIGNMENT_OF_DAY)
        Post.objects.create(
            channel=self.channel,
            rubric=rubric,
            scheduled_for=timezone.now() - timedelta(days=30),
            source_ref=f"assignment:{used.pk}",
        )

        material = fetch_source(rubric, timezone.localdate())

        self.assertEqual(material.assignment_id, eligible.pk)
        self.assertNotEqual(material.assignment_id, unpermitted.pk)
        self.assertEqual(material.facts["correct_answer"], "4")
        self.assertEqual(material.facts["reference_solution"], eligible.reference_solution)

    def test_assignment_returns_none_when_only_invalid_candidates_exist(self):
        for index, values in enumerate(
            (
                {"correct_answer": ""},
                {"reference_solution": ""},
                {"exam_part": Assignment.Part.PART2},
            )
        ):
            assignment = self.assignment(f"invalid-{index}", **values)
            SocialTaskPermission.objects.create(assignment=assignment)
        rubric = self.rubric(Rubric.SourceKind.ASSIGNMENT_OF_DAY)
        self.assertIsNone(fetch_source(rubric, date.today()))

    def test_lesson_tip_requires_published_permitted_lesson(self):
        draft = Lesson.objects.create(node=self.node, title="Черновик", status=Lesson.Status.DRAFT)
        published = Lesson.objects.create(node=self.node, title="Без разрешения", status=Lesson.Status.PUBLISHED)
        allowed = Lesson.objects.create(node=self.node, title="Разрешён", status=Lesson.Status.PUBLISHED)
        TheoryBlock.objects.create(lesson=draft, body="draft theory")
        TheoryBlock.objects.create(lesson=published, body="private theory")
        block = TheoryBlock.objects.create(lesson=allowed, title="Правило", body="public theory")
        SocialLessonPermission.objects.create(lesson=draft)
        SocialLessonPermission.objects.create(lesson=allowed)
        rubric = self.rubric(Rubric.SourceKind.LESSON_TIP)

        material = fetch_source(rubric, date.today())

        self.assertEqual(material.source_ref, f"lesson:{allowed.pk}:theory:{block.pk}")
        self.assertIn("public theory", material.reference_text)
        self.assertNotIn("private theory", material.reference_text)

    def test_exam_countdown_requires_future_date(self):
        rubric = self.rubric(Rubric.SourceKind.EXAM_COUNTDOWN)
        profile = BrandProfile.objects.create(name="Матемация")
        self.assertIsNone(fetch_source(rubric, date(2027, 1, 1)))
        profile.exam_date = date(2027, 1, 11)
        profile.save()
        self.assertEqual(fetch_source(rubric, date(2027, 1, 1)).facts["days_to_exam"], 10)
        self.assertIsNone(fetch_source(rubric, date(2027, 1, 11)))

    def test_staff_idea_is_not_marked_until_helper_is_called(self):
        rubric = self.rubric(Rubric.SourceKind.STAFF_IDEA)
        idea = ContentIdea.objects.create(title="Идея", body="Текст", audience=Rubric.Audience.STUDENTS)
        material = fetch_source(rubric, date.today())
        idea.refresh_from_db()
        self.assertIsNone(idea.used_at)
        self.assertEqual(material.content_idea_id, idea.pk)
        mark_content_idea_used(material)
        idea.refresh_from_db()
        self.assertIsNotNone(idea.used_at)

    def test_evergreen_is_for_parent_audience(self):
        BrandProfile.objects.create(name="Матемация", evergreen_topics=["  Как поддерживать ребёнка  "])
        student_rubric = self.rubric(Rubric.SourceKind.EVERGREEN, slug="student-evergreen")
        parent_rubric = self.rubric(
            Rubric.SourceKind.EVERGREEN, audience=Rubric.Audience.PARENTS, slug="parent-evergreen"
        )
        self.assertIsNone(fetch_source(student_rubric, date.today()))
        self.assertEqual(fetch_source(parent_rubric, date.today()).reference_text, "Как поддерживать ребёнка")
