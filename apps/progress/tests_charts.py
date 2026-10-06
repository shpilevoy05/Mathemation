"""График динамики прогноза: геометрия считается на сервере."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.knowledge.tests import make_student

from .charts import HEIGHT, WIDTH, forecast_chart
from .models import ProgressSnapshot


def make_snapshots(student, scores):
    now = timezone.now()
    made = []
    for index, score in enumerate(scores):
        snapshot = ProgressSnapshot.objects.create(
            student=student, predicted_score=score, target_score=student.target_score
        )
        # `auto_now_add` ставит одинаковое время: разводим замеры по дням,
        # иначе подписи оси окажутся одной датой.
        ProgressSnapshot.objects.filter(pk=snapshot.pk).update(
            created_at=now - timedelta(days=len(scores) - index)
        )
        snapshot.refresh_from_db()
        made.append(snapshot)
    return made


class ChartGeometryTests(TestCase):
    def setUp(self):
        self.student = make_student("chart-student")

    def chart(self, scores, target=None):
        return forecast_chart(
            make_snapshots(self.student, scores),
            target_score=target if target is not None else self.student.target_score,
        )

    def test_empty_history_has_no_chart(self):
        chart = forecast_chart([], target_score=80)

        self.assertFalse(chart["has_data"])
        self.assertEqual(chart["points"], [])

    def test_point_per_measurement(self):
        chart = self.chart([40, 44, 51])

        self.assertEqual([point["score"] for point in chart["points"]], [40, 44, 51])
        self.assertEqual(len(chart["line"].split()), 3)

    def test_growth_goes_up_on_screen(self):
        chart = self.chart([40, 60])

        first, last = chart["points"]
        # Экран считает сверху вниз: рост балла — меньшая координата.
        self.assertLess(last["y"], first["y"])

    def test_points_stay_inside_the_plot(self):
        chart = self.chart([12, 90, 45])

        for point in chart["points"]:
            self.assertGreaterEqual(point["y"], chart["plot_top"])
            self.assertLessEqual(point["y"], chart["plot_bottom"])
            self.assertGreaterEqual(point["x"], chart["plot_left"])
            self.assertLessEqual(point["x"], chart["plot_right"])

    def test_small_growth_is_still_visible(self):
        chart = self.chart([54, 56])

        first, last = chart["points"]
        # Шкала строится по данным: рост на два балла не должен превратиться
        # в горизонтальную полку.
        self.assertGreater(first["y"] - last["y"], 30)

    def test_flat_history_does_not_divide_by_zero(self):
        chart = self.chart([50, 50, 50])

        self.assertTrue(chart["has_data"])
        self.assertEqual(len({point["y"] for point in chart["points"]}), 1)

    def test_single_measurement_draws_a_point_without_a_line(self):
        chart = self.chart([48])

        self.assertTrue(chart["single_point"])
        self.assertEqual(len(chart["points"]), 1)
        self.assertEqual(chart["area"], "")

    def test_target_inside_the_range_becomes_a_line(self):
        chart = self.chart([78, 82], target=80)

        self.assertIsNotNone(chart["target_line"])
        self.assertIn("80", chart["target_line"]["label"])
        self.assertEqual(chart["target_note"], "")

    def test_far_target_is_a_caption_not_a_squashed_scale(self):
        chart = self.chart([40, 45], target=100)

        self.assertIsNone(chart["target_line"])
        self.assertIn("100", chart["target_note"])

    def test_axis_labels_are_dates_and_scores(self):
        chart = self.chart([40, 44, 51])

        self.assertEqual(len(chart["x_labels"]), 3)
        self.assertTrue(all("." in label["label"] for label in chart["x_labels"]))
        self.assertTrue(chart["y_ticks"])
        self.assertTrue(all(tick["label"].isdigit() for tick in chart["y_ticks"]))

    def test_long_history_keeps_three_date_labels(self):
        chart = self.chart([40, 42, 44, 46, 48, 50, 52, 54])

        self.assertEqual(len(chart["points"]), 8)
        self.assertEqual(len(chart["x_labels"]), 3)

    def test_geometry_is_json_safe(self):
        import json

        json.dumps(self.chart([40, 44]))

    def test_canvas_is_fixed_and_proportional(self):
        chart = self.chart([40, 44])

        self.assertEqual((chart["width"], chart["height"]), (WIDTH, HEIGHT))


class ParentReportChartTests(TestCase):
    def test_report_carries_the_chart(self):
        from .services import build_parent_report

        student = make_student("report-chart-student")
        make_snapshots(student, [40, 47])

        report = build_parent_report(student)

        chart = report.payload["dynamics"]["chart"]
        self.assertTrue(chart["has_data"])
        self.assertGreaterEqual(len(chart["points"]), 2)
        self.assertEqual(report.payload["dynamics"]["measurements"], len(chart["points"]))
