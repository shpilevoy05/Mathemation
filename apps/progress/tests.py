from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import StudentProfile
from apps.knowledge.services import set_mastery
from apps.knowledge.tests import make_node, make_student
from apps.planning.services import build_study_plan
from apps.practice.models import Attempt, MistakeBacklogItem
from apps.practice.services import submit_attempt
from apps.practice.tests import make_assignment
from apps.progress.services import (
    build_parent_report,
    calibrate_forecast,
    calibration_report,
    ceiling_forecast,
    create_snapshot,
    expected_primary,
    forecast_breakdown,
    forecast_interval,
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
        calibrate_forecast(self.student, actual_primary=expected_primary(self.student) - 6)
        self.assertLess(self.student.primary_calibration, 0)
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


class ExamProfileForecastTests(TestCase):
    """Прогноз считается по профилю экзамена, а не по составу банка задач."""

    def setUp(self):
        from apps.exams.models import ExamProfile, ExamTask, ExamTaskSkill

        self.student = make_student("profile-student")
        self.part1_node = make_node("p1")
        self.part2_node = make_node("p2", cluster=self.part1_node.cluster, exam_part=2)
        self.profile = ExamProfile.objects.create(
            year=2027, title="ЕГЭ (тест)", max_primary_score=6,
            primary_to_scaled=[min(100, i * 10) for i in range(7)], is_active=True,
        )
        first = ExamTask.objects.create(
            profile=self.profile, number=1, exam_part=1, max_score=1, difficulty=2
        )
        second = ExamTask.objects.create(
            profile=self.profile, number=2, exam_part=1, max_score=1, difficulty=2
        )
        third = ExamTask.objects.create(
            profile=self.profile, number=3, exam_part=2, max_score=4, difficulty=4
        )
        ExamTaskSkill.objects.create(task=first, node=self.part1_node)
        ExamTaskSkill.objects.create(task=second, node=self.part1_node)
        ExamTaskSkill.objects.create(task=third, node=self.part2_node)

    def test_bank_content_no_longer_moves_the_forecast(self):
        set_mastery(self.student, self.part1_node, 60)
        before = expected_primary(self.student)
        for index in range(10):
            easy = make_assignment(self.part1_node, answer=str(index))
            easy.difficulty = 1
            easy.save(update_fields=["difficulty"])
        self.assertEqual(expected_primary(self.student), before)

    def test_part2_task_weighs_four_times_a_part1_task(self):
        set_mastery(self.student, self.part1_node, 100)
        set_mastery(self.student, self.part2_node, 0)
        part1_only = expected_primary(self.student)
        set_mastery(self.student, self.part1_node, 0)
        set_mastery(self.student, self.part2_node, 100)
        self.assertGreater(expected_primary(self.student), part1_only)

    def test_primary_never_exceeds_profile_maximum(self):
        set_mastery(self.student, self.part1_node, 100)
        set_mastery(self.student, self.part2_node, 100)
        self.assertLessEqual(expected_primary(self.student), 6)

    def test_breakdown_sums_to_expected_primary(self):
        set_mastery(self.student, self.part1_node, 70)
        set_mastery(self.student, self.part2_node, 55)
        breakdown = forecast_breakdown(self.student)
        self.assertEqual(len(breakdown), 3)
        total = sum(item["expected_points"] for item in breakdown)
        self.assertAlmostEqual(expected_primary(self.student), total, delta=0.05)

    def test_conversion_table_comes_from_the_profile(self):
        self.assertEqual(primary_to_scaled(3), 30)

    def test_unmapped_task_contributes_nothing_and_is_reported(self):
        from apps.exams.models import ExamTask
        from apps.progress.services import profile_coverage

        set_mastery(self.student, self.part1_node, 80)
        before = expected_primary(self.student)
        ExamTask.objects.create(
            profile=self.profile, number=4, exam_part=2, max_score=4, difficulty=5
        )
        self.assertEqual(expected_primary(self.student), before)

        coverage = profile_coverage()
        self.assertEqual(coverage["unmapped_numbers"], [4])
        self.assertEqual(coverage["unmapped_score"], 4)
        item = next(i for i in forecast_breakdown(self.student) if i["number"] == 4)
        self.assertEqual(item["expected_points"], 0)
    def test_forecast_is_monotone_in_mastery(self):
        scores = []
        for mastery in (0, 20, 40, 60, 80, 100):
            set_mastery(self.student, self.part1_node, mastery)
            set_mastery(self.student, self.part2_node, mastery)
            scores.append(predict_score(self.student)[0])
        self.assertEqual(scores, sorted(scores))


class DemoProfileCoverageTests(TestCase):
    """Демо-граф должен покрывать весь профиль экзамена.

    Дырка в разметке молча занижает прогноз, поэтому она ловится тестом, а не
    глазами методиста.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def test_every_exam_task_is_mapped_to_a_node(self):
        from apps.progress.services import profile_coverage

        coverage = profile_coverage()

        self.assertEqual(coverage["unmapped_numbers"], [])
        self.assertEqual(coverage["mapped"], coverage["tasks"])
        self.assertEqual(coverage["unmapped_score"], 0)

    def test_full_mastery_reaches_the_maximum_primary_score(self):
        from apps.knowledge.models import KnowledgeNode
        from apps.progress.services import max_primary_score

        student = StudentProfile.objects.get(user__username="student")
        for node in KnowledgeNode.objects.all():
            set_mastery(student, node, 100)

        # 2PL никогда не даёт единицу: даже при mastery 100 сложные задания
        # второй части остаются вероятностными. Важно, что все 19 номеров
        # вносят вклад — потолок ~80% первичного балла, а не 60%.
        self.assertGreater(expected_primary(student), 0.8 * max_primary_score())


class CalibrationTests(TestCase):
    """Калибровка живёт в первичных баллах и даёт интервал."""

    def setUp(self):
        self.student = make_student("calibration-student")
        self.node = make_node("cal-node")
        make_assignment(self.node)

    def test_observation_is_recorded_in_primary_points(self):
        observation = calibrate_forecast(self.student, actual_primary=12)
        self.assertEqual(observation.actual_primary, 12)
        self.assertEqual(self.student.calibration_samples, 1)
        self.assertEqual(
            observation.error, round(12 - observation.predicted_primary, 2)
        )

    def test_stable_error_converges_and_narrows_the_interval(self):
        set_mastery(self.student, self.node, 60)
        raw = expected_primary(self.student)
        wide = forecast_interval(self.student)
        for _ in range(6):
            calibrate_forecast(self.student, actual_primary=raw - 4)
        narrow = forecast_interval(self.student)
        self.assertAlmostEqual(self.student.primary_calibration, -4, delta=1.5)
        self.assertLess(narrow["sigma_primary"], wide["sigma_primary"])

    def test_unstable_results_keep_the_interval_wide(self):
        raw = expected_primary(self.student)
        for delta in (6, -6, 6, -6):
            calibrate_forecast(self.student, actual_primary=raw + delta)
        self.assertGreater(forecast_interval(self.student)["sigma_primary"], 3)

    def test_interval_brackets_the_point_forecast(self):
        interval = forecast_interval(self.student)
        self.assertLessEqual(interval["low_scaled"], interval["scaled"])
        self.assertGreaterEqual(interval["high_scaled"], interval["scaled"])
        self.assertGreaterEqual(interval["low_scaled"], 0)
        self.assertLessEqual(interval["high_scaled"], 100)

    def test_calibration_cannot_push_the_score_out_of_bounds(self):
        calibrate_forecast(self.student, actual_primary=1000)
        self.assertLessEqual(predict_score(self.student)[0], 100)

    def test_report_summarises_errors(self):
        raw = expected_primary(self.student)
        calibrate_forecast(self.student, actual_primary=raw + 2)
        calibrate_forecast(self.student, actual_primary=raw - 2)
        report = calibration_report(self.student)
        self.assertEqual(report["samples"], 2)
        self.assertGreater(report["mean_absolute_error"], 0)


class NodeHoursTests(TestCase):
    """Часы на узел: потолок и планировщик считают реальную стоимость темы."""

    def setUp(self):
        self.student = make_student(
            "hours-student", weekly_hours=4,
            exam_date=timezone.localdate() + timedelta(days=28),
        )
        self.cheap = make_node("cheap-node", weight=3.0, hours_estimate=2)
        self.expensive = make_node(
            "expensive-node", cluster=self.cheap.cluster, weight=2.0, hours_estimate=40
        )

    def test_part2_node_costs_more_by_default(self):
        part1 = make_node("light-node", cluster=self.cheap.cluster, exam_part=1)
        part2 = make_node("heavy-node", cluster=self.cheap.cluster, exam_part=2)
        self.assertGreater(part2.effective_hours, part1.effective_hours)

    def test_explicit_estimate_wins_over_the_part_default(self):
        node = make_node("tuned-node", cluster=self.cheap.cluster, hours_estimate=9.5)
        self.assertEqual(node.effective_hours, 9.5)

    def test_expensive_node_does_not_fit_the_budget(self):
        forecast = ceiling_forecast(self.student)
        self.assertIn(self.cheap.id, forecast["reachable_node_ids"])
        self.assertIn(self.expensive.id, forecast["unreachable_node_ids"])

    def test_more_hours_never_shrink_the_reachable_set(self):
        previous = None
        for weekly_hours in (1, 4, 10, 40, 100):
            count = len(
                ceiling_forecast(self.student, weekly_hours=weekly_hours)["reachable_node_ids"]
            )
            if previous is not None:
                self.assertGreaterEqual(count, previous)
            previous = count
