from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

from apps.content.models import Assignment, Lesson, TheoryBlock

from .models import BrandProfile, ContentIdea, Post, Rubric, SocialTaskPermission


@dataclass(frozen=True)
class SourceMaterial:
    facts: dict[str, Any]
    reference_text: str
    source_ref: str
    assignment_id: int | None = None
    reveal_answer: bool = False
    content_idea_id: int | None = None


class ContentSource(ABC):
    @abstractmethod
    def fetch(self, rubric: Rubric, on_date: date) -> SourceMaterial | None:
        raise NotImplementedError


SOURCE_REGISTRY: dict[str, ContentSource] = {}


def register_source(source_kind: str, source: ContentSource) -> None:
    SOURCE_REGISTRY[source_kind] = source


def get_source(source_kind: str | Rubric) -> ContentSource | None:
    key = source_kind.source_kind if isinstance(source_kind, Rubric) else source_kind
    return SOURCE_REGISTRY.get(key)


def fetch_source(rubric: Rubric, on_date: date) -> SourceMaterial | None:
    source = get_source(rubric.source_kind)
    if source is None:
        raise ValueError(f"Unknown content source: {rubric.source_kind}")
    return source.fetch(rubric, on_date)


class AssignmentOfDaySource(ContentSource):
    def fetch(self, rubric: Rubric, on_date: date) -> SourceMaterial | None:
        cutoff = on_date - timedelta(days=60)
        recently_used = Post.objects.filter(
            source_ref__startswith="assignment:", scheduled_for__date__gte=cutoff
        ).values_list("source_ref", flat=True)
        used_ids = []
        for source_ref in recently_used:
            try:
                used_ids.append(int(source_ref.partition(":")[2]))
            except ValueError:
                continue

        permission = (
            SocialTaskPermission.objects.select_related("assignment")
            .filter(
                assignment__exam_part=Assignment.Part.PART1,
            )
            .exclude(assignment__correct_answer="")
            .exclude(assignment__reference_solution="")
            .exclude(assignment_id__in=used_ids)
            .order_by("assignment_id")
            .first()
        )
        if permission is None:
            return None
        assignment = permission.assignment
        return SourceMaterial(
            facts={
                "statement": assignment.statement,
                "correct_answer": assignment.correct_answer,
                "reference_solution": assignment.reference_solution,
            },
            reference_text=(
                f"{assignment.title}\n\n{assignment.statement}\n\n"
                f"Ответ: {assignment.correct_answer}\n\n{assignment.reference_solution}"
            ),
            source_ref=f"assignment:{assignment.pk}",
            assignment_id=assignment.pk,
        )


class LessonTipSource(ContentSource):
    def fetch(self, rubric: Rubric, on_date: date) -> SourceMaterial | None:
        block = (
            TheoryBlock.objects.select_related("lesson")
            .filter(
                lesson__status=Lesson.Status.PUBLISHED,
                lesson__social_permission__isnull=False,
            )
            .exclude(body="")
            .order_by("lesson_id", "order", "id")
            .first()
        )
        if block is None:
            return None
        return SourceMaterial(
            facts={"lesson_title": block.lesson.title, "theory_title": block.title, "theory": block.body},
            reference_text="\n\n".join(part for part in (block.lesson.title, block.title, block.body) if part),
            source_ref=f"lesson:{block.lesson_id}:theory:{block.pk}",
        )


class ExamCountdownSource(ContentSource):
    def fetch(self, rubric: Rubric, on_date: date) -> SourceMaterial | None:
        profile = BrandProfile.objects.first()
        if profile is None or profile.exam_date is None or profile.exam_date <= on_date:
            return None
        days = (profile.exam_date - on_date).days
        return SourceMaterial(
            facts={"days_to_exam": days, "exam_date": profile.exam_date.isoformat()},
            reference_text=f"До даты ЕГЭ осталось {days} дней.",
            source_ref=f"exam_countdown:{on_date.isoformat()}",
        )


class StaffIdeaSource(ContentSource):
    def fetch(self, rubric: Rubric, on_date: date) -> SourceMaterial | None:
        if rubric.audience == Rubric.Audience.BOTH:
            compatible_audiences = list(Rubric.Audience.values)
        else:
            compatible_audiences = [rubric.audience, Rubric.Audience.BOTH]
        idea = (
            ContentIdea.objects.filter(used_at__isnull=True)
            .filter(
                Q(rubric=rubric)
                | Q(rubric__isnull=True, audience__in=compatible_audiences)
            )
            .annotate(
                rubric_priority=Case(
                    When(rubric=rubric, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            )
            .order_by("rubric_priority", "id")
            .first()
        )
        if idea is None:
            return None
        return SourceMaterial(
            facts={"title": idea.title, "body": idea.body},
            reference_text="\n\n".join((idea.title, idea.body)),
            source_ref=f"idea:{idea.pk}",
            content_idea_id=idea.pk,
        )


def mark_content_idea_used(material: SourceMaterial, *, used_at=None) -> None:
    if material.content_idea_id is None:
        return
    ContentIdea.objects.filter(pk=material.content_idea_id, used_at__isnull=True).update(
        used_at=used_at or timezone.now()
    )


def material_for_post(post: Post) -> SourceMaterial | None:
    kind, separator, identifier = post.source_ref.partition(":")
    if not separator:
        return None
    if kind == "assignment":
        assignment = Assignment.objects.filter(pk=identifier).first()
        if assignment is None:
            return None
        return SourceMaterial(
            facts={
                "statement": assignment.statement,
                "correct_answer": assignment.correct_answer,
                "reference_solution": assignment.reference_solution,
            },
            reference_text=(
                f"{assignment.title}\n\n{assignment.statement}\n\n"
                f"Ответ: {assignment.correct_answer}\n\n{assignment.reference_solution}"
            ),
            source_ref=post.source_ref,
            assignment_id=assignment.pk,
        )
    if kind == "lesson":
        try:
            block_id = post.source_ref.rsplit(":", 1)[1]
        except (IndexError, ValueError):
            return None
        block = TheoryBlock.objects.select_related("lesson").filter(pk=block_id).first()
        if block is None:
            return None
        return SourceMaterial(
            facts={"lesson_title": block.lesson.title, "theory_title": block.title, "theory": block.body},
            reference_text="\n\n".join(part for part in (block.lesson.title, block.title, block.body) if part),
            source_ref=post.source_ref,
        )
    if kind == "idea":
        idea = ContentIdea.objects.filter(pk=identifier).first()
        if idea is None:
            return None
        return SourceMaterial(
            facts={"title": idea.title, "body": idea.body},
            reference_text="\n\n".join((idea.title, idea.body)),
            source_ref=post.source_ref,
            content_idea_id=idea.pk,
        )
    if kind == "evergreen":
        profile = BrandProfile.objects.first()
        try:
            topic = profile.evergreen_topics[int(identifier)]
        except (AttributeError, IndexError, TypeError, ValueError):
            return None
        return SourceMaterial(facts={"topic": topic}, reference_text=topic, source_ref=post.source_ref)
    if kind == "exam_countdown":
        profile = BrandProfile.objects.first()
        if profile is None or profile.exam_date is None:
            return None
        on_date = timezone.localtime(post.scheduled_for).date()
        days = (profile.exam_date - on_date).days
        if days <= 0:
            return None
        return SourceMaterial(
            facts={"days_to_exam": days, "exam_date": profile.exam_date.isoformat()},
            reference_text=f"До даты ЕГЭ осталось {days} дней.",
            source_ref=post.source_ref,
        )
    return None


class EvergreenSource(ContentSource):
    def fetch(self, rubric: Rubric, on_date: date) -> SourceMaterial | None:
        if rubric.audience not in {Rubric.Audience.PARENTS, Rubric.Audience.BOTH}:
            return None
        profile = BrandProfile.objects.first()
        topics = profile.evergreen_topics if profile else []
        if not isinstance(topics, list):
            return None
        topic_entry = next(
            ((index, item.strip()) for index, item in enumerate(topics) if isinstance(item, str) and item.strip()),
            None,
        )
        if topic_entry is None:
            return None
        topic_index, topic = topic_entry
        return SourceMaterial(
            facts={"topic": topic},
            reference_text=topic,
            source_ref=f"evergreen:{topic_index}",
        )


register_source(Rubric.SourceKind.ASSIGNMENT_OF_DAY, AssignmentOfDaySource())
register_source(Rubric.SourceKind.LESSON_TIP, LessonTipSource())
register_source(Rubric.SourceKind.EXAM_COUNTDOWN, ExamCountdownSource())
register_source(Rubric.SourceKind.STAFF_IDEA, StaffIdeaSource())
register_source(Rubric.SourceKind.EVERGREEN, EvergreenSource())
