from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.content.models import Assignment, AssignmentSkillTag
from apps.events.models import Event
from apps.knowledge.tests import make_node, make_student
from apps.planning.models import StudyPlan, StudyPlanItem
from apps.planning.services import complete_item
from apps.practice.models import Attempt, MistakeBacklogItem, ReviewSchedule
from apps.practice.services import complete_review, submit_attempt

from .models import GamificationProfile, WeeklyQuest
from .services import (
    award_xp,
    generate_weekly_quests,
    level_for_xp,
    record_attempt_activity,
    record_plan_item_activity,
    record_review_activity,
)


def make_plan(student, node, start=None):
    start = start or timezone.localdate()
    plan = StudyPlan.objects.create(student=student, target_score=student.target_score)
    for index in range(3):
        StudyPlanItem.objects.create(
            plan=plan,
            node=node,
            item_type=(
                StudyPlanItem.ItemType.PRACTICE
                if index < 2
                else StudyPlanItem.ItemType.LESSON
            ),
            order=index,
            due_date=start + timedelta(days=index),
        )
    return plan


def make_assignment(node, answer="42"):
    assignment = Assignment.objects.create(
        title="Задача", statement="...", correct_answer=answer
    )
    AssignmentSkillTag.objects.create(assignment=assignment, node=node)
    return assignment


class StreakTests(TestCase):
    def setUp(self):
        self.student = make_student()

    def test_two_consecutive_days_advance_streak(self):
        record_attempt_activity(self.student, True, date(2026, 7, 10))
        record_attempt_activity(self.student, False, date(2026, 7, 11))
        profile = GamificationProfile.objects.get(student=self.student)
        self.assertEqual(profile.streak_current, 2)
        self.assertEqual(profile.streak_best, 2)

    def test_skipped_day_resets_streak_neutrally(self):
        record_attempt_activity(self.student, True, date(2026, 7, 8))
        record_attempt_activity(self.student, True, date(2026, 7, 10))
        profile = GamificationProfile.objects.get(student=self.student)
        self.assertEqual(profile.streak_current, 1)
        self.assertEqual(profile.streak_best, 1)
        self.assertTrue(
            Event.objects.filter(
                student=self.student, event_type=Event.Type.STREAK_RESET
            ).exists()
        )

    @override_settings(STREAK_MODE="weekly")
    def test_weekly_mode_counts_consecutive_weeks(self):
        record_attempt_activity(self.student, True, date(2026, 7, 6))
        record_attempt_activity(self.student, True, date(2026, 7, 12))
        record_attempt_activity(self.student, True, date(2026, 7, 13))
        profile = GamificationProfile.objects.get(student=self.student)
        self.assertEqual(profile.streak_current, 2)
        self.assertEqual(profile.streak_period_anchor, date(2026, 7, 13))


class XpIntegrationTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.node = make_node()
        self.plan = make_plan(self.student, self.node)

    def test_xp_and_level_for_each_activity_point(self):
        award_xp(self.student, 90, "test_setup")
        assignment = make_assignment(self.node)
        # Верный ответ платит 10 XP за попытку и 5 XP за пункт плана, который
        # закрылся сам: работа сделана, отмечать её руками ученику не нужно.
        submit_attempt(self.student, assignment, "42", Attempt.Context.LESSON)
        profile = GamificationProfile.objects.get(student=self.student)
        self.assertEqual((profile.xp, profile.level), (105, level_for_xp(105)))

        submit_attempt(self.student, assignment, "wrong", Attempt.Context.LESSON)
        profile.refresh_from_db()
        self.assertEqual((profile.xp, profile.level), (107, level_for_xp(107)))

        backlog = MistakeBacklogItem.objects.get(student=self.student)
        review = backlog.reviews.first()
        complete_review(review, success=True)
        profile.refresh_from_db()
        self.assertEqual((profile.xp, profile.level), (122, level_for_xp(122)))

        # Оставшийся пункт закрывается вручную и платит один раз.
        remaining = self.plan.items.exclude(status=StudyPlanItem.Status.DONE).first()
        complete_item(remaining)
        profile.refresh_from_db()
        self.assertEqual((profile.xp, profile.level), (127, level_for_xp(127)))

    def test_completed_review_and_item_are_not_rewarded_twice(self):
        item = self.plan.items.first()
        complete_item(item)
        complete_item(item)
        self.assertEqual(GamificationProfile.objects.get(student=self.student).xp, 5)


class WeeklyQuestTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.node = make_node()
        self.week_start = date(2026, 7, 6)
        make_plan(self.student, self.node, self.week_start)

    def test_generation_is_idempotent_and_targets_are_realistic(self):
        first = generate_weekly_quests(self.student, self.week_start)
        second = generate_weekly_quests(self.student, self.week_start)
        self.assertEqual(len(first), 2)
        self.assertEqual(
            [quest.id for quest in first], [quest.id for quest in second]
        )
        self.assertTrue(all(quest.target_count >= 3 for quest in first))

    def test_attempt_progress_completes_quest_awards_xp_and_logs_event(self):
        generate_weekly_quests(self.student, self.week_start)
        for _ in range(3):
            record_attempt_activity(self.student, True, self.week_start)
        quest = WeeklyQuest.objects.get(
            student=self.student,
            week_start=self.week_start,
            quest_type=WeeklyQuest.QuestType.SOLVE_TASKS,
        )
        self.assertEqual(quest.progress_count, quest.target_count)
        self.assertTrue(quest.completed)
        self.assertEqual(
            GamificationProfile.objects.get(student=self.student).xp,
            3 * 10 + quest.reward_xp,
        )
        self.assertTrue(
            Event.objects.filter(
                student=self.student,
                event_type=Event.Type.QUEST_COMPLETED,
                payload__quest_id=quest.id,
            ).exists()
        )


class GamificationApiAndDashboardTests(TestCase):
    def setUp(self):
        self.student = make_student()
        self.node = make_node()
        make_plan(self.student, self.node)
        self.client.force_login(self.student.user)
        record_plan_item_activity(self.student)

    def test_api_structure(self):
        response = self.client.get("/api/gamification/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data),
            {"xp", "level", "streak_current", "streak_best", "streak_mode", "quests"},
        )
        self.assertEqual(response.data["xp"], 5)
        self.assertEqual(response.data["streak_mode"], "daily")
        self.assertTrue(response.data["quests"])
        self.assertIn("progress_percent", response.data["quests"][0])

    def test_dashboard_contains_gamification_widget(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-gamification-widget")
        self.assertContains(response, "Учебная серия")
        self.assertContains(response, "5 XP")

