"""Разбор партии, подбор случайного соперника и рейтинг."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.knowledge.tests import make_student
from apps.practice.models import MistakeBacklogItem

from .matchmaking import (
    bot_level_for,
    expire_stale,
    find_rival,
    get_profile,
    join_queue,
)
from .models import Match, MatchmakingTicket, MatchParticipant
from .services import (
    create_match,
    finish_match,
    finish_participant,
    next_question,
    participant_for,
    submit_answer,
)
from .tests import make_pool


class ReviewTests(TestCase):
    """После партии ученик видит свои ошибки и правильные ответы."""

    def setUp(self):
        self.student = make_student("review-player")
        make_pool()
        self.match = create_match(self.student, mode=Match.Mode.QUIZ, bot_level=1)
        self.me = participant_for(self.match, self.student)
        self.client.force_login(self.student.user)

    def play(self, *, correct: bool):
        while True:
            question = next_question(self.match, self.me)
            if question is None:
                break
            value = question.assignment.correct_answer if correct else "мимо"
            submit_answer(self.match, self.student, question, value, 3000)
            self.me.refresh_from_db()

    def state(self) -> dict:
        return self.client.get(f"/api/arena/matches/{self.match.id}/").json()

    def test_review_appears_only_after_the_match(self):
        self.assertEqual(self.state()["review"], [])

        self.play(correct=False)

        self.assertEqual(len(self.state()["review"]), self.match.questions.count())

    def test_review_shows_the_right_answer_for_a_miss(self):
        self.play(correct=False)

        row = self.state()["review"][0]

        self.assertFalse(row["is_correct"])
        self.assertEqual(row["my_answer"], "мимо")
        self.assertTrue(row["correct_answer"])

    def test_review_marks_what_was_solved(self):
        self.play(correct=True)

        self.assertTrue(all(row["is_correct"] for row in self.state()["review"]))

    def test_mistakes_still_stay_off_the_rework_shelf(self):
        self.play(correct=False)

        self.assertFalse(
            MistakeBacklogItem.objects.filter(student=self.student).exists()
        )


class MatchmakingTests(TestCase):
    def setUp(self):
        self.first = make_student("queue-one")
        self.second = make_student("queue-two")
        make_pool()

    def rate(self, student, rating):
        profile = get_profile(student)
        profile.rating = rating
        profile.save(update_fields=["rating"])
        return profile

    def test_first_player_waits(self):
        ticket = join_queue(self.first, mode=Match.Mode.QUIZ)

        self.assertEqual(ticket.status, MatchmakingTicket.Status.WAITING)
        self.assertIsNone(ticket.match_id)

    def test_close_ratings_are_paired(self):
        self.rate(self.first, 1200)
        self.rate(self.second, 1240)
        join_queue(self.first, mode=Match.Mode.QUIZ)

        ticket = join_queue(self.second, mode=Match.Mode.QUIZ)

        self.assertIsNotNone(ticket.match_id)
        self.assertTrue(ticket.match.is_ranked)
        self.assertEqual(ticket.match.status, Match.Status.ACTIVE)
        self.assertEqual(
            ticket.match.participants.filter(student__isnull=False).count(), 2
        )

    def test_strangers_can_be_paired_without_friendship(self):
        self.rate(self.first, 1100)
        self.rate(self.second, 1120)
        join_queue(self.first, mode=Match.Mode.QUIZ)

        # Случайная партия не требует знакомства: это и есть её смысл.
        self.assertIsNotNone(join_queue(self.second, mode=Match.Mode.QUIZ).match_id)

    def test_distant_rating_waits_for_the_window_to_widen(self):
        self.rate(self.first, 900)
        self.rate(self.second, 1800)
        join_queue(self.first, mode=Match.Mode.QUIZ)

        ticket = join_queue(self.second, mode=Match.Mode.QUIZ)
        self.assertIsNone(ticket.match_id)

        # Через пять минут ожидания окно шире, и соперник уже подходит.
        MatchmakingTicket.objects.filter(student=self.first).update(
            created_at=timezone.now() - timedelta(minutes=5)
        )
        self.assertIsNotNone(find_rival(ticket))

    def test_nearest_rival_wins_over_the_first_in_line(self):
        far = make_student("queue-far")
        near = make_student("queue-near")
        self.rate(far, 1000)
        self.rate(near, 1180)
        self.rate(self.first, 1200)
        join_queue(far, mode=Match.Mode.QUIZ)
        join_queue(near, mode=Match.Mode.QUIZ)

        ticket = join_queue(self.first, mode=Match.Mode.QUIZ)

        rivals = {
            participant.student_id for participant in ticket.match.participants.all()
        }
        self.assertIn(near.pk, rivals)
        self.assertNotIn(far.pk, rivals)

    def test_modes_do_not_mix(self):
        join_queue(self.first, mode=Match.Mode.QUIZ)

        self.assertIsNone(join_queue(self.second, mode=Match.Mode.SPEED).match_id)

    def test_prototypes_do_not_mix(self):
        join_queue(self.first, mode=Match.Mode.QUIZ, ege_task_number=13)

        self.assertIsNone(join_queue(self.second, mode=Match.Mode.QUIZ).match_id)

    def test_repeat_join_keeps_one_ticket(self):
        join_queue(self.first, mode=Match.Mode.QUIZ)
        join_queue(self.first, mode=Match.Mode.QUIZ)

        self.assertEqual(
            MatchmakingTicket.objects.filter(
                student=self.first, status=MatchmakingTicket.Status.WAITING
            ).count(),
            1,
        )

    def test_stale_ticket_is_dropped(self):
        join_queue(self.first, mode=Match.Mode.QUIZ)
        MatchmakingTicket.objects.filter(student=self.first).update(
            created_at=timezone.now() - timedelta(minutes=10)
        )

        expire_stale()

        self.assertEqual(
            MatchmakingTicket.objects.get(student=self.first).status,
            MatchmakingTicket.Status.CANCELLED,
        )

    def test_seed_rating_follows_the_forecast(self):
        profile = get_profile(self.first)

        # Стартовый рейтинг — не середина таблицы, а оценка по прогнозу.
        self.assertGreaterEqual(profile.rating, 800)
        self.assertLessEqual(profile.rating, 1600)

    def test_bot_level_follows_the_rating(self):
        self.rate(self.first, 850)
        self.assertEqual(bot_level_for(self.first), 1)

        self.rate(self.first, 1600)
        self.assertEqual(bot_level_for(self.first), 5)


class RatingTests(TestCase):
    def setUp(self):
        self.first = make_student("rating-one")
        self.second = make_student("rating-two")
        make_pool()
        for student in (self.first, self.second):
            profile = get_profile(student)
            profile.rating = 1200
            profile.save(update_fields=["rating"])
        join_queue(self.first, mode=Match.Mode.QUIZ)
        self.match = join_queue(self.second, mode=Match.Mode.QUIZ).match

    def finish(self, winner, loser):
        MatchParticipant.objects.filter(match=self.match, student=winner).update(
            score=500, correct_count=5, total_time_ms=10_000, finished_at=timezone.now()
        )
        MatchParticipant.objects.filter(match=self.match, student=loser).update(
            score=100, correct_count=1, total_time_ms=20_000, finished_at=timezone.now()
        )
        finish_match(self.match)

    def test_winner_gains_and_loser_loses(self):
        self.finish(self.first, self.second)

        self.assertGreater(get_profile(self.first).rating, 1200)
        self.assertLess(get_profile(self.second).rating, 1200)

    def test_played_and_wins_are_counted(self):
        self.finish(self.first, self.second)

        self.assertEqual(get_profile(self.first).matches_played, 1)
        self.assertEqual(get_profile(self.first).wins, 1)
        self.assertEqual(get_profile(self.second).wins, 0)

    def test_bot_match_leaves_the_rating_alone(self):
        before = get_profile(self.first).rating
        bot_match = create_match(self.first, mode=Match.Mode.QUIZ, bot_level=3)
        me = participant_for(bot_match, self.first)
        MatchParticipant.objects.filter(pk=me.pk).update(
            score=500, finished_at=timezone.now()
        )
        me.refresh_from_db()
        finish_participant(bot_match, me)
        finish_match(bot_match)

        # Бот не рейтингованный соперник: набивать о него рейтинг нельзя.
        self.assertEqual(get_profile(self.first).rating, before)


class QueueApiTests(TestCase):
    def setUp(self):
        self.student = make_student("queue-api")
        make_pool()
        self.client.force_login(self.student.user)

    def test_join_poll_and_cancel(self):
        joined = self.client.post(
            "/api/arena/queue/", {"mode": "quiz"}, content_type="application/json"
        )
        self.assertEqual(joined.status_code, 201)
        self.assertEqual(joined.json()["status"], "waiting")

        self.assertEqual(self.client.get("/api/arena/queue/").json()["status"], "waiting")

        self.client.delete("/api/arena/queue/")
        self.assertEqual(self.client.get("/api/arena/queue/").json()["status"], "idle")

    def test_bot_fallback_starts_a_match_at_the_player_level(self):
        self.client.post(
            "/api/arena/queue/", {"mode": "quiz"}, content_type="application/json"
        )

        response = self.client.post(
            "/api/arena/queue/bot/", {"mode": "quiz"}, content_type="application/json"
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(response.json()["bot_level"])
        # Ожидание снято: играть в двух местах одновременно нельзя.
        self.assertEqual(self.client.get("/api/arena/queue/").json()["status"], "idle")
