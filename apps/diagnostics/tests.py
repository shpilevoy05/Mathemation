from django.test import TestCase

from apps.knowledge.services import mastery_map
from apps.knowledge.tests import make_node, make_student
from apps.planning.services import get_active_plan
from apps.content.models import Assignment
from apps.practice.models import Attempt
from apps.practice.services import submit_attempt
from apps.practice.tests import make_assignment

from .models import DiagnosticResult, DiagnosticTest
from .services import complete_diagnostic, submit_diagnostic_answers


class DiagnosticFlowTests(TestCase):
    def test_diagnostic_seeds_mastery_and_builds_plan(self):
        student = make_student()
        known = make_node("known")
        unknown = make_node("unknown", cluster=known.cluster)
        a1 = make_assignment(known, answer="1")
        a2 = make_assignment(unknown, answer="2")
        test = DiagnosticTest.objects.create(title="Входная")
        test.assignments.set([a1, a2])
        result = DiagnosticResult.objects.create(student=student, test=test)

        submit_attempt(student, a1, "1", Attempt.Context.DIAGNOSTIC, diagnostic_result=result)
        submit_attempt(student, a2, "x", Attempt.Context.DIAGNOSTIC, diagnostic_result=result)
        complete_diagnostic(result)

        masteries = mastery_map(student)
        self.assertEqual(masteries[known.id], 100.0)
        # attempt processing lowered it slightly below the seeded 0 → stays low
        self.assertLess(masteries[unknown.id], 50)

        plan = get_active_plan(student)
        self.assertIsNotNone(plan)
        plan_nodes = set(plan.items.values_list("node_id", flat=True))
        self.assertIn(unknown.id, plan_nodes)
        self.assertNotIn(known.id, plan_nodes)

        student.refresh_from_db()
        self.assertIsNotNone(student.start_score)
        self.assertEqual(result.status, DiagnosticResult.Status.COMPLETED)
        self.assertEqual(result.primary_score, 1)

    def test_submit_auto_checks_only_part1(self):
        student = make_student(username="diagnostic-part1-only")
        node = make_node("diagnostic-part1")
        part1 = make_assignment(node, answer="7")
        part2 = make_assignment(
            node,
            answer="",
            part=Assignment.Part.PART2,
        )
        test = DiagnosticTest.objects.create(title="Полная диагностика")
        test.assignments.set([part1, part2])
        result = DiagnosticResult.objects.create(student=student, test=test)

        submit_diagnostic_answers(
            result,
            {str(part1.id): "7", str(part2.id): "не проверять"},
        )

        self.assertEqual(result.attempts.count(), 1)
        self.assertEqual(result.attempts.get().assignment, part1)
        self.assertEqual(result.status, DiagnosticResult.Status.COMPLETED)
