"""Арена: дружба, партии, бот и правила подсчёта."""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.content.models import Assignment
from apps.economy.services import get_wallet
from apps.events.models import Event
from apps.gamification.models import GamificationProfile
from apps.knowledge.models import SkillMastery
from apps.knowledge.tests import make_node, make_student
from apps.practice.models import Attempt, MistakeBacklogItem

from .bot import bot_run, clamp_level
from .ranks import rank_for_rating
from .models import Friendship, Match, MatchParticipant
from .services import (
    DAILY_REWARDED_MATCHES,
    are_friends,
    create_match,
    finish_participant,
    friends_of,
    next_question,
    participant_for,
    send_friend_request,
    submit_answer,
    winner_of,
    question_pool,
)


def sit_down(match, *students):
    """Посадить игроков за стол: партия не начинается, пока не зашли все."""
    from .services import join_match

    for student in students:
        join_match(match, student)
    match.refresh_from_db()
    return match


def make_theory(count: int = 30, clusters: int = 5):
    """Банк вопросов по теории: из него собираются квиз и «своя игра».

    Вопросы простые и однословные — тесту важны правила игры, а не содержание.
    """
    from apps.content.models import TheoryQuestion
    from apps.knowledge.models import TopicCluster

    made = []
    for column in range(clusters):
        cluster, _ = TopicCluster.objects.get_or_create(
            title=f"Тема {column}", defaults={"order": column}
        )
        for index in range(max(1, count // clusters)):
            difficulty = (index % 5) + 1
            answer = f"ответ{column}{index}"
            made.append(TheoryQuestion.objects.create(
                cluster=cluster,
                prompt=f"Вопрос {column}-{index}?",
                correct_answer=answer,
                difficulty=difficulty,
                options=[answer, "мимо1", "мимо2", "мимо3"],
            ))
    return made


def make_pool(count: int = 12, ege_number: int | None = None):
    """Банк коротких задач: партия берёт вопросы отсюда."""
    node = make_node(f"arena-node-{ege_number or 'any'}", ege_task_numbers=[ege_number] if ege_number else [])
    made = []
    for index in range(count):
        assignment = Assignment.objects.create(
            title=f"Задача {index}", statement="2+2", correct_answer=str(index),
            difficulty=(index % 5) + 1,
        )
        assignment.skill_tags.create(node=node, weight=1.0)
        made.append(assignment)
    return made


class ArenaQuestionPoolTests(TestCase):
    def test_disabled_assignment_is_excluded(self):
        enabled, disabled = make_pool(2)
        disabled.arena_enabled = False
        disabled.save(update_fields=["arena_enabled"])

        pool_ids = set(question_pool().values_list("pk", flat=True))

        self.assertIn(enabled.pk, pool_ids)
        self.assertNotIn(disabled.pk, pool_ids)


class ArenaProfileBatchTests(TestCase):
    def test_arena_context_loads_all_participant_profiles_in_one_query(self):
        from apps.web.services import arena_context

        student = make_student("arena-batch-owner")
        rivals = [make_student(f"arena-batch-{index}") for index in range(3)]
        for rival in rivals:
            match = Match.objects.create(
                created_by=student,
                status=Match.Status.FINISHED,
                finished_at=timezone.now(),
            )
            MatchParticipant.objects.create(match=match, student=student, score=100)
            MatchParticipant.objects.create(match=match, student=rival, score=50)

        with CaptureQueriesContext(connection) as captured:
            context = arena_context(student)

        profile_queries = [
            query["sql"] for query in captured.captured_queries
            if "arena_arenaprofile" in query["sql"].lower()
            and query["sql"].lstrip().upper().startswith("SELECT")
        ]
        self.assertEqual(len(profile_queries), 1, profile_queries)
        self.assertEqual(len(context["match_history"]), 3)
        self.assertTrue(
            all(row["results"][0].rank_code for row in context["match_history"])
        )

    def test_match_payload_loads_both_profiles_in_one_query(self):
        from apps.arena.api import match_payload

        student = make_student("arena-payload-owner")
        rival = make_student("arena-payload-rival")
        match = Match.objects.create(created_by=student)
        MatchParticipant.objects.create(match=match, student=student)
        MatchParticipant.objects.create(match=match, student=rival)

        with CaptureQueriesContext(connection) as captured:
            payload = match_payload(match, student)

        profile_queries = [
            query["sql"] for query in captured.captured_queries
            if "arena_arenaprofile" in query["sql"].lower()
            and query["sql"].lstrip().upper().startswith("SELECT")
        ]
        self.assertEqual(len(profile_queries), 1, profile_queries)
        self.assertTrue(payload["me"]["rank_code"])
        self.assertTrue(payload["opponent"]["rank_code"])


class FriendshipTests(TestCase):
    def setUp(self):
        self.first = make_student("friend-one")
        self.second = make_student("friend-two")

    def test_request_then_accept_makes_friends(self):
        link = send_friend_request(self.first, self.second)

        self.assertEqual(link.status, Friendship.Status.PENDING)
        self.assertFalse(are_friends(self.first, self.second))

        from .services import accept_friend_request

        accept_friend_request(link, self.second)

        self.assertTrue(are_friends(self.first, self.second))
        self.assertIn(self.second, list(friends_of(self.first)))
        self.assertIn(self.first, list(friends_of(self.second)))

    def test_counter_request_is_taken_as_consent(self):
        send_friend_request(self.first, self.second)

        # Оба уже позвали друг друга — спрашивать второй раз незачем.
        send_friend_request(self.second, self.first)

        self.assertTrue(are_friends(self.first, self.second))
        self.assertEqual(Friendship.objects.count(), 1)

    def test_repeat_request_does_not_duplicate(self):
        send_friend_request(self.first, self.second)
        send_friend_request(self.first, self.second)

        self.assertEqual(Friendship.objects.count(), 1)

    def test_self_request_is_refused(self):
        with self.assertRaises(ValidationError):
            send_friend_request(self.first, self.first)

    def test_only_addressee_answers_the_request(self):
        from .services import accept_friend_request

        link = send_friend_request(self.first, self.second)

        with self.assertRaises(ValidationError):
            accept_friend_request(link, self.first)


class BotTests(TestCase):
    def setUp(self):
        self.student = make_student("bot-rival")
        make_pool()

    def test_level_is_clamped(self):
        self.assertEqual(clamp_level(0), 1)
        self.assertEqual(clamp_level(9), 5)

    def test_bot_run_is_reproducible(self):
        match = create_match(self.student, mode=Match.Mode.SPEED, bot_level=3)
        questions = list(match.questions.select_related("assignment"))

        first = bot_run(questions, 3, seed=42)
        second = bot_run(questions, 3, seed=42)

        self.assertEqual(
            [row["is_correct"] for row in first], [row["is_correct"] for row in second]
        )

    def test_stronger_bot_answers_better_on_average(self):
        match = create_match(self.student, mode=Match.Mode.SPEED, bot_level=1)
        questions = list(match.questions.select_related("assignment"))

        weak = sum(
            sum(row["is_correct"] for row in bot_run(questions, 1, seed=seed))
            for seed in range(30)
        )
        strong = sum(
            sum(row["is_correct"] for row in bot_run(questions, 5, seed=seed))
            for seed in range(30)
        )

        self.assertGreater(strong, weak)

    def test_bot_plays_before_the_human_starts(self):
        match = create_match(self.student, mode=Match.Mode.SPEED, bot_level=4)
        bot = match.participants.get(is_bot=True)

        # Результат соперника существует до первого хода человека: подстроиться
        # под игрока он не может.
        self.assertIsNotNone(bot.finished_at)
        self.assertEqual(bot.answers.count(), match.questions.count())


class MatchCreationTests(TestCase):
    def setUp(self):
        self.student = make_student("match-owner")
        self.friend = make_student("match-friend")
        make_pool()

    def test_modes_have_their_own_length(self):
        make_theory()
        speed = create_match(self.student, mode=Match.Mode.SPEED, bot_level=2)
        quiz = create_match(self.student, mode=Match.Mode.QUIZ, bot_level=2)

        self.assertEqual(speed.questions.count(), 8)
        self.assertEqual(quiz.questions.count(), 6)

    def test_board_prices_cells_by_difficulty(self):
        make_theory()
        match = create_match(self.student, mode=Match.Mode.BOARD, bot_level=2)

        prices = {question.points for question in match.questions.all()}
        self.assertTrue(prices <= {100, 200, 300, 400, 500})
        self.assertGreater(len(prices), 1)

    def test_both_sides_get_the_same_questions(self):
        from .services import accept_friend_request

        accept_friend_request(send_friend_request(self.student, self.friend), self.friend)
        match = create_match(self.student, mode=Match.Mode.SPEED, opponent=self.friend)

        self.assertEqual(match.participants.count(), 2)
        self.assertEqual(match.questions.count(), 8)

    def test_stranger_cannot_be_challenged(self):
        with self.assertRaises(ValidationError):
            create_match(self.student, mode=Match.Mode.SPEED, opponent=self.friend)

    def test_opponent_is_required(self):
        with self.assertRaises(ValidationError):
            create_match(self.student, mode=Match.Mode.SPEED)

    def test_empty_bank_is_refused_with_a_reason(self):
        Assignment.objects.all().delete()

        with self.assertRaises(ValidationError):
            create_match(self.student, mode=Match.Mode.SPEED, bot_level=2)

    def test_prototype_filters_the_pool(self):
        make_pool(count=10, ege_number=13)

        match = create_match(
            self.student, mode=Match.Mode.SPEED, bot_level=2, ege_task_number=13
        )

        for question in match.questions.select_related("assignment"):
            numbers = [
                number
                for tag in question.assignment.skill_tags.select_related("node")
                for number in tag.node.ege_task_numbers
            ]
            self.assertIn(13, numbers)


class PlayTests(TestCase):
    def setUp(self):
        self.student = make_student("player")
        make_pool()
        self.match = create_match(self.student, mode=Match.Mode.SPEED, bot_level=3)
        sit_down(self.match, self.student)
        self.me = participant_for(self.match, self.student)

    def answer_all(self, *, correct: bool):
        """Играть до конца партии.

        Конец наступает не только на последней задаче: как только догнать
        лидера уже нельзя, партия закрывается сама.
        """
        while True:
            self.match.refresh_from_db()
            if self.match.is_over:
                break
            question = next_question(self.match, self.me)
            if question is None:
                break
            value = question.assignment.correct_answer if correct else "мимо"
            submit_answer(self.match, self.student, question, value, 5000)
            self.me.refresh_from_db()

    def test_correct_answer_scores_the_question_price(self):
        question = next_question(self.match, self.me)

        submit_answer(self.match, self.student, question, question.assignment.correct_answer, 4000)

        self.me.refresh_from_db()
        self.assertEqual(self.me.score, question.points)
        self.assertEqual(self.me.correct_count, 1)

    def test_second_answer_to_the_same_question_is_refused(self):
        question = next_question(self.match, self.me)
        submit_answer(self.match, self.student, question, "1", 1000)

        with self.assertRaises(ValidationError):
            submit_answer(self.match, self.student, question, "2", 1000)

    def test_client_time_is_ignored_for_ranking(self):
        question = next_question(self.match, self.me)

        with patch("apps.arena.services._elapsed_ms", return_value=4000):
            submit_answer(self.match, self.student, question, "1", 999_999_999)

        self.me.refresh_from_db()
        self.assertEqual(self.me.total_time_ms, 4000)

    def test_match_finishes_when_nothing_can_change(self):
        self.answer_all(correct=True)

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.FINISHED)
        self.assertIsNotNone(self.match.finished_at)

    def test_answers_reach_the_log_but_not_mastery(self):
        self.answer_all(correct=False)

        self.assertTrue(
            Attempt.objects.filter(student=self.student, context=Attempt.Context.ARENA).exists()
        )
        # Скорость под таймером — не свидетельство понимания темы.
        self.assertFalse(SkillMastery.objects.filter(student=self.student).exists())
        self.assertFalse(MistakeBacklogItem.objects.filter(student=self.student).exists())

    def test_outsider_cannot_answer(self):
        stranger = make_student("stranger")
        question = next_question(self.match, self.me)

        with self.assertRaises(ValidationError):
            submit_answer(self.match, stranger, question, "1", 1000)

    def test_finished_match_takes_no_more_answers(self):
        self.answer_all(correct=True)
        other = create_match(self.student, mode=Match.Mode.SPEED, bot_level=1)
        question = other.questions.first()

        with self.assertRaises(ValidationError):
            submit_answer(self.match, self.student, question, "1", 1000)


class ScoringTests(TestCase):
    def setUp(self):
        self.student = make_student("scorer")
        make_pool()

    def test_time_breaks_a_tie(self):
        match = create_match(self.student, mode=Match.Mode.SPEED, bot_level=1)
        me = participant_for(match, self.student)
        bot = match.participants.get(is_bot=True)
        MatchParticipant.objects.filter(pk=me.pk).update(score=300, total_time_ms=10_000)
        MatchParticipant.objects.filter(pk=bot.pk).update(score=300, total_time_ms=20_000)

        champion = winner_of(match)

        self.assertEqual(champion.pk, me.pk)

    def test_full_tie_has_no_winner(self):
        match = create_match(self.student, mode=Match.Mode.SPEED, bot_level=1)
        match.participants.update(score=200, total_time_ms=15_000)

        self.assertIsNone(winner_of(match))


class RewardTests(TestCase):
    def setUp(self):
        self.student = make_student("winner")
        make_pool()

    def play_and_win(self):
        match = create_match(self.student, mode=Match.Mode.SPEED, bot_level=1)
        me = participant_for(match, self.student)
        bot = match.participants.get(is_bot=True)
        MatchParticipant.objects.filter(pk=bot.pk).update(
            score=0, correct_count=0, total_time_ms=60_000
        )
        MatchParticipant.objects.filter(pk=me.pk).update(score=500, correct_count=5)
        me.refresh_from_db()
        finish_participant(match, me)
        return match

    def test_win_pays_xp_and_coins_once(self):
        match = self.play_and_win()

        profile = GamificationProfile.objects.get(student=self.student)
        self.assertGreater(profile.xp, 0)
        self.assertGreater(get_wallet(self.student).balance, 0)

        # Повторное закрытие партии не платит второй раз.
        balance = get_wallet(self.student).balance
        from .services import finish_match

        finish_match(match)
        self.assertEqual(get_wallet(self.student).balance, balance)

    def test_daily_cap_stops_farming(self):
        for _ in range(DAILY_REWARDED_MATCHES):
            self.play_and_win()
        balance = get_wallet(self.student).balance

        self.play_and_win()

        self.assertEqual(get_wallet(self.student).balance, balance)
        self.assertEqual(
            Event.objects.filter(
                student=self.student, event_type=Event.Type.ARENA_MATCH_FINISHED
            ).count(),
            DAILY_REWARDED_MATCHES + 1,
        )


class ArenaApiTests(TestCase):
    def setUp(self):
        self.student = make_student("api-player")
        self.friend = make_student("api-friend")
        make_pool()
        self.client.force_login(self.student.user)

    def test_friend_request_and_answer(self):
        response = self.client.post(
            "/api/arena/friends/request/",
            {"username": self.friend.user.username}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)

        link_id = response.json()["id"]
        self.client.force_login(self.friend.user)
        answer = self.client.post(f"/api/arena/friends/{link_id}/accept/", {}, content_type="application/json")

        self.assertEqual(answer.status_code, 200)
        self.assertTrue(are_friends(self.student, self.friend))

    def test_unknown_username_is_not_found(self):
        response = self.client.post(
            "/api/arena/friends/request/",
            {"username": "нет-такого"}, content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_create_match_and_answer_through_the_api(self):
        created = self.client.post(
            "/api/arena/matches/",
            {"mode": "speed", "bot_level": 2}, content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        # Партия ждёт игрока: задачи появляются, когда он сел за стол.
        self.assertEqual(created.json()["status"], "lobby")
        state = self.client.post(
            f"/api/arena/matches/{created.json()['id']}/join/"
        ).json()
        self.assertIsNotNone(state["question"])

        answer = self.client.post(
            f"/api/arena/matches/{state['id']}/answer/",
            {"question_id": state["question"]["id"], "answer": "0", "elapsed_ms": 3000},
            content_type="application/json",
        )

        self.assertEqual(answer.status_code, 200)
        self.assertIn("last_answer", answer.json())

    def test_opponent_is_visible_live(self):
        created = self.client.post(
            "/api/arena/matches/",
            {"mode": "speed", "bot_level": 2}, content_type="application/json",
        ).json()

        state = self.client.get(f"/api/arena/matches/{created['id']}/").json()

        # Соперник виден целиком: имя, оформление и счёт. Это табло, а не
        # подсказка — гнаться не за кем, если счёт соперника узнаёшь в конце.
        for key in ("title", "avatar", "frame", "score", "answered"):
            self.assertIn(key, state["opponent"])

    def test_opponent_answers_stay_hidden(self):
        created = self.client.post(
            "/api/arena/matches/",
            {"mode": "speed", "bot_level": 2}, content_type="application/json",
        ).json()

        state = self.client.get(f"/api/arena/matches/{created['id']}/").json()

        # Счёт — да, ответы — нет: иначе арена превращается в списывание.
        self.assertEqual(state["review"], [])
        self.assertNotIn("answers", state["opponent"])

    def test_someone_elses_match_is_not_found(self):
        created = self.client.post(
            "/api/arena/matches/",
            {"mode": "speed", "bot_level": 2}, content_type="application/json",
        ).json()
        self.client.force_login(self.friend.user)

        self.assertEqual(
            self.client.get(f"/api/arena/matches/{created['id']}/").status_code, 404
        )

    def test_arena_page_opens(self):
        response = self.client.get(reverse("arena"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Новая партия")
        self.assertEqual(
            response.context["arena_rank"],
            rank_for_rating(response.context["arena_rating"]),
        )
