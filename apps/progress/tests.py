from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.knowledge.services import set_mastery
from apps.knowledge.tests import make_node, make_student
from apps.planning.services import build_study_plan
from apps.practice.models import Attempt, MistakeBacklogItem
from apps.practice.services import submit_attempt
from apps.practice.tests import make_assignment
from apps.progress.services import (
    build_parent_report,
    calibrate_forecast,
    ceiling_forecast,
    create_snapshot,
    forecast_recommendations,
    platform_forecast,
    predict_score,
    primary_to_scaled,
)


class ForecastTests(TestCase):
    def setUp(self):
        self.student = make_student(target_score=80)
        self.n1 = make_node("n1")
        self.n2 = make_node("n2", cluster=self.n1.cluster)

    def test_predict_score_via_primary_table(self):
        set_mastery(self.student, self.n1, 100)
        set_mastery(self.student, self.n2, 0)
        predicted, avg = predict_score(self.student)
        # 50% mastery → 16 первичных → тестовый балл по таблице ФИПИ.
        self.assertEqual(avg, 50)
        self.assertEqual(predicted, primary_to_scaled(16))

    def test_snapshot_contains_weak_topics(self):
        set_mastery(self.student, self.n1, 90)
        set_mastery(self.student, self.n2, 10)
        snapshot = create_snapshot(self.student)
        self.assertEqual(snapshot.weak_topics[0]["code"], "n2")
        self.assertEqual(snapshot.target_score, 80)

    def test_calibration_pulls_forecast_towards_mock_fact(self):
        set_mastery(self.student, self.n1, 100)
        set_mastery(self.student, self.n2, 0)
        before, _ = predict_score(self.student)
        calibrate_forecast(self.student, actual_scaled=before - 20)
        self.assertLess(self.student.forecast_calibration, 0)
        after, _ = predict_score(self.student)
        self.assertLess(after, before)

    def test_forecast_api_stays_in_score_bounds(self):
        self.client.force_login(self.student.user)
        response = self.client.get("/api/forecast/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(0 <= response.json()["current_score"] <= 100)
        self.assertTrue(0 <= response.json()["ceiling_score"] <= 100)


class CeilingForecastTests(TestCase):
    """Потолок и «рычаги»: темп и дата двигают достижимый балл."""

    def setUp(self):
        self.student = make_student(
            weekly_hours=4, exam_date=timezone.localdate() + timedelta(days=28)
        )
        cluster = None
        self.nodes = []
        for i in range(6):
            node = make_node(f"c{i}", cluster=cluster)
            cluster = node.cluster
            self.nodes.append(node)

    def test_ceiling_above_current_and_levers_move_it(self):
        set_mastery(self.student, self.nodes[0], 80)
        slow = ceiling_forecast(self.student, weekly_hours=1)
        fast = ceiling_forecast(self.student, weekly_hours=40)
        self.assertGreaterEqual(slow["ceiling_score"], slow["current_score"])
        self.assertGreaterEqual(fast["ceiling_score"], slow["ceiling_score"])
        # При медленном темпе часть узлов честно помечена недостижимой.
        self.assertTrue(slow["unreachable_node_ids"])
        self.assertLessEqual(
            len(fast["unreachable_node_ids"]), len(slow["unreachable_node_ids"])
        )

    def test_no_exam_date_means_everything_reachable(self):
        self.student.exam_date = None
        self.student.save()
        forecast = ceiling_forecast(self.student)
        self.assertEqual(forecast["unreachable_node_ids"], [])

    def test_platform_forecast_uses_saved_student_inputs(self):
        result = platform_forecast(self.student)
        self.assertEqual(result["weekly_hours"], self.student.weekly_hours)
        self.assertEqual(result["exam_date"], self.student.exam_date)
        self.assertEqual(result["target_score"], self.student.target_score)
        self.assertGreaterEqual(result["forecast_score"], result["current_level"])

    def test_hours_needed_is_minimal_or_none(self):
        recommendations = forecast_recommendations(self.student)
        needed = recommendations["hours_needed_for_target"]
        if needed is not None:
            self.assertGreaterEqual(
                ceiling_forecast(self.student, weekly_hours=needed)["ceiling_score"],
                self.student.target_score,
            )
            if needed > 1:
                self.assertLess(
                    ceiling_forecast(self.student, weekly_hours=needed - 1)["ceiling_score"],
                    self.student.target_score,
                )

        self.student.target_score = 100
        self.student.exam_date = timezone.localdate()
        self.student.save(update_fields=["target_score", "exam_date"])
        self.assertIsNone(
            forecast_recommendations(self.student)["hours_needed_for_target"]
        )

    def test_top_topics_skip_zero_gain_and_keep_walking(self):
        self.student.target_score = 1
        self.student.save(update_fields=["target_score"])
        available = {
            node.id: {"state": "available"} for node in self.nodes
        }
        score_sequence = [50, 50, 50, 52, 50, 53, 54]
        with (
            patch("apps.knowledge.services.node_states", return_value=available),
            patch(
                "apps.planning.services.order_pending_nodes",
                return_value=self.nodes[:5],
            ),
            patch(
                "apps.progress.services._score_from_dtos",
                side_effect=score_sequence,
            ),
        ):
            topics = forecast_recommendations(self.student)["top_topics"]

        self.assertEqual(
            [topic["node_id"] for topic in topics],
            [self.nodes[1].id, self.nodes[3].id, self.nodes[4].id],
        )
        self.assertTrue(all(topic["score_gain"] > 0 for topic in topics))


class ParentReportTests(TestCase):
    def setUp(self):
        self.student = make_student(target_score=90)
        self.node = make_node()
        self.assignment = make_assignment(self.node)

    def test_report_structure(self):
        build_study_plan(self.student)
        submit_attempt(self.student, self.assignment, "42", Attempt.Context.LESSON)
        create_snapshot(self.student)
        report = build_parent_report(self.student)
        payload = report.payload
        for key in (
            "week_fact",
            "dynamics",
            "risks",
            "weak_topics",
            "error_type_distribution",
            "next_step",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["week_fact"]["attempts"], 1)
        self.assertEqual(payload["week_fact"]["solved"], 1)
        self.assertEqual(payload["dynamics"]["target_score"], 90)
        self.assertIn("platform_forecast", payload)
        self.assertIn("current_level", payload["dynamics"])
        self.assertIn("forecast_score", payload["dynamics"])
        # Активность есть — риска «не было активности» быть не должно.
        self.assertNotIn("На этой неделе не было активности.", payload["risks"])

    def test_report_shows_next_step_not_blame(self):
        report = build_parent_report(self.student)
        self.assertTrue(report.payload["next_step"])
        self.assertIn("На этой неделе не было активности.", report.payload["risks"])

    def test_report_uses_russian_plan_item_type_label(self):
        build_study_plan(self.student)
        report = build_parent_report(self.student)
        self.assertTrue(report.payload["next_step"].startswith("Урок:"))
        self.assertNotIn("Lesson:", report.payload["next_step"])

    def test_report_idempotent_per_week(self):
        build_parent_report(self.student)
        build_parent_report(self.student)
        self.assertEqual(self.student.parent_reports.count(), 1)

    def test_report_includes_error_type_distribution(self):
        MistakeBacklogItem.objects.create(
            student=self.student,
            assignment=self.assignment,
            node=self.node,
            error_type=MistakeBacklogItem.ErrorType.ARITHMETIC_SLIP,
            error_count=2,
        )
        report = build_parent_report(self.student)
        self.assertEqual(
            report.payload["error_type_distribution"]["arithmetic_slip"], 2
        )
