from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ParentProfile, StudentGroup, User
from apps.exams.models import ExamProfile
from apps.knowledge.models import SkillMastery
from apps.knowledge.tests import make_node, make_student

from .services import _plan_contract_cache_key, plan_contract, students_at_risk


def forecast_by_hours(multiplier=10, cap=100, unreachable=()):
    def forecast(hours):
        return {
            "ceiling_score": min(hours * multiplier, cap),
            "unreachable_node_ids": list(unreachable),
        }

    return forecast


class PlanContractTests(TestCase):
    def setUp(self):
        cache.clear()
        self.student = make_student(
            "contract-student",
            weekly_hours=4,
            target_score=80,
            exam_date=timezone.localdate() + timedelta(days=90),
        )

    def test_contract_statuses(self):
        with patch(
            "apps.progress.services._contract_ceiling_runner",
            return_value=forecast_by_hours(),
        ):
            self.student.weekly_hours = 9
            self.student.save(update_fields=["weekly_hours"])
            self.assertEqual(plan_contract(self.student)["status"], "on_track")

            self.student.weekly_hours = 4
            self.student.save(update_fields=["weekly_hours"])
            needs = plan_contract(self.student)
            self.assertEqual(needs["status"], "needs_hours")
            self.assertEqual(needs["needed_hours"], 8)
            self.assertTrue(needs["is_at_risk"])

        cache.clear()
        with patch(
            "apps.progress.services._contract_ceiling_runner",
            return_value=forecast_by_hours(multiplier=4, cap=79),
        ):
            unreachable = plan_contract(self.student)
            self.assertEqual(unreachable["status"], "unreachable")
            self.assertIsNone(unreachable["needed_hours"])
            self.assertEqual(unreachable["best_score"], 79)

    def test_no_data_without_exam_or_target(self):
        self.student.exam_date = None
        self.assertEqual(plan_contract(self.student)["status"], "no_data")
        self.assertIn("дата", plan_contract(self.student)["reason"].lower())

        self.student.exam_date = timezone.localdate() + timedelta(days=90)
        self.student.target_score = 0
        result = plan_contract(self.student)
        self.assertEqual(result["status"], "no_data")
        self.assertIn("цель", result["reason"].lower())

    def test_binary_search_matches_linear_minimum(self):
        target = self.student.target_score
        expected = next(hour for hour in range(1, 21) if hour * 10 >= target)
        simulations = Mock(side_effect=forecast_by_hours())
        with patch(
            "apps.progress.services._contract_ceiling_runner",
            return_value=simulations,
        ):
            result = plan_contract(self.student)

        self.assertEqual(result["needed_hours"], expected)
        self.assertLess(simulations.call_count, 20)

    def test_cache_hit_avoids_ceiling_recomputation(self):
        simulations = Mock(side_effect=forecast_by_hours())
        with patch(
            "apps.progress.services._contract_ceiling_runner",
            return_value=simulations,
        ) as prepare:
            first = plan_contract(self.student)
            calls_after_first = simulations.call_count
            second = plan_contract(self.student)

        self.assertEqual(second, first)
        self.assertGreater(calls_after_first, 0)
        self.assertEqual(simulations.call_count, calls_after_first)
        self.assertEqual(prepare.call_count, 1)

    def test_daily_cache_survives_mastery_updates(self):
        simulations = Mock(side_effect=forecast_by_hours())
        with patch(
            "apps.progress.services._contract_ceiling_runner",
            return_value=simulations,
        ) as prepare:
            first = plan_contract(self.student)
            node = make_node("contract-cache-mastery")
            SkillMastery.objects.create(student=self.student, node=node, mastery=70)
            second = plan_contract(self.student)

        self.assertEqual(second, first)
        self.assertEqual(prepare.call_count, 1)

    def test_contract_inputs_invalidate_cache_immediately(self):
        simulations = Mock(side_effect=forecast_by_hours())
        with patch(
            "apps.progress.services._contract_ceiling_runner",
            return_value=simulations,
        ) as prepare:
            plan_contract(self.student)
            self.student.weekly_hours += 1
            plan_contract(self.student)
            self.student.target_score -= 1
            plan_contract(self.student)
            self.student.exam_date += timedelta(days=1)
            plan_contract(self.student)

        self.assertEqual(prepare.call_count, 4)

    def test_first_request_on_a_new_day_recomputes_contract(self):
        simulations = Mock(side_effect=forecast_by_hours())
        today = timezone.localdate()
        with (
            patch(
                "apps.progress.services._contract_ceiling_runner",
                return_value=simulations,
            ) as prepare,
            patch("apps.progress.services.timezone.localdate") as localdate,
        ):
            localdate.return_value = today
            plan_contract(self.student)
            localdate.return_value = today + timedelta(days=1)
            plan_contract(self.student)

        self.assertEqual(prepare.call_count, 2)

    def test_cache_key_contains_only_daily_contract_inputs(self):
        today = timezone.localdate()
        with patch("apps.progress.services.timezone.localdate", return_value=today):
            key = _plan_contract_cache_key(self.student)

        profile = ExamProfile.active()
        self.assertEqual(
            key,
            (
                f"plan-contract:v2:{self.student.pk}:{today.isoformat()}:"
                f"{self.student.weekly_hours}:{self.student.target_score}:"
                f"{self.student.exam_date.isoformat()}:{profile.pk}"
            ),
        )

    def test_binary_search_prepares_ceiling_inputs_once(self):
        forecast = forecast_by_hours()
        simulations = Mock(side_effect=lambda _prepared, hours: forecast(hours))
        with (
            patch("apps.progress.services._prepare_ceiling", return_value={}) as prepare,
            patch(
                "apps.progress.services._simulate_prepared_ceiling",
                side_effect=simulations,
            ),
        ):
            plan_contract(self.student)

        self.assertEqual(prepare.call_count, 1)
        self.assertLess(simulations.call_count, 20)

    def test_not_taken_is_limited_and_ordered_by_exam_value(self):
        nodes = [make_node(f"contract-drop-{index}") for index in range(6)]
        values = {node.pk: float(index) for index, node in enumerate(nodes)}
        with (
            patch(
                "apps.progress.services._contract_ceiling_runner",
                return_value=forecast_by_hours(
                    unreachable=[node.pk for node in nodes]
                ),
            ),
            patch(
                "apps.planning.services.exam_values_for_nodes",
                return_value=values,
            ),
        ):
            result = plan_contract(self.student)

        self.assertEqual(
            result["not_taken"],
            [node.title for node in reversed(nodes[1:])],
        )


class RiskListTests(TestCase):
    def setUp(self):
        cache.clear()
        self.curator = User.objects.create_user("risk-curator", is_staff=True)
        self.own_high = make_student("risk-own-high")
        self.own_low = make_student("risk-own-low")
        self.inactive_group_student = make_student("risk-inactive-group")
        self.other = make_student("risk-other")
        own_group = StudentGroup.objects.create(
            title="Own", curator=self.curator, is_active=True
        )
        own_group.students.add(self.own_high, self.own_low)
        inactive_group = StudentGroup.objects.create(
            title="Inactive", curator=self.curator, is_active=False
        )
        inactive_group.students.add(self.inactive_group_student)
        other_curator = User.objects.create_user("other-curator", is_staff=True)
        other_group = StudentGroup.objects.create(
            title="Other", curator=other_curator, is_active=True
        )
        other_group.students.add(self.other)

    @staticmethod
    def contract_for(student):
        gaps = {
            "risk-own-high": 30,
            "risk-own-low": 10,
            "risk-inactive-group": 40,
            "risk-other": 50,
        }
        gap = gaps[student.user.username]
        return {
            "target_score": 80,
            "forecast_score": 80 - gap,
            "status": "needs_hours",
            "is_at_risk": True,
        }

    def test_curator_risks_are_scoped_and_sorted_by_gap(self):
        with patch(
            "apps.progress.services.plan_contract", side_effect=self.contract_for
        ):
            rows = students_at_risk(self.curator)

        self.assertEqual(
            [row["student"] for row in rows],
            [self.own_high, self.own_low],
        )

    def test_risk_page_permissions_and_curator_scope(self):
        student_user = self.own_high.user
        parent_user = User.objects.create_user("risk-parent", role=User.Role.PARENT)
        ParentProfile.objects.create(user=parent_user)
        url = reverse("studio_risks")

        for forbidden in (student_user, parent_user):
            self.client.force_login(forbidden)
            self.assertEqual(self.client.get(url).status_code, 403)

        captured = {}

        def fake_render(_request, template, context):
            captured.update({"template": template, "context": context})
            return HttpResponse("ok")

        self.client.force_login(self.curator)
        with (
            patch("apps.studio.views.render", side_effect=fake_render),
            patch(
                "apps.progress.services.plan_contract", side_effect=self.contract_for
            ),
        ):
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["template"], "studio/risks.html")
        self.assertEqual(
            [row["student"] for row in captured["context"]["rows"]],
            [self.own_high, self.own_low],
        )

    def test_risk_page_permission_matrix(self):
        url = reverse("studio_risks")
        smm = User.objects.create_user(
            "risk-smm", role=User.Role.SMM, is_staff=True
        )
        inactive_curator = User.objects.create_user(
            "risk-inactive-curator", is_staff=True
        )
        StudentGroup.objects.create(
            title="Inactive only", curator=inactive_curator, is_active=False
        )
        methodist = User.objects.create_user(
            "risk-methodist", role=User.Role.METHODIST, is_staff=True
        )
        superuser = User.objects.create_superuser(
            "risk-superuser", password="test-password"
        )

        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

        for forbidden in (smm, inactive_curator):
            self.client.force_login(forbidden)
            self.assertEqual(self.client.get(url).status_code, 403)

        with patch("apps.progress.services.students_at_risk", return_value=[]):
            for allowed in (self.curator, methodist, superuser):
                self.client.force_login(allowed)
                self.assertEqual(self.client.get(url).status_code, 200)


class ContractApiTests(TestCase):
    def test_apply_forecast_returns_contract(self):
        student = make_student(
            "contract-api",
            exam_date=timezone.localdate() + timedelta(days=90),
        )
        self.client.force_login(student.user)
        expected = {"status": "on_track", "forecast_score": 85}

        with patch("apps.progress.services.plan_contract", return_value=expected):
            response = self.client.post(
                "/api/forecast/apply/",
                {"weekly_hours": 8},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["contract"], expected)
