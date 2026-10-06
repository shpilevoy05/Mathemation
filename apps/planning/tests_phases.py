from datetime import date, timedelta

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.knowledge.tests import make_node, make_student

from .phases import CONSOLIDATION, EXAM, LEARNING, phase_for_date
from .services import build_study_plan, plan_phase


class PhaseBoundaryTests(SimpleTestCase):
    def phase(self, total_weeks, weeks_left):
        start = date(2026, 9, 1)
        exam = start + timedelta(weeks=total_weeks)
        return phase_for_date(
            start,
            exam,
            exam - timedelta(weeks=weeks_left),
            consolidation_weeks=settings.PLAN_CONSOLIDATION_WEEKS,
            exam_phase_weeks=settings.PLAN_EXAM_PHASE_WEEKS,
        )

    def test_38_week_window_stays_fixed_as_today_advances(self):
        phases = [
            self.phase(38, weeks_left)
            for weeks_left in (38, 10, 6, 3, 1)
        ]
        self.assertEqual(
            [phase.code for phase in phases],
            [LEARNING, LEARNING, CONSOLIDATION, EXAM, EXAM],
        )
        expected_start = date(2026, 9, 1) + timedelta(weeks=32)
        self.assertTrue(
            all(phase.consolidation_starts_on == expected_start for phase in phases)
        )

    def test_late_10_week_starter_has_two_week_exam_phase(self):
        self.assertEqual(self.phase(10, 3).code, LEARNING)
        phase = self.phase(10, 2)
        self.assertEqual(phase.code, EXAM)
        self.assertEqual(phase.consolidation_starts_on, phase.exam_starts_on)

    def test_without_exam_date_is_always_learning(self):
        start = date(2026, 9, 1)
        phase = phase_for_date(
            start,
            None,
            start + timedelta(days=500),
            consolidation_weeks=settings.PLAN_CONSOLIDATION_WEEKS,
            exam_phase_weeks=settings.PLAN_EXAM_PHASE_WEEKS,
        )
        self.assertEqual(phase.code, LEARNING)
        self.assertIsNone(phase.ends_on)


class PlanPhaseServiceTests(TestCase):
    def test_service_uses_first_archived_plan_as_preparation_start(self):
        student = make_student(
            "phase-service", exam_date=timezone.localdate() + timedelta(weeks=3)
        )
        first = build_study_plan(student)
        first_start = timezone.now() - timedelta(weeks=35)
        first.__class__.objects.filter(pk=first.pk).update(created_at=first_start)
        brand_new = make_node("phase-rebuild-new")
        current = build_study_plan(student)

        result = plan_phase(student)

        self.assertEqual(result["phase"], EXAM)
        self.assertEqual(result["ends_on"], student.exam_date)
        self.assertFalse(current.items.filter(node=brand_new).exists())
        self.assertGreaterEqual(current.unplanned_nodes, 1)
