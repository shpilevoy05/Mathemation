from datetime import date, timedelta
from unittest.mock import patch

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
    advance_streak,
    award_xp,
    generate_weekly_quests,
    level_for_xp,
    next_streak_badge,
    record_attempt_activity,
    record_plan_item_activity,
    record_review_activity,
    streak_badges,
    streak_unit,
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

    def test_flame_is_granted_exactly_at_seven_and_not_equipped(self):
        from apps.economy.models import InventoryItem, ShopItem

        for offset in range(6):
            advance_streak(self.student, date(2026, 7, 1) + timedelta(days=offset))

        self.assertFalse(
            InventoryItem.objects.filter(
                student=self.student, item__slot="frame", item__code="flame"
            ).exists()
        )

        advance_streak(self.student, date(2026, 7, 7))

        flame = ShopItem.objects.get(slot="frame", code="flame")
        self.assertEqual(flame.tier, ShopItem.Tier.REWARD)
        self.assertEqual(flame.price_coins, 0)
        owned = InventoryItem.objects.get(student=self.student, item=flame)
        self.assertFalse(owned.is_equipped)

    def test_flame_grant_and_milestone_event_are_idempotent(self):
        from apps.economy.models import InventoryItem

        for offset in range(8):
            advance_streak(self.student, date(2026, 7, 1) + timedelta(days=offset))
        advance_streak(self.student, date(2026, 7, 8))

        self.assertEqual(
            InventoryItem.objects.filter(
                student=self.student, item__slot="frame", item__code="flame"
            ).count(),
            1,
        )

    def test_flame_owner_does_not_touch_catalog_on_later_advance(self):
        for offset in range(7):
            advance_streak(self.student, date(2026, 7, 1) + timedelta(days=offset))

        with patch("apps.economy.catalog.ensure_cosmetic") as ensure_cosmetic:
            advance_streak(self.student, date(2026, 7, 8))

        ensure_cosmetic.assert_not_called()
        self.assertEqual(
            Event.objects.filter(
                student=self.student,
                event_type=Event.Type.STREAK_MILESTONE,
                payload__days=7,
            ).count(),
            1,
        )

    def test_streak_badges_and_next_badge(self):
        profile = GamificationProfile.objects.create(
            student=self.student,
            streak_current=12,
            streak_best=15,
        )

        badges = streak_badges(profile)

        self.assertEqual([badge["code"] for badge in badges[:3]], ["streak-7", "streak-15", "streak-30"])
        self.assertEqual([badge["earned"] for badge in badges[:3]], [True, True, False])
        self.assertEqual(next_streak_badge(profile), {"days": 30, "left": 18})

    def test_next_streak_badge_returns_none_after_last_milestone(self):
        profile = GamificationProfile.objects.create(
            student=self.student,
            streak_current=150,
            streak_best=150,
        )

        self.assertIsNone(next_streak_badge(profile))

    @override_settings(STREAK_MODE="daily")
    def test_daily_streak_unit(self):
        self.assertEqual(streak_unit(), "дн.")

    @override_settings(STREAK_MODE="weekly")
    def test_weekly_streak_unit(self):
        self.assertEqual(streak_unit(), "нед.")


class StreakRewardMigrationTests(TestCase):
    def test_backfill_creates_flame_and_grants_existing_profiles_once(self):
        from apps.economy.models import InventoryItem, ShopCategory, ShopItem
        from apps.gamification.migrations._streak_rewards import (
            grant_flame_to_existing_profiles,
        )

        student = make_student("streak-backfill")
        other = make_student("streak-below-threshold")
        GamificationProfile.objects.create(student=student, streak_best=7)
        GamificationProfile.objects.create(student=other, streak_best=6)

        granted = grant_flame_to_existing_profiles(
            ShopCategory,
            ShopItem,
            InventoryItem,
            GamificationProfile,
        )
        granted_again = grant_flame_to_existing_profiles(
            ShopCategory,
            ShopItem,
            InventoryItem,
            GamificationProfile,
        )

        flame = ShopItem.objects.get(slot="frame", code="flame")
        self.assertEqual(flame.tier, ShopItem.Tier.REWARD)
        self.assertEqual(flame.price_coins, 0)
        self.assertEqual(granted, 1)
        self.assertEqual(granted_again, 0)
        self.assertTrue(InventoryItem.objects.filter(student=student, item=flame).exists())
        self.assertFalse(InventoryItem.objects.filter(student=other, item=flame).exists())


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
            {
                "xp", "level", "streak_current", "streak_best", "streak_mode",
                "streak_freezes", "xp_boost_percent", "xp_boost_until", "quests",
            },
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

    def test_dashboard_context_contains_streak_badge_data(self):
        from apps.web.services import dashboard_context

        context = dashboard_context(self.student)

        self.assertIn("streak_badges", context)
        self.assertIn("next_streak_badge", context)
        self.assertEqual(context["streak_unit"], "дн.")
        self.assertEqual(context["streak_badges"][0]["code"], "streak-7")

