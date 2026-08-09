from datetime import timedelta

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.ai_mentor.models import AiHintMessage, AiHintSession
from apps.content.models import Assignment, DailyChallenge, Lesson
from apps.expert_review.models import ExpertReviewRequest
from apps.mocks.models import MockExam
from apps.practice.models import Attempt, MistakeBacklogItem
from apps.practice.services import submit_attempt
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
        self.assertContains(response, 'class="student-hero"')
        self.assertContains(response, 'class="stat-grid"')
        self.assertContains(response, 'class="score-journey"')
        self.assertContains(response, 'class="logo-mark"')
        # Иконки интерфейса приходят спрайтом, а не эмодзи.
        self.assertContains(response, 'id="i-flame"')
        self.assertContains(response, 'href="#i-home"')

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

    def test_lesson_page_asks_for_the_link_instead_of_carrying_it(self):
        lesson = Lesson.objects.get(node=self.node)
        lesson.video_provider = Lesson.VideoProvider.OTHER
        lesson.video_url = "https://rutube.ru/video/lesson/"
        lesson.video_duration_minutes = 15
        lesson.save(
            update_fields=["video_provider", "video_url", "video_duration_minutes"]
        )

        response = self.client.get(reverse("lesson", args=[self.node.id]))

        # Сохранённая страница не должна давать доступ к видео: в HTML лежит
        # только адрес выдачи, а сама ссылка приходит отдельным запросом.
        self.assertNotContains(response, "rutube.ru")
        self.assertContains(response, f'data-video="/api/lessons/{lesson.id}/playback/"')
        self.assertContains(response, "Длительность: 15 мин.")

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


class DesignSystemTests(TestCase):
    """Новое оформление: граф на карте, шкала первичных, сигмы, тарифы в меню."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.user = User.objects.get(username="student")

    def setUp(self):
        self.client.force_login(self.user)

    def test_map_ships_graph_layout_with_nodes_and_edges(self):
        response = self.client.get(reverse("knowledge_map"))
        graph = response.context["graph"]

        self.assertEqual(len(graph["nodes"]), KnowledgeNode.objects.count())
        self.assertTrue(graph["edges"])
        self.assertContains(response, "graph-data")

    def test_graph_nodes_never_overlap_each_other(self):
        graph = self.client.get(reverse("knowledge_map")).context["graph"]

        for first in graph["nodes"]:
            for second in graph["nodes"]:
                if first["id"] >= second["id"]:
                    continue
                distance = (
                    (first["x"] - second["x"]) ** 2 + (first["y"] - second["y"]) ** 2
                ) ** 0.5
                self.assertGreater(distance, 70, f"{first['title']} и {second['title']}")

    def test_dashboard_gauge_uses_primary_points_with_target_and_interval(self):
        gauge = self.client.get(reverse("dashboard")).context["gauge"]

        self.assertEqual(gauge["max_primary"], 32)
        self.assertEqual(gauge["target_scaled"], self.user.student_profile.target_score)
        self.assertLessEqual(gauge["now_percent"], 100)
        self.assertGreaterEqual(gauge["target_percent"], gauge["now_percent"])

    def test_forecast_page_shows_profile_coverage(self):
        response = self.client.get(reverse("forecast"))

        self.assertEqual(response.context["coverage"]["unmapped_numbers"], [])
        self.assertContains(response, "Покрытие профиля экзамена")

    def test_shop_speaks_about_sigmas_and_shows_the_token(self):
        response = self.client.get(reverse("shop"))

        self.assertContains(response, "сигм")
        self.assertContains(response, "sigma-coin")

    def test_navigation_leads_to_pricing(self):
        self.assertContains(self.client.get(reverse("dashboard")), reverse("pricing"))


class CompletionAndVerdictTests(TestCase):
    """Пройденное занятие, счёт недели у родителя и вердикт эксперта у ученика."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.user = User.objects.get(username="student")

    def setUp(self):
        self.client.force_login(self.user)
        self.student = self.user.student_profile

    def _solve_all_tasks(self, node):
        from apps.practice.services import submit_attempt

        assignments = Assignment.objects.filter(skill_tags__node=node).distinct()
        for assignment in assignments:
            submit_attempt(
                self.student, assignment, assignment.correct_answer, Attempt.Context.LESSON
            )
        return assignments.count()

    def test_lesson_point_is_done_once_every_task_is_solved(self):
        node = KnowledgeNode.objects.get(code="frac-powers")
        self.assertTrue(self._solve_all_tasks(node))

        points = [
            point
            for cluster in self.client.get(reverse("track")).context["track_clusters"]
            for point in cluster["points"]
            if point["node_id"] == node.id and point["type"] == "lesson"
        ]

        self.assertTrue(points)
        for point in points:
            self.assertTrue(point["is_done"], point["title"])
            self.assertEqual(point["marker"], "✓")

    def test_parent_week_counts_items_by_completion_not_by_due_date(self):
        from apps.planning.services import complete_item, get_active_plan
        from apps.progress.services import build_parent_report

        plan = get_active_plan(self.student)
        item = plan.items.filter(item_type="lesson").first()
        # Пункт со сроком в прошлом, закрытый сегодня, — работа этой недели.
        item.due_date = timezone.localdate() - timedelta(days=30)
        item.save(update_fields=["due_date"])
        complete_item(item)

        report = build_parent_report(self.student)

        self.assertEqual(report.payload["week_fact"]["plan_items_done"], 1)

    def test_returned_work_is_visible_to_the_student_with_the_comment(self):
        from django.core.files.base import ContentFile

        from apps.accounts.models import User as UserModel
        from apps.expert_review.services import finish_review, submit_solution

        assignment = Assignment.objects.filter(exam_part=2).first()
        review = submit_solution(
            self.student, assignment, ContentFile(b"\xff\xd8\xff\xe0jpeg", name="s.jpg")
        )
        finish_review(
            review, UserModel.objects.get(username="expert"), {"1": 0},
            comment="Проекция верна, пересчитай тангенс.", needs_resubmission=True,
        )

        response = self.client.get(reverse("practice_backlog"))

        rows = response.context["expert_reviews"]
        self.assertEqual(rows[0]["status_label"], "вернули на доработку")
        self.assertTrue(rows[0]["needs_resubmission"])
        self.assertContains(response, "Проекция верна")
        self.assertContains(response, "data-resubmit-form")

    def test_pending_work_is_shown_as_waiting_for_the_expert(self):
        from django.core.files.base import ContentFile

        from apps.expert_review.services import submit_solution

        assignment = Assignment.objects.filter(exam_part=2).first()
        submit_solution(
            self.student, assignment, ContentFile(b"\xff\xd8\xff\xe0jpeg", name="s.jpg")
        )

        rows = self.client.get(reverse("practice_backlog")).context["expert_reviews"]

        self.assertTrue(rows[0]["is_pending"])
        self.assertFalse(rows[0]["needs_resubmission"])


class ParentReportContentTests(TestCase):
    """Родителю нужны конкретные числа прогресса и траектории, а не прочерки."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def setUp(self):
        self.parent = User.objects.get(username="parent")
        self.student = User.objects.get(username="student").student_profile
        self.client.force_login(self.parent)

    def test_progress_block_counts_topics_plan_and_week(self):
        from apps.progress.services import build_parent_report

        progress = build_parent_report(self.student).payload["progress"]

        self.assertEqual(progress["nodes_total"], KnowledgeNode.objects.count())
        self.assertGreater(progress["plan_items_total"], 0)
        self.assertIn("average_mastery", progress)
        self.assertLessEqual(progress["program_percent"], 100)

    def test_trajectory_block_names_the_scenario_and_the_pace(self):
        from apps.progress.services import build_parent_report

        trajectory = build_parent_report(self.student).payload["trajectory"]

        self.assertTrue(trajectory["title"])
        self.assertEqual(trajectory["student_weekly_hours"], self.student.weekly_hours)
        self.assertIsInstance(trajectory["keeps_pace"], bool)

    def test_forecast_is_measured_even_without_the_nightly_job(self):
        from apps.progress.models import ProgressSnapshot
        from apps.progress.services import build_parent_report

        ProgressSnapshot.objects.filter(student=self.student).delete()

        dynamics = build_parent_report(self.student).payload["dynamics"]

        self.assertIsNotNone(dynamics["current_predicted_score"])
        self.assertEqual(ProgressSnapshot.objects.filter(student=self.student).count(), 1)

    def test_page_shows_both_blocks_with_numbers(self):
        response = self.client.get(reverse("parent_dashboard"))

        self.assertContains(response, "Прогресс по программе")
        self.assertContains(response, "Текущая траектория")
        self.assertContains(response, "тем освоено")
        self.assertNotContains(response, "Траектория назначается после входной диагностики")


class ShopAndDailyVisualTests(TestCase):
    """Витрина и задание дня собраны по макету: карточки, ярлыки, неделя серии."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.user = User.objects.get(username="student")

    def setUp(self):
        self.client.force_login(self.user)

    def test_every_shop_item_becomes_a_card_with_an_icon_and_a_tag(self):
        cards = self.client.get(reverse("shop")).context["shop_cards"]

        self.assertTrue(cards)
        for card in cards:
            with self.subTest(item=card["item"].title):
                self.assertTrue(card["icon"].startswith("i-"))
                self.assertTrue(card["tag"])
                self.assertIn(card["group"], {"boost", "avatar", "frame", "theme", "badge"})

    def test_unaffordable_item_says_how_much_is_missing(self):
        from apps.economy.models import ShopItem

        expensive = ShopItem.objects.filter(effect=ShopItem.Effect.NONE).order_by(
            "-price_coins"
        ).first()

        card = next(
            row for row in self.client.get(reverse("shop")).context["shop_cards"]
            if row["item"] == expensive
        )

        self.assertFalse(card["affordable"])
        self.assertEqual(card["missing"], expensive.price_coins)

    def test_freeze_card_is_frosted_and_boosts_group_together(self):
        cards = {
            row["item"].effect: row
            for row in self.client.get(reverse("shop")).context["shop_cards"]
        }

        self.assertTrue(cards["streak_freeze"]["frosted"])
        self.assertEqual(cards["streak_freeze"]["group"], "boost")
        self.assertEqual(cards["xp_boost"]["group"], "boost")

    def test_daily_page_shows_the_week_of_the_streak(self):
        response = self.client.get(reverse("daily_challenge"))

        week = response.context["week_days"]
        self.assertEqual(len(week), 7)
        self.assertEqual(sum(1 for day in week if day["is_today"]), 1)
        self.assertContains(response, "Неделя серии")

    def test_solved_challenge_reports_the_streak_instead_of_the_form(self):
        challenge = DailyChallenge.objects.get(date=timezone.localdate())
        submit_attempt(
            self.user.student_profile, challenge.assignment,
            challenge.assignment.correct_answer, Attempt.Context.LESSON,
        )

        response = self.client.get(reverse("daily_challenge"))

        self.assertTrue(response.context["solved"])
        self.assertContains(response, "Серия продлена")


class HomeworkAndDailyPageTests(TestCase):
    """Домашки и задание дня видны ученику в кабинете, а не только в API."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.user = User.objects.get(username="student")

    def setUp(self):
        self.client.force_login(self.user)

    def test_homework_page_shows_assigned_work_with_progress(self):
        response = self.client.get(reverse("homework"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Домашка: вычисления и уравнения")
        self.assertContains(response, "решено")
        self.assertEqual(response.context["open_count"], 1)
        row = response.context["homework_rows"][0]
        self.assertEqual(row["progress"]["total"], 3)
        self.assertEqual(row["percent"], 0)

    def test_homework_task_links_to_lesson_of_its_node(self):
        row = self.client.get(reverse("homework")).context["homework_rows"][0]
        task = row["tasks"][0]

        self.assertIsNotNone(task["node"])
        self.assertEqual(task["url"], reverse("lesson", args=[task["node"].id]))

    def test_daily_page_shows_todays_challenge_with_answer_form(self):
        response = self.client.get(reverse("daily_challenge"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["challenge"])
        self.assertFalse(response.context["solved"])
        self.assertContains(response, "data-attempt-form")
        self.assertContains(response, "data-answer-progress")

    def test_daily_page_reports_solved_state_after_correct_attempt(self):
        challenge = DailyChallenge.objects.get(date=timezone.localdate())
        submit_attempt(
            self.user.student_profile,
            challenge.assignment,
            challenge.assignment.correct_answer,
            Attempt.Context.LESSON,
        )

        response = self.client.get(reverse("daily_challenge"))

        self.assertTrue(response.context["solved"])
        self.assertNotContains(response, "data-attempt-form")

    def test_navigation_links_to_homework_and_daily(self):
        response = self.client.get(reverse("dashboard"))

        for url in (reverse("homework"), reverse("daily_challenge")):
            with self.subTest(url=url):
                self.assertContains(response, url)

    def test_pages_require_login(self):
        self.client.logout()
        for name in ("homework", "daily_challenge"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
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
