"""Календарь: тот же план, разложенный по датам."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.knowledge.tests import make_node, make_student
from apps.practice.tests import make_assignment

from .models import StudyPlanItem
from .schedule import month_schedule
from .services import PlanItemMoveRefused, build_study_plan, get_active_plan, move_item


class ScheduleGridTests(TestCase):
    def setUp(self):
        self.student = make_student("schedule-student")
        self.node = make_node("schedule-node")
        make_assignment(self.node, answer="1")
        build_study_plan(self.student)
        self.today = timezone.localdate()

    def days(self, schedule):
        return [day for week in schedule["weeks"] for day in week]

    def test_grid_covers_whole_weeks_starting_on_monday(self):
        schedule = month_schedule(self.student)

        for week in schedule["weeks"]:
            self.assertEqual(len(week), 7)
        self.assertEqual(schedule["weeks"][0][0]["date"].weekday(), 0)

    def test_plan_items_land_on_their_due_date(self):
        item = get_active_plan(self.student).items.first()
        item.due_date = self.today
        item.save(update_fields=["due_date"])

        schedule = month_schedule(self.student, self.today.year, self.today.month)

        today_cell = next(day for day in self.days(schedule) if day["date"] == self.today)
        self.assertTrue(any(entry["title"] == self.node.title for entry in today_cell["entries"]))

    def test_done_item_is_marked_and_not_movable(self):
        item = get_active_plan(self.student).items.first()
        item.due_date = self.today
        item.status = StudyPlanItem.Status.DONE
        item.save(update_fields=["due_date", "status"])

        schedule = month_schedule(self.student, self.today.year, self.today.month)
        cell = next(day for day in self.days(schedule) if day["date"] == self.today)
        entry = cell["entries"][0]

        self.assertTrue(entry["is_done"])
        self.assertFalse(entry["movable"])

    def test_exam_day_is_on_the_calendar(self):
        self.student.exam_date = self.today + timedelta(days=3)
        self.student.save(update_fields=["exam_date"])

        schedule = month_schedule(self.student, self.today.year, self.today.month)
        cell = next(
            day for day in self.days(schedule) if day["date"] == self.student.exam_date
        )

        self.assertIn("exam", [entry["kind"] for entry in cell["entries"]])

    def test_month_navigation_wraps_the_year(self):
        schedule = month_schedule(self.student, 2027, 1)

        self.assertEqual(schedule["previous"], {"year": 2026, "month": 12})
        self.assertEqual(schedule["next"], {"year": 2027, "month": 2})

    def test_student_without_plan_gets_an_empty_grid(self):
        other = make_student("no-plan-schedule")

        schedule = month_schedule(other)

        self.assertTrue(schedule["weeks"])
        self.assertEqual(schedule["planned_count"], 0)


class MoveItemTests(TestCase):
    def setUp(self):
        self.student = make_student("move-student")
        self.node = make_node("move-node")
        make_assignment(self.node, answer="1")
        build_study_plan(self.student)
        self.item = get_active_plan(self.student).items.first()
        self.today = timezone.localdate()

    def test_move_changes_the_plan(self):
        target = self.today + timedelta(days=5)

        move_item(self.item, target)

        self.item.refresh_from_db()
        self.assertEqual(self.item.due_date, target)

    def test_move_into_the_past_is_refused(self):
        with self.assertRaises(PlanItemMoveRefused):
            move_item(self.item, self.today - timedelta(days=1))

    def test_move_past_the_exam_is_refused(self):
        self.student.exam_date = self.today + timedelta(days=10)
        self.student.save(update_fields=["exam_date"])

        with self.assertRaises(PlanItemMoveRefused):
            move_item(self.item, self.today + timedelta(days=11))

    def test_done_item_does_not_move(self):
        self.item.status = StudyPlanItem.Status.DONE
        self.item.save(update_fields=["status"])

        with self.assertRaises(PlanItemMoveRefused):
            move_item(self.item, self.today + timedelta(days=2))

    def test_move_is_written_to_the_plan_log(self):
        from .models import PlanChangeLog

        move_item(self.item, self.today + timedelta(days=4))

        self.assertTrue(
            PlanChangeLog.objects.filter(
                plan__student=self.student, reason=PlanChangeLog.Reason.MANUAL
            ).exists()
        )


class MoveApiTests(TestCase):
    def setUp(self):
        self.student = make_student("move-api-student")
        self.node = make_node("move-api-node")
        make_assignment(self.node, answer="1")
        build_study_plan(self.student)
        self.item = get_active_plan(self.student).items.first()
        self.client.force_login(self.student.user)

    def post(self, value):
        return self.client.post(
            f"/api/plan/items/{self.item.id}/move/",
            {"due_date": value}, content_type="application/json",
        )

    def test_move_returns_the_updated_item(self):
        target = (timezone.localdate() + timedelta(days=2)).isoformat()

        response = self.post(target)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["due_date"], target)

    def test_broken_date_is_a_bad_request(self):
        self.assertEqual(self.post("вчера").status_code, 400)

    def test_refused_move_is_a_conflict(self):
        past = (timezone.localdate() - timedelta(days=3)).isoformat()

        self.assertEqual(self.post(past).status_code, 409)

    def test_someone_elses_item_is_not_found(self):
        other = make_student("other-move-student")
        self.client.force_login(other.user)

        self.assertEqual(self.post(timezone.localdate().isoformat()).status_code, 404)
