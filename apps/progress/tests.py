from django.test import TestCase

from apps.knowledge.services import set_mastery
from apps.knowledge.tests import make_node, make_student
from apps.planning.services import build_study_plan
from apps.practice.models import Attempt
from apps.practice.services import submit_attempt
from apps.practice.tests import make_assignment
from apps.progress.services import build_parent_report, create_snapshot, predict_score


class ForecastTests(TestCase):
    def setUp(self):
        self.student = make_student(target_score=80)
        self.n1 = make_node("n1")
        self.n2 = make_node("n2", cluster=self.n1.cluster)

    def test_predict_score_weighted_average(self):
        set_mastery(self.student, self.n1, 100)
        set_mastery(self.student, self.n2, 0)
        predicted, avg = predict_score(self.student)
        self.assertEqual(predicted, 50)

    def test_snapshot_contains_weak_topics(self):
        set_mastery(self.student, self.n1, 90)
        set_mastery(self.student, self.n2, 10)
        snapshot = create_snapshot(self.student)
        self.assertEqual(snapshot.weak_topics[0]["code"], "n2")
        self.assertEqual(snapshot.target_score, 80)


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
        for key in ("week_fact", "dynamics", "risks", "weak_topics", "next_step"):
            self.assertIn(key, payload)
        self.assertEqual(payload["week_fact"]["attempts"], 1)
        self.assertEqual(payload["week_fact"]["solved"], 1)
        self.assertEqual(payload["dynamics"]["target_score"], 90)
        # Активность есть — риска «не было активности» быть не должно.
        self.assertNotIn("На этой неделе не было активности.", payload["risks"])

    def test_report_shows_next_step_not_blame(self):
        report = build_parent_report(self.student)
        self.assertTrue(report.payload["next_step"])
        self.assertIn("На этой неделе не было активности.", report.payload["risks"])

    def test_report_idempotent_per_week(self):
        build_parent_report(self.student)
        build_parent_report(self.student)
        self.assertEqual(self.student.parent_reports.count(), 1)
