"""Календарь занятий: план, повторы и дедлайны на сетке месяца.

План уже знает, что и когда делать, но список «сегодня/на неделе» не отвечает
на вопросы «сколько занятий на следующей неделе» и «что успею до пробника».
Календарь — это тот же план, разложенный по датам, а не вторая сущность:
переносить можно только пункты плана, и перенос меняет сам план.
"""

from __future__ import annotations

from calendar import Calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.urls import reverse
from django.utils import timezone

WEEK_START = 0  # понедельник

KIND_LESSON = "lesson"
KIND_PRACTICE = "practice"
KIND_REVIEW = "review"
KIND_HOMEWORK = "homework"
KIND_EXAM = "exam"

KIND_LABELS = {
    KIND_LESSON: "Занятие",
    KIND_PRACTICE: "Практика",
    KIND_REVIEW: "Повтор",
    KIND_HOMEWORK: "Домашка",
    KIND_EXAM: "Экзамен",
}


@dataclass
class Entry:
    kind: str
    title: str
    url: str = ""
    is_done: bool = False
    plan_item_id: int | None = None

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "kind_label": KIND_LABELS.get(self.kind, self.kind),
            "title": self.title,
            "url": self.url,
            "is_done": self.is_done,
            "plan_item_id": self.plan_item_id,
            "movable": self.plan_item_id is not None and not self.is_done,
        }


@dataclass
class Day:
    date: date
    in_month: bool
    entries: list[Entry] = field(default_factory=list)

    def as_dict(self, today: date) -> dict:
        return {
            "date": self.date,
            "iso": self.date.isoformat(),
            "day": self.date.day,
            "in_month": self.in_month,
            "is_today": self.date == today,
            "is_past": self.date < today,
            "entries": [entry.as_dict() for entry in self.entries],
            # Просрочка — это не «много дел», а невыполненное вчерашнее.
            "overdue": self.date < today and any(not e.is_done for e in self.entries),
        }


def _plan_entries(student, first: date, last: date) -> dict[date, list[Entry]]:
    from .models import StudyPlanItem
    from .services import get_active_plan

    plan = get_active_plan(student)
    if plan is None:
        return {}
    entries: dict[date, list[Entry]] = {}
    items = (
        plan.items.filter(due_date__gte=first, due_date__lte=last)
        .select_related("node")
        .order_by("order")
    )
    for item in items:
        kind = KIND_LESSON if item.item_type == StudyPlanItem.ItemType.LESSON else KIND_PRACTICE
        entries.setdefault(item.due_date, []).append(
            Entry(
                kind=kind,
                title=item.node.title,
                url=reverse("lesson", args=[item.node_id]),
                is_done=item.status == StudyPlanItem.Status.DONE,
                plan_item_id=item.id,
            )
        )
    return entries


def _review_entries(student, first: date, last: date) -> dict[date, list[Entry]]:
    from apps.practice.models import ReviewSchedule

    entries: dict[date, list[Entry]] = {}
    reviews = (
        ReviewSchedule.objects.filter(
            backlog_item__student=student, due_date__gte=first, due_date__lte=last
        )
        .select_related("backlog_item__node")
    )
    for review in reviews:
        entries.setdefault(review.due_date, []).append(
            Entry(
                kind=KIND_REVIEW,
                title=review.backlog_item.node.title,
                url=reverse("practice_backlog"),
                is_done=review.status != ReviewSchedule.Status.PENDING,
            )
        )
    return entries


def _homework_entries(student, first: date, last: date) -> dict[date, list[Entry]]:
    from apps.content.models import HomeworkSubmission

    entries: dict[date, list[Entry]] = {}
    submissions = (
        HomeworkSubmission.objects.filter(student=student, homework__due_at__isnull=False)
        .select_related("homework")
    )
    for submission in submissions:
        due = timezone.localtime(submission.homework.due_at).date()
        if not (first <= due <= last):
            continue
        entries.setdefault(due, []).append(
            Entry(
                kind=KIND_HOMEWORK,
                title=submission.homework.title,
                url=reverse("homework"),
                is_done=submission.status in (
                    HomeworkSubmission.Status.SUBMITTED,
                    HomeworkSubmission.Status.CHECKED,
                ),
            )
        )
    return entries


def month_schedule(student, year: int | None = None, month: int | None = None) -> dict:
    """Сетка месяца с делами ученика."""
    today = timezone.localdate()
    year = year or today.year
    month = month or today.month
    anchor = date(year, month, 1)

    weeks = Calendar(firstweekday=WEEK_START).monthdatescalendar(year, month)
    first, last = weeks[0][0], weeks[-1][-1]

    buckets: dict[date, list[Entry]] = {}
    for source in (
        _plan_entries(student, first, last),
        _review_entries(student, first, last),
        _homework_entries(student, first, last),
    ):
        for day, entries in source.items():
            buckets.setdefault(day, []).extend(entries)

    if student.exam_date and first <= student.exam_date <= last:
        buckets.setdefault(student.exam_date, []).append(
            Entry(kind=KIND_EXAM, title="Экзамен", url="")
        )

    grid = [
        [
            Day(day, day.month == month, sorted(buckets.get(day, []), key=lambda e: e.kind)).as_dict(today)
            for day in week
        ]
        for week in weeks
    ]

    previous = (anchor - timedelta(days=1)).replace(day=1)
    following = (weeks[-1][-1] + timedelta(days=1)).replace(day=1)
    planned = sum(
        1 for week in grid for day in week
        for entry in day["entries"] if day["in_month"] and not entry["is_done"]
    )
    return {
        "year": year,
        "month": month,
        "month_start": anchor,
        "weeks": grid,
        "weekday_labels": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
        "previous": {"year": previous.year, "month": previous.month},
        "next": {"year": following.year, "month": following.month},
        "planned_count": planned,
        "exam_date": student.exam_date,
        "days_to_exam": (student.exam_date - today).days if student.exam_date else None,
    }
