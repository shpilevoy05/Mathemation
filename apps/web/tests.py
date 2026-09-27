from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.ai_mentor.models import AiHintMessage, AiHintSession
from apps.content.models import Assignment, Lesson
from apps.diagnostics.models import DiagnosticResult, DiagnosticTest
from apps.expert_review.models import ExpertReviewRequest
from apps.mocks.models import MockExam
from apps.planning.models import StudyPlanItem, Trajectory, TrajectoryTransition
from apps.planning.services import get_active_plan
from apps.practice.models import MistakeBacklogItem
from apps.progress.models import ProgressSnapshot
from apps.knowledge.models import KnowledgeDependency, KnowledgeNode, TopicCluster
from apps.knowledge.services import set_mastery
from apps.knowledge.tests import make_node, make_student

from .services import (
    _track_point,
    gauge_metrics,
    journey_percent,
    track_context,
    xp_progress_percent,
)


class DashboardMetricServiceTests(SimpleTestCase):
    def test_gauge_journey_and_xp_percentages_are_prepared_in_services(self):
        self.assertEqual(gauge_metrics(50)["offset"], "125.60")
        self.assertEqual(journey_percent(60, 80, 60), 100)
        self.assertEqual(journey_percent(60, 40, 60), 0)
        self.assertEqual(xp_progress_percent(250, 2), 50)


class CabinetCssRegressionTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
            encoding="utf-8"
        )

    def test_mobile_header_disables_backdrop_filter(self):
        mobile_css = self.css.split("@media (max-width: 720px)", 1)[1]
        self.assertIn("backdrop-filter: none", mobile_css)
        self.assertIn("-webkit-backdrop-filter: none", mobile_css)

    def test_chip_inputs_are_bounded_and_have_visible_keyboard_focus(self):
        self.assertIn(".chip-toggle { position: relative; }", self.css)
        self.assertIn("width: 1px; height: 1px", self.css)
        self.assertIn(".chip-toggle input:focus-visible + span", self.css)

    def test_forecast_cards_align_to_top_and_target_button_does_not_wrap(self):
        self.assertIn("align-items: start", self.css)
        self.assertIn(".target-score-form button { white-space: nowrap; }", self.css)

    def test_parent_gauge_caption_is_readable_below_the_svg(self):
        self.assertIn(".gauge-wrap .gauge-caption-text", self.css)
        self.assertIn("font-size: 12px", self.css)

    def test_learning_track_has_desktop_grid_and_mobile_path_rules(self):
        self.assertIn(
            "grid-template-columns: minmax(0, 1fr) 340px", self.css
        )
        self.assertIn(".track-sidebar { position: sticky; top: 88px", self.css)
        self.assertIn(
            ".track-layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 40px; align-items: start; }",
            self.css,
        )
        self.assertNotIn(".track-layout { padding-bottom", self.css)
        self.assertIn(
            ".track-column { min-width: 0; padding-bottom: 120px;", self.css
        )
        self.assertIn("max-height: calc(100vh - 88px - 72px)", self.css)
        self.assertIn("overflow-y: auto", self.css)
        self.assertIn("scrollbar-width: thin", self.css)
        self.assertIn("@media (max-width: 1023px)", self.css)
        self.assertIn(".track-sidebar { display: none; }", self.css)
        self.assertIn(
            ".track-unit-notes { justify-content: center; width: 44px; height: 44px; padding: 0; }",
            self.css,
        )
        self.assertEqual(
            self.css.count(
                ".track-unit-header .track-unit-notes span { font-size: 22px; line-height: 1; }"
            ),
            2,
        )
        self.assertIn(".track-unit { --offset-scale: .75; }", self.css)
        self.assertNotIn(".track-pos-", self.css)


class ForecastJavascriptRegressionTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.javascript = (
            Path(settings.BASE_DIR) / "static" / "js" / "app.js"
        ).read_text(encoding="utf-8")

    def test_neutral_delta_and_saved_button_state_are_explicit(self):
        self.assertIn('"= прогнозу платформы"', self.javascript)
        self.assertIn("forecastRoot.dataset.savedHours = String(data.weekly_hours)", self.javascript)
        self.assertIn("saveButton.disabled = true", self.javascript)
        self.assertIn("success.textContent = data.schedule_summary", self.javascript)

    def test_track_module_handles_popovers_escape_and_current_jump(self):
        self.assertIn('document.querySelector("[data-learning-track]")', self.javascript)
        self.assertIn('event.key === "Escape"', self.javascript)
        self.assertIn('aria-expanded", "true"', self.javascript)
        self.assertIn('behavior: "auto"', self.javascript)
        self.assertIn('behavior: "smooth"', self.javascript)
        self.assertIn("IntersectionObserver", self.javascript)


class BackofficeCabinetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.student = User.objects.get(username="student")
        cls.expert = User.objects.get(username="expert")
        cls.methodist = User.objects.get(username="methodist")
        cls.review = ExpertReviewRequest.objects.get(
            status=ExpertReviewRequest.Status.SUBMITTED
        )
        ExpertReviewRequest.objects.filter(pk=cls.review.pk).update(
            created_at=timezone.now() - timedelta(hours=cls.review.sla_hours + 1)
        )
        cls.superuser = User.objects.create_superuser(
            username="root-reviewer", password="test"
        )
        cls.staff = User.objects.create_user(
            username="staff-reviewer", password="test", is_staff=True
        )

    def test_backoffice_pages_redirect_anonymous_user(self):
        for url in (reverse("expert_queue"), reverse("methodist_dashboard")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)

    def test_expert_access_and_other_roles_get_placeholder(self):
        self.client.force_login(self.expert)
        response = self.client.get(reverse("expert_queue"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "В очереди")
        self.assertContains(response, self.review.assignment.title)
        self.assertContains(response, "просрочено")

        for user in (self.student, self.methodist):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("expert_queue"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Кабинет эксперта недоступен")
                self.assertNotContains(response, self.review.assignment.title)

    def test_methodist_access_and_expert_gets_placeholder(self):
        self.client.force_login(self.methodist)
        response = self.client.get(reverse("methodist_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Дыры контента")

        self.client.force_login(self.expert)
        response = self.client.get(reverse("methodist_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Кабинет методиста недоступен")
        self.assertNotContains(response, "Граф по кластерам")

    def test_superuser_sees_both_backoffice_pages(self):
        self.client.force_login(self.superuser)
        self.assertContains(self.client.get(reverse("expert_queue")), "В очереди")
        self.assertContains(
            self.client.get(reverse("methodist_dashboard")), "Граф по кластерам"
        )

    def test_dashboard_redirects_each_non_student_role(self):
        cases = (
            (self.expert, reverse("expert_queue")),
            (self.methodist, reverse("methodist_dashboard")),
            (User.objects.get(username="parent"), reverse("parent_dashboard")),
            (self.staff, reverse("admin:index")),
            (self.superuser, reverse("admin:index")),
        )
        for user, expected_url in cases:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("dashboard"))
                self.assertRedirects(response, expected_url, fetch_redirect_response=False)

    def test_dashboard_without_profile_or_backoffice_role_renders_empty_state(self):
        user = User.objects.create_user(username="profileless-user")
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Кабинет ученика недоступен")

    def test_review_page_contains_criteria_and_error_type_chips(self):
        self.client.force_login(self.expert)
        response = self.client.get(reverse("expert_review", args=[self.review.id]))
        self.assertEqual(response.status_code, 200)
        for number in range(1, self.review.assignment.max_score + 1):
            self.assertContains(response, f"К{number}")
        self.assertContains(response, "неверный метод")
        self.assertNotContains(response, "тип уточняется")

    def test_methodist_lists_assignment_without_reference_solution(self):
        gap = Assignment.objects.create(
            title="Задача без эталона",
            statement="Условие",
            exam_part=Assignment.Part.PART2,
        )
        self.client.force_login(self.methodist)
        response = self.client.get(reverse("methodist_dashboard"))
        self.assertContains(response, gap.title)
        self.assertContains(
            response, f"/admin/content/assignment/{gap.id}/change/"
        )


class TrackContextTests(TestCase):
    def test_offsets_mirror_and_exactly_one_current_point_is_prepared(self):
        student = make_student(username="track-context-student")
        cluster = TopicCluster.objects.create(
            title="Тестовый кластер", color="#3D6BE5", order=0
        )
        mirrored_cluster = TopicCluster.objects.create(
            title="Зеркальный кластер", color="#58CC02", order=1
        )
        mastered = make_node("track-mastered", cluster=cluster, order=0)
        prerequisite = make_node("track-prerequisite", cluster=cluster, order=1)
        locked = make_node("track-locked", cluster=cluster, order=2)
        mirrored_nodes = [
            make_node(f"track-mirrored-{index}", cluster=mirrored_cluster, order=index)
            for index in range(2)
        ]
        KnowledgeDependency.objects.create(
            node=locked, prerequisite=prerequisite, min_mastery=70
        )
        for node in (mastered, prerequisite, locked, *mirrored_nodes):
            Lesson.objects.create(node=node, title=f"Урок: {node.title}")
        set_mastery(student, mastered, 90)
        set_mastery(student, prerequisite, 20)

        context = track_context(student)
        first_unit, second_unit = context["track_units"][:2]
        points = first_unit["points"]

        self.assertEqual(
            [point["offset_px"] for point in points], [0, 44, 70, 44, 0, -44]
        )
        self.assertEqual(
            [point["offset_px"] for point in second_unit["points"]],
            [0, -44, -70, -44],
        )
        self.assertFalse(first_unit["mirrored"])
        self.assertTrue(second_unit["mirrored"])
        current_points = [
            point
            for unit in context["track_units"]
            for point in unit["points"]
            if point["is_current"]
        ]
        self.assertEqual(len(current_points), 1)
        self.assertIs(context["current_point"], current_points[0])
        self.assertEqual(current_points[0]["cta_label"], "ПРОДОЛЖИТЬ")

    def test_cta_icons_and_locked_conditions_are_prepared(self):
        student = make_student(username="track-state-student")
        cluster = TopicCluster.objects.create(title="Состояния", color="#3D6BE5")
        mastered = make_node("state-mastered", cluster=cluster, order=0)
        prerequisite = make_node("state-prerequisite", cluster=cluster, order=1)
        locked = make_node("state-locked", cluster=cluster, order=2)
        KnowledgeDependency.objects.create(
            node=locked, prerequisite=prerequisite, min_mastery=70
        )
        for node in (mastered, prerequisite, locked):
            Lesson.objects.create(node=node, title=f"Урок: {node.title}")
        set_mastery(student, mastered, 90)

        points = track_context(student)["track_units"][0]["points"]
        mastered_points = [point for point in points if point["node_id"] == mastered.id]
        self.assertTrue(all(point["is_done"] for point in mastered_points))
        self.assertTrue(all(point["icon"] == "check" for point in mastered_points))
        self.assertTrue(
            all(point["cta_label"] == "ПОВТОРИТЬ" for point in mastered_points)
        )
        available_point = next(
            point for point in points if point["node_id"] == prerequisite.id
        )
        self.assertEqual(available_point["cta_label"], "НАЧАТЬ")
        locked_point = next(
            point for point in points if point["node_id"] == locked.id
        )
        self.assertEqual(locked_point["visual_state"], "locked")
        self.assertEqual(locked_point["cta_label"], "ЗАКРЫТО")
        self.assertIsNone(locked_point["url"])
        condition = locked_point["popover_conditions"][0]
        self.assertEqual(condition["title"], prerequisite.title)
        self.assertEqual(condition["current"], 0)
        self.assertEqual(condition["required"], 70)
        self.assertEqual(condition["percent"], 0)

    def test_special_point_ctas_and_icons(self):
        cases = (
            ("review", "available", "К ОТРАБОТКЕ", "review"),
            ("mock", "available", "К ПРОБНИКУ", "mock"),
            ("practice", "decayed", "ПОВТОРИТЬ", "review"),
        )
        for point_type, state, cta, icon in cases:
            with self.subTest(point_type=point_type, state=state):
                point = _track_point(
                    point_type,
                    "Точка",
                    {"state": state, "mastery": 40, "unmet_conditions": []},
                    node_id=1,
                )
                self.assertEqual(point["cta_label"], cta)
                self.assertEqual(point["icon"], icon)


class StudentCabinetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.user = User.objects.get(username="student")
        cls.node = KnowledgeNode.objects.get(code="frac-powers")

    def setUp(self):
        self.client.force_login(self.user)

    def test_every_student_page_returns_200(self):
        urls = [
            reverse("dashboard"),
            reverse("knowledge_map"),
            reverse("knowledge_node", args=[self.node.id]),
            reverse("track"),
            reverse("lesson", args=[self.node.id]),
            reverse("practice_backlog"),
            reverse("forecast"),
            reverse("diagnostic"),
            reverse("mocks"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_every_student_page_redirects_anonymous_user(self):
        self.client.logout()
        urls = [
            reverse("dashboard"),
            reverse("knowledge_map"),
            reverse("knowledge_node", args=[self.node.id]),
            reverse("track"),
            reverse("lesson", args=[self.node.id]),
            reverse("practice_backlog"),
            reverse("forecast"),
            reverse("diagnostic"),
            reverse("mocks"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)

    def test_dashboard_contains_named_trajectory(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Траектория")
        self.assertContains(response, "84+")
        self.assertContains(response, f"{self.user.student_profile.weekly_hours} ч/нед")
        self.assertContains(response, "Прогноз к экзамену")
        self.assertNotContains(response, "<h2>Потолок</h2>", html=False)
        self.assertNotContains(response, "· прогноз при текущем темпе")

    def test_week_plan_auto_opens_once_per_login_session(self):
        TrajectoryTransition.objects.filter(student=self.user.student_profile).update(
            acknowledged=True
        )
        first = self.client.get(reverse("dashboard"))
        self.assertTrue(first.context["show_week_plan"])
        self.assertContains(
            first,
            'id="week-plan-dialog" data-session-start data-auto-open',
            html=False,
        )

        second = self.client.get(reverse("dashboard"))
        self.assertFalse(second.context["show_week_plan"])
        self.assertNotContains(second, 'data-session-start')

        self.client.logout()
        self.client.force_login(self.user)
        after_login = self.client.get(reverse("dashboard"))
        self.assertTrue(after_login.context["show_week_plan"])
        self.assertContains(after_login, 'data-session-start')

    def test_dashboard_contains_h1_design_system_markers_and_logo(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, 'class="hero student-hero"')
        self.assertContains(response, 'class="stat-grid"')
        self.assertContains(response, 'class="score-journey"')
        self.assertContains(response, 'class="logo-mark"')

    def test_knowledge_map_contains_seed_nodes(self):
        response = self.client.get(reverse("knowledge_map"))
        self.assertContains(response, "Действия с дробями и степенями")
        self.assertContains(response, "Линейные и квадратные уравнения")
        self.assertContains(response, "0% из 50%")
        self.assertContains(response, "осталось 50%")

    def test_track_page_contains_cluster_sections_and_path_points(self):
        response = self.client.get(reverse("track"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-track-unit")
        self.assertContains(response, "data-track-point")
        self.assertContains(response, 'class="track-unit-header"')
        self.assertContains(response, "data-track-popover")
        self.assertContains(response, "data-track-jump")
        self.assertContains(response, 'class="track-sidebar"')
        self.assertContains(response, "Квесты недели")
        self.assertContains(response, "Следующий шаг")
        self.assertContains(response, "Прогноз к экзамену")
        self.assertContains(
            response,
            f"при {response.context['platform_forecast']['weekly_hours']} ч/нед",
        )
        self.assertContains(response, "track-state-locked")

    def test_locked_track_node_is_a_button_without_lesson_link(self):
        locked = KnowledgeNode.objects.get(code="roots-logs")
        response = self.client.get(reverse("track"))

        self.assertContains(response, '<button class="track-node"', html=False)
        self.assertContains(response, "ЗАКРЫТО")
        self.assertNotContains(response, f'href="/lesson/{locked.id}/"', html=False)

    def test_methodist_node_admin_contains_both_dependency_inlines(self):
        self.client.force_login(User.objects.get(username="methodist"))
        response = self.client.get(
            reverse("admin:knowledge_knowledgenode_change", args=[self.node.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Условия открытия (родительские темы)")
        self.assertContains(response, "Открывает темы (дочерние)")

    def test_mentor_panel_is_only_rendered_for_lesson_context(self):
        url = reverse("lesson", args=[self.node.id])
        self.assertContains(self.client.get(url), 'data-mentor-panel')
        self.assertNotContains(self.client.get(f"{url}?context=review"), 'data-mentor-panel')

    def test_https_video_is_embedded_on_lesson_page(self):
        lesson = Lesson.objects.get(node=self.node)
        lesson.video_url = "https://videos.example/embed/lesson"
        lesson.video_duration_minutes = 15
        lesson.save(update_fields=["video_url", "video_duration_minutes"])

        response = self.client.get(reverse("lesson", args=[self.node.id]))

        self.assertContains(
            response, '<iframe src="https://videos.example/embed/lesson"', html=False
        )
        self.assertContains(response, "Длительность: 15 мин.")
        self.assertContains(response, 'class="video-frame"')

    def test_base_loads_local_katex_and_seed_refreshes_math_text(self):
        response = self.client.get(reverse("lesson", args=[self.node.id]))
        self.assertContains(response, "/static/vendor/katex/katex.min.css")
        self.assertContains(response, "/static/vendor/katex/katex.min.js")
        self.assertContains(response, "/static/vendor/katex/auto-render.min.js")
        self.assertTrue(Assignment.objects.filter(statement__contains="$").exists())
        before = Assignment.objects.count()
        call_command("seed_demo", verbosity=0)
        self.assertEqual(Assignment.objects.count(), before)

    def test_http_video_is_a_link_and_is_not_embedded(self):
        lesson = Lesson.objects.get(node=self.node)
        lesson.video_url = "http://videos.example/embed/lesson"
        lesson.save(update_fields=["video_url"])

        response = self.client.get(reverse("lesson", args=[self.node.id]))

        self.assertNotContains(response, '<iframe src="http://videos.example/embed/lesson"')
        self.assertContains(response, 'href="http://videos.example/embed/lesson"')

    def test_forecast_contains_required_caveat(self):
        response = self.client.get(reverse("forecast"))
        self.assertContains(response, "при текущем темпе")
        self.assertContains(response, "не гарантия")
        self.assertContains(response, "Прогноз платформы")
        self.assertContains(response, "Рекомендации платформы")
        self.assertContains(response, "Сохранить")
        self.assertContains(response, "= прогнозу платформы")

    def test_forecast_shows_empty_topic_recommendation_without_zero_gains(self):
        student = self.user.student_profile
        for node in KnowledgeNode.objects.all():
            set_mastery(student, node, 100)

        response = self.client.get(reverse("forecast"))

        self.assertContains(
            response,
            "Все доступные темы уже дают максимум — открой следующие через карту навыков.",
        )
        self.assertNotContains(response, "+0 баллов")

    def test_parent_dashboard_entry_redirects_to_parent_report(self):
        parent = User.objects.get(username="parent")
        self.client.force_login(parent)
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(
            response, reverse("parent_dashboard"), fetch_redirect_response=False
        )

    def test_diagnostic_page_and_dashboard_link_render_for_student(self):
        ProgressSnapshot.objects.filter(student=self.user.student_profile).delete()
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, 'href="/diagnostic/"')
        diagnostic = self.client.get(reverse("diagnostic"))
        self.assertEqual(diagnostic.status_code, 200)
        self.assertContains(diagnostic, "Диагностика")
        self.assertContains(diagnostic, "Начать")

    def test_diagnostic_page_shows_latest_completed_score(self):
        test = DiagnosticTest.objects.filter(is_active=True).first()
        DiagnosticResult.objects.create(
            student=self.user.student_profile,
            test=test,
            status=DiagnosticResult.Status.COMPLETED,
            estimated_score=72,
            completed_at=timezone.now(),
        )
        response = self.client.get(reverse("diagnostic"))
        self.assertContains(response, "Последний результат")
        self.assertContains(response, "оценка 72 баллов")

    def test_diagnostic_run_is_404_for_another_student(self):
        other_student = make_student(username="diagnostic-owner")
        test = DiagnosticTest.objects.filter(is_active=True).first()
        result = DiagnosticResult.objects.create(student=other_student, test=test)
        response = self.client.get(reverse("diagnostic_run", args=[result.id]))
        self.assertEqual(response.status_code, 404)

    def test_diagnostic_run_does_not_render_correct_answers(self):
        test = DiagnosticTest.objects.filter(is_active=True).first()
        assignment = test.assignments.filter(exam_part=Assignment.Part.PART1).first()
        assignment.correct_answer = "LEAKED-CORRECT-ANSWER"
        assignment.save(update_fields=["correct_answer"])
        result = DiagnosticResult.objects.create(
            student=self.user.student_profile, test=test
        )
        response = self.client.get(reverse("diagnostic_run", args=[result.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "LEAKED-CORRECT-ANSWER")

    def test_completed_diagnostic_run_shows_completed_state(self):
        test = DiagnosticTest.objects.filter(is_active=True).first()
        result = DiagnosticResult.objects.create(
            student=self.user.student_profile,
            test=test,
            status=DiagnosticResult.Status.COMPLETED,
        )
        response = self.client.get(reverse("diagnostic_run", args=[result.id]))
        self.assertContains(response, "Диагностика уже завершена")

    def test_web_diagnostic_start_reuses_in_progress_result(self):
        test = DiagnosticTest.objects.filter(is_active=True).first()
        result = DiagnosticResult.objects.create(
            student=self.user.student_profile, test=test
        )
        response = self.client.post(
            f"/api/diagnostics/{test.id}/start/",
            {"reuse_in_progress": True},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["result_id"], result.id)
        self.assertEqual(
            DiagnosticResult.objects.filter(
                student=self.user.student_profile,
                test=test,
                status=DiagnosticResult.Status.IN_PROGRESS,
            ).count(),
            1,
        )

    def test_dashboard_uses_human_readable_trajectory_reason(self):
        student = self.user.student_profile
        trajectories = list(Trajectory.objects.order_by("target_min")[:2])
        TrajectoryTransition.objects.create(
            student=student,
            from_trajectory=trajectories[0],
            to_trajectory=trajectories[1],
            reasons=["target_score"],
        )
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "изменена цель")
        self.assertNotContains(response, "Причины:</strong> target_score")

    def test_dashboard_shows_pending_overdue_item_but_not_done_one(self):
        student = self.user.student_profile
        plan = get_active_plan(student)
        pending_node = make_node("overdue-pending")
        done_node = make_node("overdue-done", cluster=pending_node.cluster)
        yesterday = timezone.localdate() - timedelta(days=1)
        StudyPlanItem.objects.create(
            plan=plan,
            node=pending_node,
            due_date=yesterday,
            order=1000,
        )
        StudyPlanItem.objects.create(
            plan=plan,
            node=done_node,
            due_date=yesterday,
            order=1001,
            status=StudyPlanItem.Status.DONE,
        )
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, pending_node.title)
        self.assertContains(response, "Просрочено")
        self.assertContains(response, "is-overdue")
        today_titles = [item.node.title for item in response.context["today_items"]]
        self.assertNotIn(done_node.title, today_titles)

    def test_start_mock_opens_run_page_with_server_deadline(self):
        exam = MockExam.objects.filter(is_active=True).first()
        response = self.client.post(f"/api/mocks/{exam.id}/start/", data={})
        self.assertEqual(response.status_code, 201)
        run = self.client.get(reverse("mock_run", args=[response.json()["result_id"]]))
        self.assertEqual(run.status_code, 200)
        self.assertContains(run, "data-deadline")
        self.assertContains(run, "Дедлайн сервера")
        self.assertContains(
            run,
            "Можно отправить пробник без фото — задачи второй части без решения получат 0 баллов.",
        )
        self.assertNotContains(run, "required")

    def test_student_sees_parent_placeholder(self):
        response = self.client.get(reverse("parent_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "родительский кабинет недоступен")

    def test_parent_summary_has_caveat_error_distribution_and_no_chat_text(self):
        student = self.user.student_profile
        assignment = self.node.assignments.first()
        MistakeBacklogItem.objects.create(
            student=student,
            assignment=assignment,
            node=self.node,
            error_type=MistakeBacklogItem.ErrorType.WRONG_METHOD,
        )
        session = AiHintSession.objects.create(
            student=student, assignment=assignment, node=self.node, hints_used=1
        )
        AiHintMessage.objects.create(
            session=session, role=AiHintMessage.Role.MENTOR, text="СЕКРЕТНЫЙ ТЕКСТ ЧАТА"
        )
        parent = User.objects.get(username="parent")
        self.client.force_login(parent)
        response = self.client.get(reverse("parent_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "при текущем темпе")
        self.assertContains(response, "Распределение ошибок")
        self.assertContains(response, "неверный метод")
        self.assertContains(response, "Подсказок наставника")
        self.assertNotContains(response, "СЕКРЕТНЫЙ ТЕКСТ ЧАТА")

    def test_parent_report_contains_gauge_sparkline_and_pace_caveat(self):
        student = self.user.student_profile
        ProgressSnapshot.objects.create(
            student=student,
            start_score=40,
            predicted_score=50,
            target_score=student.target_score,
        )
        self.client.force_login(User.objects.get(username="parent"))

        response = self.client.get(reverse("parent_dashboard"))

        self.assertContains(response, "stroke-dasharray")
        self.assertContains(response, "<polyline", html=False)
        self.assertContains(response, "при текущем темпе")
        self.assertContains(
            response,
            '<p class="gauge-caption-text">прогноз платформы к экзамену</p>',
            html=False,
        )
        self.assertNotContains(response, '<text class="gauge-caption"', html=False)

    def test_login_contains_large_logo_and_tagline(self):
        self.client.logout()
        response = self.client.get(reverse("login"))
        self.assertContains(response, "logo--lg")
        self.assertContains(response, "ценит время")
