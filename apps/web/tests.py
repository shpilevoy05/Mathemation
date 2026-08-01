from datetime import timedelta

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.ai_mentor.models import AiHintMessage, AiHintSession
from apps.content.models import Assignment, Lesson
from apps.expert_review.models import ExpertReviewRequest
from apps.mocks.models import MockExam
from apps.practice.models import MistakeBacklogItem
from apps.progress.models import ProgressSnapshot
from apps.knowledge.models import KnowledgeDependency, KnowledgeNode, TopicCluster
from apps.knowledge.services import set_mastery
from apps.knowledge.tests import make_node, make_student

from .services import (
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
    def test_positions_unlock_conditions_and_mastered_state_are_prepared(self):
        student = make_student(username="track-context-student")
        cluster = TopicCluster.objects.create(title="Тестовый кластер", color="#3D6BE5")
        mastered = make_node("track-mastered", cluster=cluster, order=0)
        prerequisite = make_node("track-prerequisite", cluster=cluster, order=1)
        locked = make_node("track-locked", cluster=cluster, order=2)
        KnowledgeDependency.objects.create(
            node=locked, prerequisite=prerequisite, min_mastery=70
        )
        for node in (mastered, prerequisite, locked):
            Lesson.objects.create(
                node=node, title=f"Урок: {node.title}",
                status=Lesson.Status.PUBLISHED,
            )
        set_mastery(student, mastered, 90)

        context = track_context(student)
        points = context["track_clusters"][0]["points"]

        self.assertEqual([point["position"] for point in points], [0, 1, 2, 3, 4, 0])
        mastered_points = [point for point in points if point["node_id"] == mastered.id]
        self.assertTrue(all(point["is_done"] for point in mastered_points))
        locked_point = next(
            point for point in points if point["node_id"] == locked.id
        )
        self.assertEqual(locked_point["visual_state"], "locked")
        self.assertIsNone(locked_point["url"])
        self.assertEqual(locked_point["unlock_conditions"][0]["title"], prerequisite.title)
        self.assertIn("нужно 70%, сейчас 0%", locked_point["unlock_tooltip"])


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
        self.assertContains(response, "при текущем темпе")

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
        self.assertContains(response, "нужно 50%")
        self.assertContains(response, "сейчас 0%")

    def test_track_page_contains_cluster_sections_and_path_points(self):
        response = self.client.get(reverse("track"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-track-cluster")
        self.assertContains(response, "data-track-point")
        self.assertContains(response, "track-pos-0")
        self.assertContains(response, "track-state-locked")

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
        lesson.video_provider = Lesson.VideoProvider.OTHER
        lesson.video_url = "https://videos.example/embed/lesson"
        lesson.video_duration_minutes = 15
        lesson.save(
            update_fields=["video_provider", "video_url", "video_duration_minutes"]
        )

        response = self.client.get(reverse("lesson", args=[self.node.id]))

        self.assertContains(
            response, '<iframe src="https://videos.example/embed/lesson"', html=False
        )
        self.assertContains(response, "Длительность: 15 мин.")

    def test_http_video_is_a_link_and_is_not_embedded(self):
        lesson = Lesson.objects.get(node=self.node)
        lesson.video_provider = Lesson.VideoProvider.OTHER
        lesson.video_url = "http://videos.example/embed/lesson"
        lesson.save(update_fields=["video_provider", "video_url"])

        response = self.client.get(reverse("lesson", args=[self.node.id]))

        self.assertNotContains(response, '<iframe src="http://videos.example/embed/lesson"')
        self.assertContains(response, 'href="http://videos.example/embed/lesson"')

    def test_forecast_contains_required_caveat(self):
        response = self.client.get(reverse("forecast"))
        self.assertContains(response, "при текущем темпе")
        self.assertContains(response, "не гарантия")

    def test_non_student_gets_polite_placeholder(self):
        parent = User.objects.get(username="parent")
        self.client.force_login(parent)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "кабинет ученика недоступен")

    def test_start_mock_opens_run_page_with_server_deadline(self):
        exam = MockExam.objects.filter(is_active=True).first()
        response = self.client.post(f"/api/mocks/{exam.id}/start/", data={})
        self.assertEqual(response.status_code, 201)
        run = self.client.get(reverse("mock_run", args=[response.json()["result_id"]]))
        self.assertEqual(run.status_code, 200)
        self.assertContains(run, "data-deadline")
        self.assertContains(run, "Дедлайн сервера")

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

    def test_login_contains_large_logo_and_tagline(self):
        self.client.logout()
        response = self.client.get(reverse("login"))
        self.assertContains(response, "logo--lg")
        self.assertContains(response, "ценит время")


class ShopPageTests(TestCase):
    """Магазин доступен из кабинета, а не только через API."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.user = User.objects.get(username="student")

    def setUp(self):
        self.client.force_login(self.user)

    def test_shop_page_lists_items_and_balance(self):
        response = self.client.get(reverse("shop"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Магазин")
        self.assertContains(response, "Аватар «Сова»")

    def test_navigation_and_dashboard_link_to_shop(self):
        for url in (reverse("dashboard"), reverse("track")):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), reverse("shop"))

    def test_shop_page_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("shop"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)


class ProgressFeedbackTests(TestCase):
    """Ответ ученика сразу показывает движение по теме."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.user = User.objects.get(username="student")
        cls.node = KnowledgeNode.objects.get(code="frac-powers")

    def setUp(self):
        self.client.force_login(self.user)

    def test_attempt_response_carries_node_progress(self):
        from apps.content.models import Assignment

        assignment = Assignment.objects.filter(skill_tags__node=self.node).first()
        response = self.client.post(
            f"/api/assignments/{assignment.id}/attempt/",
            {"answer": assignment.correct_answer, "context": "lesson"},
            "application/json",
        )
        self.assertEqual(response.status_code, 201)
        progress = response.json()["progress"]
        self.assertTrue(progress)
        entry = next(item for item in progress if item["node_id"] == self.node.id)
        self.assertGreater(entry["mastery"], 0)
        self.assertGreaterEqual(entry["solved"], 1)
        self.assertLessEqual(entry["solved"], entry["total"])
        self.assertIn("lesson", entry["completed_plan_items"])

    def test_track_shows_solved_task_counter(self):
        from apps.content.models import Assignment

        assignment = Assignment.objects.filter(skill_tags__node=self.node).first()
        self.client.post(
            f"/api/assignments/{assignment.id}/attempt/",
            {"answer": assignment.correct_answer, "context": "lesson"},
            "application/json",
        )
        context = track_context(self.user.student_profile)
        point = next(
            item
            for cluster in context["track_clusters"]
            for item in cluster["points"]
            if item.get("node_id") == self.node.id
        )
        self.assertGreaterEqual(point["tasks_solved"], 1)
        self.assertGreater(point["tasks_total"], 0)
        self.assertContains(self.client.get(reverse("track")), "задачи")
