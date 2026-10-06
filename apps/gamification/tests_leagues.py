"""Лиги: участие по желанию, когорты по двадцать мест, итоги месяца."""

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.economy.models import InventoryItem, ShopItem, XpBoost
from apps.economy.services import get_wallet
from apps.knowledge.tests import make_student

from .leagues import (
    COHORT_SIZE,
    COIN_PRIZES,
    PROMOTION_PLACES,
    close_season,
    current_season,
    disable_leagues,
    enable_leagues,
    league_state,
    membership_for,
    rotate_seasons,
    standings,
)
from .models import (
    GamificationProfile,
    League,
    LeagueCohort,
    LeagueMember,
    LeagueSeason,
    LeagueTrophy,
)
from .services import award_xp


def profile_of(student) -> GamificationProfile:
    profile, _ = GamificationProfile.objects.get_or_create(student=student)
    return profile


class OptInTests(TestCase):
    """Соревнование выключено, пока ученик сам его не включил."""

    def setUp(self):
        self.student = make_student("league-one")

    def test_leagues_are_off_by_default(self):
        self.assertFalse(profile_of(self.student).leagues_enabled)
        self.assertIsNone(membership_for(self.student))

    def test_xp_does_not_reach_leagues_while_off(self):
        award_xp(self.student, 50, source="test")

        self.assertIsNone(membership_for(self.student))
        self.assertFalse(LeagueMember.objects.exists())

    def test_enabling_seats_the_student(self):
        member = enable_leagues(self.student)

        self.assertTrue(profile_of(self.student).leagues_enabled)
        self.assertEqual(member.cohort.league, League.DELTA)
        self.assertEqual(member.cohort.members.count(), COHORT_SIZE)

    def test_xp_counts_after_enabling(self):
        enable_leagues(self.student)

        award_xp(self.student, 40, source="test")

        self.assertEqual(membership_for(self.student).xp, 40)

    def test_leaving_frees_the_seat(self):
        enable_leagues(self.student)
        cohort = membership_for(self.student).cohort

        disable_leagues(self.student)

        self.assertFalse(profile_of(self.student).leagues_enabled)
        self.assertIsNone(membership_for(self.student))
        # Место занял бот: соперники не должны гнаться за ушедшим.
        self.assertEqual(cohort.members.count(), COHORT_SIZE)

    def test_experience_survives_leaving(self):
        enable_leagues(self.student)
        award_xp(self.student, 30, source="test")

        disable_leagues(self.student)

        self.assertEqual(profile_of(self.student).xp, 30)


class CohortTests(TestCase):
    """Двадцать мест: сначала живые, остальное — боты."""

    def seat(self, name: str, xp: int = 0):
        student = make_student(name)
        enable_leagues(student)
        if xp:
            award_xp(student, xp, source="test")
        return student

    def test_cohort_is_always_full(self):
        self.seat("cohort-one")

        cohort = LeagueCohort.objects.get()

        self.assertEqual(cohort.members.count(), COHORT_SIZE)
        self.assertEqual(cohort.members.filter(is_filler=False).count(), 1)

    def test_new_player_takes_a_bot_seat(self):
        self.seat("cohort-one")
        self.seat("cohort-two")

        cohort = LeagueCohort.objects.get()

        self.assertEqual(cohort.members.count(), COHORT_SIZE)
        self.assertEqual(cohort.members.filter(is_filler=False).count(), 2)

    def test_twenty_first_player_opens_a_new_cohort(self):
        for index in range(COHORT_SIZE + 1):
            self.seat(f"crowd-{index}")

        self.assertEqual(LeagueCohort.objects.count(), 2)
        self.assertEqual(
            LeagueMember.objects.filter(is_filler=False, cohort__index=0).count(),
            COHORT_SIZE,
        )

    def test_leagues_do_not_mix(self):
        student = self.seat("delta-player")
        alpha = make_student("alpha-player")
        profile = profile_of(alpha)
        profile.league = League.ALPHA
        profile.save(update_fields=["league"])

        enable_leagues(alpha)

        self.assertNotEqual(
            membership_for(student).cohort_id, membership_for(alpha).cohort_id
        )
        self.assertEqual(membership_for(alpha).cohort.league, League.ALPHA)


class StandingsTests(TestCase):
    def setUp(self):
        self.students = []
        for index in range(3):
            student = make_student(f"rank-{index}")
            enable_leagues(student)
            award_xp(student, (index + 1) * 100, source="test")
            self.students.append(student)
        self.cohort = LeagueCohort.objects.get()

    def test_order_is_by_experience(self):
        rows = standings(self.cohort)

        self.assertEqual([row["place"] for row in rows[:3]], [1, 2, 3])
        self.assertEqual(rows[0]["xp"], 300)

    def test_bots_stand_below_the_weakest_player(self):
        rows = standings(self.cohort)
        live = [row for row in rows if not row["is_filler"]]
        bots = [row for row in rows if row["is_filler"]]

        weakest = min(row["xp"] for row in live)
        self.assertTrue(all(row["xp"] < weakest for row in bots))
        self.assertTrue(all(row["place"] > len(live) for row in bots))

    def test_bots_stay_below_even_at_zero(self):
        newcomer = make_student("rank-zero")
        enable_leagues(newcomer)

        rows = standings(self.cohort)
        mine = next(row for row in rows if row["is_me"] is False and row["title"].startswith("rank-zero"))

        self.assertTrue(all(row["place"] > mine["place"] for row in rows if row["is_filler"]))

    def test_promotion_and_prize_zones_are_marked(self):
        rows = standings(self.cohort)

        self.assertTrue(rows[0]["promotes"])
        self.assertEqual(rows[0]["coins"], COIN_PRIZES[1])
        self.assertFalse(rows[PROMOTION_PLACES]["promotes"])
        self.assertEqual(rows[PROMOTION_PLACES]["coins"], 0)

    def test_state_knows_my_place(self):
        state = league_state(self.students[2])

        self.assertEqual(state["place"], 1)
        self.assertEqual(state["xp"], 300)
        self.assertTrue(state["enabled"])


class SeasonCloseTests(TestCase):
    """Итоги месяца: повышения, сигмы и особые награды."""

    def build(self, league: str, count: int = 12):
        students = []
        for index in range(count):
            student = make_student(f"{league}-{index}")
            profile = profile_of(student)
            profile.league = league
            profile.save(update_fields=["league"])
            enable_leagues(student)
            award_xp(student, (count - index) * 100, source="test")
            students.append(student)
        return students

    def test_top_ten_move_up(self):
        students = self.build(League.DELTA)

        close_season(current_season())

        # Первые десять поднялись, одиннадцатый остался.
        self.assertEqual(profile_of(students[0]).league, League.GAMMA)
        self.assertEqual(profile_of(students[9]).league, League.GAMMA)
        self.assertEqual(profile_of(students[10]).league, League.DELTA)

    def test_top_five_get_coins(self):
        students = self.build(League.DELTA)
        # Сигмы за опыт начисляются и так, поэтому смотрим прибавку, а не итог.
        before = [get_wallet(student).balance for student in students[:6]]

        close_season(current_season())

        after = [get_wallet(student).balance for student in students[:6]]
        self.assertEqual(after[0] - before[0], COIN_PRIZES[1])
        self.assertEqual(after[4] - before[4], COIN_PRIZES[5])
        self.assertEqual(after[5] - before[5], 0)

    def test_places_are_recorded(self):
        self.build(League.DELTA, count=3)

        close_season(current_season())

        places = list(
            LeagueMember.objects.filter(is_filler=False)
            .order_by("place").values_list("place", flat=True)
        )
        self.assertEqual(places, [1, 2, 3])

    def test_season_closes_once(self):
        self.build(League.DELTA, count=2)
        season = current_season()
        close_season(season)

        second = close_season(season)

        season.refresh_from_db()
        self.assertEqual(season.status, LeagueSeason.Status.CLOSED)
        self.assertEqual(second["promoted"], 0)

    def test_prizes_reach_the_junior_leagues_too(self):
        students = self.build(League.DELTA, count=4)

        close_season(current_season())

        # Первое место в Дельте — ускоритель на 12 часов и заморозка.
        top = LeagueTrophy.objects.filter(student=students[0]).get()
        self.assertEqual(top.place, 1)
        self.assertIn("на 12 ч", top.prize)
        self.assertIn("заморозка", top.prize.lower())
        self.assertTrue(top.trophy)
        self.assertIn("вымпел", top.prize.lower())

    def test_only_the_top_three_get_a_prize(self):
        students = self.build(League.DELTA, count=5)

        close_season(current_season())

        places = sorted(LeagueTrophy.objects.values_list("place", flat=True))
        self.assertEqual(places, [1, 2, 3])
        self.assertFalse(LeagueTrophy.objects.filter(student=students[3]).exists())

    def test_second_place_gets_a_boost(self):
        students = self.build(League.DELTA, count=3)

        close_season(current_season())

        self.assertTrue(XpBoost.objects.filter(student=students[1]).exists())

    def test_prize_grows_with_the_league(self):
        from .leagues import prize_title

        # Набор один, но длина ускорителя и число заморозок растут по лестнице.
        self.assertIn("на 12 ч", prize_title(League.DELTA, 1))
        self.assertIn("на 24 ч", prize_title(League.GAMMA, 1))
        self.assertIn("на 48 ч", prize_title(League.OMEGA, 1))

    def test_second_place_gets_only_the_boost(self):
        from .leagues import prize_title

        self.assertIn("ускоритель", prize_title(League.GAMMA, 2).lower())
        self.assertNotIn("заморозк", prize_title(League.GAMMA, 2).lower())

    def test_third_place_gets_only_the_freezes(self):
        from .leagues import prize_title

        self.assertIn("заморозки", prize_title(League.OMEGA, 3).lower())
        self.assertNotIn("ускоритель", prize_title(League.OMEGA, 3).lower())

    def test_every_league_has_a_pennant(self):
        from .leagues import has_trophy, prize_title

        for league in League.values:
            with self.subTest(league=league):
                self.assertTrue(has_trophy(league))
                self.assertIn("вымпел", prize_title(league, 1).lower())

    def test_beta_champion_gets_freezes_and_a_trophy(self):
        students = self.build(League.BETA, count=2)

        close_season(current_season())

        self.assertEqual(profile_of(students[0]).streak_freezes, 3)
        self.assertTrue(LeagueTrophy.objects.filter(student=students[0]).exists())

    def test_alpha_champion_gets_a_boost(self):
        students = self.build(League.ALPHA, count=2)

        close_season(current_season())

        self.assertTrue(XpBoost.objects.filter(student=students[0]).exists())

    def test_sigma_champion_gets_a_trophy(self):
        students = self.build(League.SIGMA, count=2)

        close_season(current_season())

        award = LeagueTrophy.objects.get(student=students[0])
        self.assertTrue(award.trophy)
        self.assertIn("вымпел", award.prize)

    def test_sigma_champion_stays_in_sigma(self):
        students = self.build(League.SIGMA, count=2)

        close_season(current_season())

        # Выше Сигмы ничего нет: чемпион остаётся защищать титул.
        self.assertEqual(profile_of(students[0]).league, League.SIGMA)

    def test_first_place_gets_both_parts(self):
        students = self.build(League.OMEGA, count=2)

        close_season(current_season())

        # Первое место — и ускоритель, и заморозки.
        self.assertTrue(XpBoost.objects.filter(student=students[0]).exists())
        self.assertEqual(profile_of(students[0]).streak_freezes, 3)

    def test_cosmetic_prizes_are_idempotent_and_champion_is_first_only(self):
        students = self.build(League.DELTA, count=3)
        season = current_season()

        close_season(season)
        first_counts = [
            InventoryItem.objects.filter(
                student=student, item__tier=ShopItem.Tier.REWARD
            ).count()
            for student in students
        ]
        close_season(season)

        self.assertEqual(first_counts, [2, 1, 1])
        self.assertEqual(
            [
                InventoryItem.objects.filter(
                    student=student, item__tier=ShopItem.Tier.REWARD
                ).count()
                for student in students
            ],
            first_counts,
        )
        self.assertTrue(
            InventoryItem.objects.filter(
                student=students[0], item__code="champion-delta"
            ).exists()
        )
        for student in students[1:]:
            self.assertFalse(
                InventoryItem.objects.filter(
                    student=student, item__code__startswith="champion-"
                ).exists()
            )
        self.assertEqual(
            LeagueTrophy.objects.filter(season=season, trophy=True).count(), 3
        )

    def test_missing_reward_cosmetics_are_created_for_the_champion(self):
        students = self.build(League.DELTA, count=1)
        self.assertFalse(
            ShopItem.objects.filter(
                tier=ShopItem.Tier.REWARD,
                code__in=["rosette-delta-1", "champion-delta"],
            ).exists()
        )

        close_season(current_season())

        self.assertTrue(
            InventoryItem.objects.filter(
                student=students[0], item__code="rosette-delta-1"
            ).exists()
        )
        self.assertTrue(
            InventoryItem.objects.filter(
                student=students[0], item__code="champion-delta"
            ).exists()
        )

    def test_leagues_page_renders_the_pennant_for_a_trophy(self):
        students = self.build(League.DELTA, count=1)
        close_season(current_season())
        self.client.force_login(students[0].user)

        response = self.client.get(reverse("leagues"))

        self.assertContains(response, "#pennant-delta-1")


class RotationTests(TestCase):
    def test_expired_season_is_closed_and_a_new_one_opens(self):
        past = LeagueSeason.objects.create(
            starts_on=date(2020, 1, 1), ends_on=date(2020, 1, 31)
        )

        report = rotate_seasons(timezone.localdate())

        past.refresh_from_db()
        self.assertEqual(past.status, LeagueSeason.Status.CLOSED)
        self.assertEqual(report["closed"], 1)
        self.assertTrue(LeagueSeason.objects.filter(status=LeagueSeason.Status.ACTIVE).exists())

    def test_running_season_is_left_alone(self):
        season = current_season()

        rotate_seasons(season.starts_on + timedelta(days=1))

        season.refresh_from_db()
        self.assertEqual(season.status, LeagueSeason.Status.ACTIVE)

    def test_task_runs_the_rotation(self):
        from .tasks import rotate_leagues

        report = rotate_leagues()

        self.assertIn("season", report)


class LeagueApiTests(TestCase):
    def setUp(self):
        self.student = make_student("league-api")
        self.client.force_login(self.student.user)

    def test_state_is_off_by_default(self):
        state = self.client.get("/api/leagues/").json()

        self.assertFalse(state["enabled"])
        self.assertEqual(state["rows"], [])

    def test_opt_in_and_out(self):
        joined = self.client.post("/api/leagues/participation/")

        self.assertEqual(joined.status_code, 201)
        self.assertTrue(joined.json()["enabled"])
        self.assertEqual(len(joined.json()["rows"]), COHORT_SIZE)

        left = self.client.delete("/api/leagues/participation/")

        self.assertFalse(left.json()["enabled"])

    def test_page_shows_the_invitation_while_off(self):
        body = self.client.get("/leagues/").content.decode()

        self.assertIn("data-league-join", body)

    def test_page_shows_the_table_after_opting_in(self):
        enable_leagues(self.student)

        body = self.client.get("/leagues/").content.decode()

        self.assertIn("league-table", body)
        self.assertIn("Граница повышения", body)
