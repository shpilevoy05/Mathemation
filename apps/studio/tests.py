from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import Promotion, Subscription, Tariff
from apps.billing.services import promotion_status
from apps.content.models import (
    Assignment, AssignmentSkillTag, DailyChallenge, Lesson, TheoryBlock,
)
from apps.content.services import save_daily_challenge
from apps.diagnostics.models import DiagnosticTest
from apps.events.models import Event
from apps.knowledge.models import KnowledgeDependency, KnowledgeNode, TopicCluster
from apps.knowledge.tests import make_student
from apps.practice.models import Attempt
from apps.mocks.models import MockExam


class StudioTestCase(TestCase):
    def setUp(self):
        self.methodist = User.objects.create_user(
            "studio-methodist", role=User.Role.METHODIST
        )
        self.cluster = TopicCluster.objects.create(title="Алгебра")
        self.node = KnowledgeNode.objects.create(
            code="studio-node", title="Квадратные уравнения", cluster=self.cluster
        )

    def login(self):
        self.client.force_login(self.methodist)

    def lesson_data(self, **overrides):
        data = {
            "node": str(self.node.pk),
            "title": "Урок про дискриминант",
            "order": "1",
            "video_provider": Lesson.VideoProvider.KINESCOPE,
            "video_url": "",
            "video_duration_minutes": "",
            "theory-TOTAL_FORMS": "1",
            "theory-INITIAL_FORMS": "0",
            "theory-MIN_NUM_FORMS": "0",
            "theory-MAX_NUM_FORMS": "1000",
            "theory-0-title": "Формула",
            "theory-0-body": "D = b² - 4ac",
            "theory-0-order": "0",
        }
        data.update(overrides)
        return data

    def task_data(self, **overrides):
        data = {
            "title": "Решите уравнение",
            "lesson": "",
            "statement": "x + 1 = 2",
            "exam_part": "1",
            "difficulty": "2",
            "max_score": "1",
            "answer_type": Assignment.AnswerType.NUMBER,
            "correct_answer": "1",
            "answer_spec": "{}",
            "reference_solution": "Перенесём единицу.",
            "arena_enabled": "on",
            "change_note": "",
            "skills-TOTAL_FORMS": "1",
            "skills-INITIAL_FORMS": "0",
            "skills-MIN_NUM_FORMS": "0",
            "skills-MAX_NUM_FORMS": "1000",
            "skills-0-node": str(self.node.pk),
            "skills-0-weight": "0.7",
        }
        data.update(overrides)
        return data


class StudioPermissionTests(StudioTestCase):
    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("studio_lessons"))
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('studio_lessons')}",
        )

    def test_student_gets_403(self):
        student = make_student("studio-student")
        self.client.force_login(student.user)
        self.assertEqual(self.client.get(reverse("studio_tasks")).status_code, 403)

    def test_methodist_can_open_all_sections(self):
        self.login()
        for name in (
            "studio_lessons", "studio_tasks", "studio_graph", "studio_daily",
            "studio_pricing", "studio_tests", "studio_task_picker",
        ):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_student_cannot_open_wave_two_sections(self):
        student = make_student("studio-wave-two-student")
        self.client.force_login(student.user)
        for name in ("studio_daily", "studio_pricing", "studio_tests"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)


class LessonStudioTests(StudioTestCase):
    def test_create_lesson_with_theory_block_and_audit(self):
        self.login()
        response = self.client.post(reverse("studio_lesson_new"), self.lesson_data())

        lesson = Lesson.objects.get(title="Урок про дискриминант")
        self.assertRedirects(response, reverse("studio_lesson_edit", args=[lesson.pk]))
        self.assertEqual(TheoryBlock.objects.get(lesson=lesson).body, "D = b² - 4ac")
        self.assertTrue(
            Event.objects.filter(
                event_type=Event.Type.ADMIN_ACTION,
                payload__action="lesson.save",
            ).exists()
        )

    def test_publish_empty_lesson_shows_friendly_error(self):
        self.login()
        lesson = Lesson.objects.create(node=self.node, title="Пустой урок")

        response = self.client.post(
            reverse("studio_lesson_edit", args=[lesson.pk]), {"action": "publish"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Нельзя опубликовать пустой урок")
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, Lesson.Status.DRAFT)

    def test_lesson_search_and_status_filter(self):
        self.login()
        Lesson.objects.create(node=self.node, title="Нужный черновик")
        Lesson.objects.create(
            node=self.node, title="Чужой опубликованный", status=Lesson.Status.PUBLISHED
        )
        response = self.client.get(
            reverse("studio_lessons"), {"q": "Нужный", "status": Lesson.Status.DRAFT}
        )
        self.assertContains(response, "Нужный черновик")
        self.assertNotContains(response, "Чужой опубликованный")


class TaskStudioTests(StudioTestCase):
    def test_create_task_with_weighted_skill(self):
        self.login()
        response = self.client.post(reverse("studio_task_new"), self.task_data())

        assignment = Assignment.objects.get(title="Решите уравнение")
        self.assertRedirects(response, reverse("studio_task_edit", args=[assignment.pk]))
        tag = AssignmentSkillTag.objects.get(assignment=assignment, node=self.node)
        self.assertEqual(tag.weight, 0.7)

    def test_edit_after_attempt_creates_new_version_and_audit(self):
        self.login()
        assignment = Assignment.objects.create(
            title="Старая задача", statement="Старое условие", correct_answer="2"
        )
        assignment.skill_tags.create(node=self.node, weight=1)
        student = make_student("studio-version-student")
        Attempt.objects.create(student=student, assignment=assignment, submitted_answer="2")
        data = self.task_data(
            title="Старая задача",
            statement="Новое условие",
            correct_answer="3",
            change_note="Исправлена опечатка",
            **{
                "skills-INITIAL_FORMS": "1",
                "skills-0-id": str(assignment.skill_tags.get().pk),
            },
        )

        response = self.client.post(reverse("studio_task_edit", args=[assignment.pk]), data)

        self.assertRedirects(response, reverse("studio_task_edit", args=[assignment.pk]))
        assignment.refresh_from_db()
        self.assertEqual(assignment.statement, "Новое условие")
        self.assertEqual(list(assignment.versions.values_list("number", flat=True)), [2, 1])
        self.assertEqual(assignment.versions.get(number=2).change_note, "Исправлена опечатка")
        self.assertTrue(
            Event.objects.filter(payload__action="assignment.new_version").exists()
        )

    def test_task_search_and_filters(self):
        self.login()
        shown = Assignment.objects.create(
            title="Логарифм", statement="Найдите x", correct_answer="",
            reference_solution="", difficulty=4, arena_enabled=False,
        )
        shown.skill_tags.create(node=self.node, weight=1)
        Assignment.objects.create(
            title="Геометрия", statement="Площадь", correct_answer="5",
            reference_solution="Готово", difficulty=1,
        )
        response = self.client.get(
            reverse("studio_tasks"),
            {
                "q": "Найдите", "cluster": self.cluster.pk, "difficulty": 4,
                "arena": "no", "missing_answer": "yes", "missing_solution": "yes",
            },
        )
        self.assertContains(response, "Логарифм")
        self.assertNotContains(response, "Геометрия")


class GraphStudioTests(StudioTestCase):
    def setUp(self):
        super().setUp()
        self.other = KnowledgeNode.objects.create(
            code="studio-other", title="Линейные уравнения", cluster=self.cluster
        )
        self.third = KnowledgeNode.objects.create(
            code="studio-third", title="Неравенства", cluster=self.cluster
        )
        self.login()

    def dependency_data(self, **overrides):
        data = {
            "action": "add_dependency",
            "direction": "this_requires",
            "other_node": str(self.other.pk),
            "kind": KnowledgeDependency.Kind.PREREQUISITE,
            "min_mastery": "70",
        }
        data.update(overrides)
        return data

    def test_creates_node_with_editable_fields_and_audit(self):
        response = self.client.post(
            reverse("studio_node_new"),
            {
                "action": "save",
                "code": "studio-created",
                "title": "Новая тема",
                "cluster": str(self.cluster.pk),
                "ege_numbers": "6, 12",
                "hours_estimate": "3.5",
                "weight": "0.8",
            },
        )
        created = KnowledgeNode.objects.get(code="studio-created")
        self.assertRedirects(response, reverse("studio_node_edit", args=[created.pk]))
        self.assertEqual(created.ege_task_numbers, [6, 12])
        self.assertEqual(created.hours_estimate, 3.5)
        self.assertTrue(Event.objects.filter(payload__action="knowledge_node.save").exists())

    def test_adds_dependencies_in_both_directions_and_deletes(self):
        url = reverse("studio_node_edit", args=[self.node.pk])
        self.client.post(url, self.dependency_data())
        first = KnowledgeDependency.objects.get(
            node=self.node, prerequisite=self.other
        )
        self.client.post(
            url,
            self.dependency_data(
                direction="other_requires", other_node=str(self.third.pk),
                kind=KnowledgeDependency.Kind.SUPPORTS,
            ),
        )
        self.assertTrue(
            KnowledgeDependency.objects.filter(
                node=self.third, prerequisite=self.node,
                kind=KnowledgeDependency.Kind.SUPPORTS,
            ).exists()
        )
        response = self.client.post(
            reverse("studio_dependency_delete", args=[self.node.pk, first.pk])
        )
        self.assertRedirects(response, url)
        self.assertFalse(KnowledgeDependency.objects.filter(pk=first.pk).exists())
        actions = set(
            Event.objects.filter(event_type=Event.Type.ADMIN_ACTION)
            .values_list("payload__action", flat=True)
        )
        self.assertIn("knowledge_dependency.add", actions)
        self.assertIn("knowledge_dependency.delete", actions)

    def test_cycle_is_rejected_with_friendly_message(self):
        KnowledgeDependency.objects.create(node=self.other, prerequisite=self.node)
        response = self.client.post(
            reverse("studio_node_edit", args=[self.node.pk]), self.dependency_data()
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "создаёт цикл")
        self.assertEqual(KnowledgeDependency.objects.count(), 1)

    def test_graph_search_returns_expected_node(self):
        response = self.client.get(reverse("studio_graph"), {"q": "Квадратные"})
        self.assertContains(response, "Квадратные уравнения")
        self.assertNotContains(response, "Линейные уравнения")


class DailyChallengeStudioTests(StudioTestCase):
    def setUp(self):
        super().setUp()
        self.login()
        self.assignment = Assignment.objects.create(
            title="Задача дня", statement="2 + 2", correct_answer="4"
        )

    def test_create_daily_challenge(self):
        day = timezone.localdate() + timedelta(days=2)
        response = self.client.post(
            reverse("studio_daily_edit", args=[day.isoformat()]),
            {
                "assignment": str(self.assignment.pk), "title": "Разминка",
                "description": "Решите без калькулятора", "reward_xp": "30",
                "is_active": "on", "action": "save",
            },
        )
        challenge = DailyChallenge.objects.get(date=day)
        self.assertRedirects(response, reverse("studio_daily_edit", args=[day.isoformat()]))
        self.assertEqual(challenge.assignment, self.assignment)
        self.assertEqual(challenge.reward_xp, 30)
        self.assertTrue(Event.objects.filter(payload__action="daily_challenge.save").exists())

    def test_duplicate_date_is_friendly_domain_error(self):
        day = timezone.localdate() + timedelta(days=3)
        DailyChallenge.objects.create(date=day, assignment=self.assignment)
        second = DailyChallenge(
            date=timezone.localdate() + timedelta(days=4), assignment=self.assignment
        )
        with self.assertRaisesMessage(ValidationError, "уже назначено"):
            save_daily_challenge(
                date=day, assignment=self.assignment, instance=second,
                created_by=self.methodist,
            )

    def test_past_day_is_read_only(self):
        day = timezone.localdate() - timedelta(days=1)
        DailyChallenge.objects.create(date=day, assignment=self.assignment, title="Было")
        url = reverse("studio_daily_edit", args=[day.isoformat()])
        response = self.client.get(url)
        self.assertContains(response, "только чтение")
        self.assertNotContains(response, "Сохранить")
        self.assertEqual(self.client.post(url, {"action": "save"}).status_code, 403)


class PricingStudioTests(StudioTestCase):
    def setUp(self):
        super().setUp()
        self.login()
        self.tariff = Tariff.objects.create(
            code="solo", title="Самостоятельно", price_rub=Decimal("2900.00"),
            features={"Занятия": "без ограничений"},
        )

    def test_price_change_versions_tariff_and_keeps_subscription(self):
        student = make_student("studio-price-student")
        subscription = Subscription.objects.create(
            student=student, tariff=self.tariff, status=Subscription.Status.ACTIVE,
            starts_at=timezone.now(), ends_at=timezone.now() + timedelta(days=30),
        )
        response = self.client.post(
            reverse("studio_tariff_price", args=[self.tariff.pk]),
            {"price_rub": "3200.00"},
        )
        updated = Tariff.objects.get(code="solo", version=2)
        self.assertRedirects(response, reverse("studio_tariff_edit", args=[updated.pk]))
        self.tariff.refresh_from_db()
        subscription.refresh_from_db()
        self.assertFalse(self.tariff.is_active)
        self.assertEqual(subscription.tariff, self.tariff)
        self.assertEqual(updated.price_rub, Decimal("3200.00"))

    def promotion_data(self, **overrides):
        data = {
            "title": "Первый месяц", "description": "", "code": "start10",
            "kind": Promotion.Kind.PERCENT, "value": "10", "tariff_codes": ["solo"],
            "starts_at": "", "ends_at": "", "max_uses": "0", "is_active": "on",
        }
        data.update(overrides)
        return data

    def test_percent_above_one_hundred_is_rejected(self):
        response = self.client.post(
            reverse("studio_promotion_new"), self.promotion_data(value="101")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "от 1 до 100")
        self.assertFalse(Promotion.objects.exists())

    def test_code_is_normalised_and_unique_among_active(self):
        first = self.client.post(reverse("studio_promotion_new"), self.promotion_data())
        promotion = Promotion.objects.get()
        self.assertRedirects(first, reverse("studio_promotion_edit", args=[promotion.pk]))
        self.assertEqual(promotion.code, "START10")

        duplicate = self.client.post(
            reverse("studio_promotion_new"), self.promotion_data(title="Другая")
        )
        self.assertContains(duplicate, "уже существует")
        self.assertEqual(Promotion.objects.count(), 1)

    def test_inactive_code_can_be_reused_by_active_promotion(self):
        Promotion.objects.create(
            title="Старая", code="START10", value=10, is_active=False
        )
        response = self.client.post(reverse("studio_promotion_new"), self.promotion_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Promotion.objects.filter(code="START10").count(), 2)

    def test_statuses_and_preview_price(self):
        now = timezone.now()
        live = Promotion.objects.create(title="Идёт", value=10)
        planned = Promotion.objects.create(
            title="Потом", value=10, starts_at=now + timedelta(days=1)
        )
        ended = Promotion.objects.create(
            title="Конец", value=10, ends_at=now - timedelta(minutes=1)
        )
        exhausted = Promotion.objects.create(
            title="Лимит", value=10, max_uses=1, used_count=1
        )
        disabled = Promotion.objects.create(title="Выкл", value=10, is_active=False)
        self.assertEqual(
            [promotion_status(item, now) for item in (live, planned, ended, exhausted, disabled)],
            ["live", "scheduled", "ended", "exhausted", "disabled"],
        )
        response = self.client.get(reverse("studio_promotion_edit", args=[live.pk]))
        self.assertContains(response, "2900,00 ₽ → 2610,00 ₽")


class TestBuilderStudioTests(StudioTestCase):
    def setUp(self):
        super().setUp()
        self.login()
        self.first = Assignment.objects.create(
            title="Алгебра 1", statement="x=1", correct_answer="1", exam_part=1
        )
        self.second = Assignment.objects.create(
            title="Алгебра 2", statement="Докажите", reference_solution="Разбор",
            exam_part=2,
        )
        self.first.skill_tags.create(node=self.node, weight=1)
        self.second.skill_tags.create(node=self.node, weight=1)

    def test_diagnostic_adds_and_removes_tasks(self):
        response = self.client.post(
            reverse("studio_diagnostic_new"),
            {"title": "Срез", "is_active": "on", "add_tasks": [self.first.pk, self.second.pk]},
        )
        diagnostic = DiagnosticTest.objects.get(title="Срез")
        self.assertRedirects(response, reverse("studio_diagnostic_edit", args=[diagnostic.pk]))
        self.assertEqual(diagnostic.assignments.count(), 2)
        self.client.post(
            reverse("studio_diagnostic_edit", args=[diagnostic.pk]),
            {"remove_task": str(self.first.pk)},
        )
        self.assertEqual(list(diagnostic.assignments.all()), [self.second])

    def test_mock_adds_and_removes_tasks(self):
        response = self.client.post(
            reverse("studio_mock_new"),
            {
                "title": "Пробник", "duration_minutes": "235", "is_active": "on",
                "add_tasks": [self.first.pk, self.second.pk],
            },
        )
        exam = MockExam.objects.get(title="Пробник")
        self.assertRedirects(response, reverse("studio_mock_edit", args=[exam.pk]))
        self.assertEqual(exam.assignments.count(), 2)
        self.client.post(
            reverse("studio_mock_edit", args=[exam.pk]),
            {"remove_task": str(self.second.pk)},
        )
        self.assertEqual(list(exam.assignments.all()), [self.first])

    def test_picker_filters_by_search_node_part_and_ege(self):
        self.node.ege_task_numbers = [6]
        self.node.save(update_fields=["ege_task_numbers"])
        other = Assignment.objects.create(
            title="Геометрия", statement="Площадь", correct_answer="4", exam_part=1
        )
        response = self.client.get(
            reverse("studio_task_picker"),
            {"q": "Алгебра 1", "node": self.node.pk, "part": 1, "ege": 6},
        )
        self.assertContains(response, "Алгебра 1")
        self.assertNotContains(response, "Алгебра 2")
        self.assertNotContains(response, other.title)
