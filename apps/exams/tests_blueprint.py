"""Структура ЕГЭ-2027: 20 заданий, 33 первичных балла, шкала перевода."""

from django.conf import settings
from django.test import TestCase

from apps.knowledge.models import KnowledgeNode, TopicCluster

from .blueprint import (
    MAX_PRIMARY_SCORE,
    PRIMARY_TO_SCALED,
    TASKS,
    YEAR,
    load_blueprint,
)
from .models import ExamProfile, ExamTask, ExamTaskSkill


class StructureTests(TestCase):
    """Числа структуры проверяются здесь, а не в голове у методиста."""

    def test_twenty_tasks(self):
        self.assertEqual(len(TASKS), 20)

    def test_part_one_is_thirteen_tasks_by_one_point(self):
        part1 = [task for task in TASKS if task[1] == 1]

        self.assertEqual([task[0] for task in part1], list(range(1, 14)))
        self.assertEqual(len(part1), 13)
        self.assertTrue(all(task[2] == 1 for task in part1))

    def test_part_two_is_seven_tasks_and_twenty_points(self):
        part2 = [task for task in TASKS if task[1] == 2]

        self.assertEqual([task[0] for task in part2], list(range(14, 21)))
        self.assertEqual([task[2] for task in part2], [2, 3, 2, 2, 3, 4, 4])
        self.assertEqual(sum(task[2] for task in part2), 20)

    def test_numbers_are_consecutive(self):
        self.assertEqual([task[0] for task in TASKS], list(range(1, 21)))

    def test_maximum_primary_score(self):
        self.assertEqual(MAX_PRIMARY_SCORE, 33)

    def test_new_tasks_are_in_place(self):
        titles = {number: title for number, _p, _s, _d, title in TASKS}

        # Новое только задание 6; прежние 8, 12 и 16 поменяли место/формат.
        self.assertIn("Случайная величина", titles[6])
        self.assertEqual(titles[9], "Производная и первообразная по графику")
        self.assertEqual(titles[13], "Экономическая задача и финансы (краткий ответ)")
        self.assertEqual(
            titles[17],
            "Моделирование реальных ситуаций: алгебра и начала анализа",
        )


class ScaleTests(TestCase):
    def test_table_covers_every_primary_score(self):
        self.assertEqual(len(PRIMARY_TO_SCALED), MAX_PRIMARY_SCORE + 1)

    def test_table_never_goes_down(self):
        pairs = zip(PRIMARY_TO_SCALED, PRIMARY_TO_SCALED[1:])

        self.assertTrue(all(low <= high for low, high in pairs))

    def test_table_spans_the_whole_scale(self):
        self.assertEqual(PRIMARY_TO_SCALED[0], 0)
        self.assertEqual(PRIMARY_TO_SCALED[-1], 100)

    def test_settings_fallback_matches_the_blueprint(self):
        # Настройки — запасной вариант на случай пустой базы. Разъехавшись
        # с разметкой, они дадут прогноз по другой шкале и никто не заметит.
        self.assertEqual(settings.MAX_PRIMARY_SCORE, MAX_PRIMARY_SCORE)
        self.assertEqual(settings.PRIMARY_TO_SCALED, PRIMARY_TO_SCALED)


class LoadTests(TestCase):
    def setUp(self):
        cluster = TopicCluster.objects.create(title="Тема", order=0)
        self.node = KnowledgeNode.objects.create(
            code="n-6", title="Случайные величины", cluster=cluster,
            ege_task_numbers=[6],
        )
        self.other = KnowledgeNode.objects.create(
            code="n-20", title="Числа", cluster=cluster, ege_task_numbers=[20],
        )

    def test_profile_is_created_and_active(self):
        load_blueprint()

        profile = ExamProfile.active()
        self.assertEqual(profile.year, YEAR)
        self.assertEqual(profile.max_primary_score, 33)
        self.assertEqual(profile.tasks.count(), 20)

    def test_scale_is_marked_as_provisional(self):
        load_blueprint()

        # Официальную шкалу на 33 балла Рособрнадзор ещё не публиковал:
        # выдавать приближение за неё нельзя.
        self.assertFalse(ExamProfile.active().scale_is_official)

    def test_tasks_are_linked_to_the_graph(self):
        load_blueprint()

        task = ExamTask.objects.get(number=6)
        self.assertEqual(
            list(task.skills.values_list("node_id", flat=True)), [self.node.pk]
        )

    def test_unmapped_tasks_are_reported(self):
        report = load_blueprint()

        self.assertIn(1, report["tasks_without_skills"])
        self.assertNotIn(6, report["tasks_without_skills"])

    def test_loading_twice_changes_nothing(self):
        load_blueprint()
        first = ExamTaskSkill.objects.count()

        load_blueprint()

        self.assertEqual(ExamProfile.objects.count(), 1)
        self.assertEqual(ExamTask.objects.count(), 20)
        self.assertEqual(ExamTaskSkill.objects.count(), first)

    def test_dry_run_touches_nothing(self):
        before = (
            ExamProfile.objects.count(),
            ExamTask.objects.count(),
            ExamTaskSkill.objects.count(),
        )

        report = load_blueprint(dry_run=True)

        self.assertTrue(report["dry_run"])
        self.assertEqual(
            (
                ExamProfile.objects.count(),
                ExamTask.objects.count(),
                ExamTaskSkill.objects.count(),
            ),
            before,
        )

    def test_stale_links_are_dropped(self):
        load_blueprint()
        self.node.ege_task_numbers = []
        self.node.save(update_fields=["ege_task_numbers"])

        load_blueprint()

        self.assertFalse(ExamTask.objects.get(number=6).skills.exists())

    def test_old_tasks_are_removed_from_the_profile(self):
        load_blueprint()
        profile = ExamProfile.active()
        ExamTask.objects.create(profile=profile, number=21, exam_part=2, max_score=4)

        load_blueprint()

        # Сумма баллов профиля должна совпадать с максимальным первичным баллом.
        self.assertEqual(
            sum(profile.tasks.values_list("max_score", flat=True)), MAX_PRIMARY_SCORE
        )

    def test_profile_validates_its_own_scale(self):
        load_blueprint()

        ExamProfile.active().full_clean()

    def test_command_loads_the_profile(self):
        from django.core.management import call_command

        call_command("load_exam_blueprint", verbosity=0)

        self.assertEqual(ExamProfile.objects.count(), 1)


class ForecastNoticeTests(TestCase):
    """Экран прогноза не выдаёт приближение за официальную шкалу."""

    def setUp(self):
        from apps.knowledge.tests import make_student

        self.student = make_student("scale-notice")
        self.client.force_login(self.student.user)
        load_blueprint()

    def test_provisional_scale_is_announced(self):
        body = self.client.get("/forecast/").content.decode()

        self.assertIn("предварительной шкале", body)

    def test_official_scale_says_nothing(self):
        ExamProfile.objects.update(scale_is_official=True)

        body = self.client.get("/forecast/").content.decode()

        self.assertNotIn("предварительной шкале", body)

    def test_scale_covers_the_new_maximum(self):
        body = self.client.get("/forecast/").content.decode()

        self.assertIn("первичных из 33", body)
