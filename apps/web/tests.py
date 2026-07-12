from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.ai_mentor.models import AiHintMessage, AiHintSession
from apps.content.models import Lesson
from apps.mocks.models import MockExam
from apps.practice.models import MistakeBacklogItem
from apps.knowledge.models import KnowledgeNode


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

    def test_knowledge_map_contains_seed_nodes(self):
        response = self.client.get(reverse("knowledge_map"))
        self.assertContains(response, "Действия с дробями и степенями")
        self.assertContains(response, "Линейные и квадратные уравнения")
        self.assertContains(response, "нужно 50%")
        self.assertContains(response, "сейчас 0%")

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
