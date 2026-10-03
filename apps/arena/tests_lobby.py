"""Партия начинается, когда за столом оба, и опрашивается дёшево."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from apps.knowledge.tests import make_student

from .models import Match, MatchQuestion
from .services import (
    LOBBY_TTL_SECONDS,
    accept_match,
    advance,
    cancel_match,
    create_match,
    join_match,
    open_question,
    participant_for,
    pick_cell,
    submit_quiz_answer,
)
from .tests import make_pool, make_theory, sit_down
from .tests_modes import befriend


class BotLobbyTests(TestCase):
    """С ботом ожидание — формальность: он за столом с самого начала."""

    def setUp(self):
        self.student = make_student("lobby-bot")
        make_theory()
        make_pool()

    def test_match_waits_for_the_player(self):
        match = create_match(self.student, mode=Match.Mode.QUIZ, bot_level=2)

        self.assertEqual(match.status, Match.Status.LOBBY)
        # Вопрос выбран, но не открыт: таймер не идёт, пока игрока нет.
        self.assertIsNone(open_question(match).opened_at)

    def test_joining_starts_the_match(self):
        match = create_match(self.student, mode=Match.Mode.QUIZ, bot_level=2)

        join_match(match, self.student)

        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.ACTIVE)
        self.assertIsNotNone(match.started_at)
        self.assertIsNotNone(open_question(match).opened_at)

    def test_bot_is_at_the_table_from_the_start(self):
        match = create_match(self.student, mode=Match.Mode.QUIZ, bot_level=2)

        self.assertIsNotNone(match.participants.get(is_bot=True).joined_at)


class LobbyNamesTests(TestCase):
    """Кого ждём — это про соперника, а не про того, кто смотрит на экран."""

    def setUp(self):
        self.first = make_student("names-one")
        self.second = make_student("names-two")
        make_theory()
        befriend(self.first, self.second)
        self.match = create_match(
            self.first, mode=Match.Mode.QUIZ, opponent=self.second
        )
        accept_match(self.match, self.second)
        join_match(self.match, self.first)
        self.match.refresh_from_db()
        self.client.force_login(self.first.user)

    def test_rival_is_named(self):
        lobby = self.client.get(
            f"/api/arena/matches/{self.match.id}/"
        ).json()["lobby"]

        self.assertEqual(len(lobby["waiting_for"]), 1)
        self.assertTrue(lobby["joined"])


class HumanLobbyTests(TestCase):
    """С человеком партия ждёт и согласия, и присутствия."""

    def setUp(self):
        self.first = make_student("lobby-one")
        self.second = make_student("lobby-two")
        make_theory()
        befriend(self.first, self.second)
        self.match = create_match(
            self.first, mode=Match.Mode.QUIZ, opponent=self.second
        )

    def test_invite_waits_for_consent(self):
        self.assertEqual(self.match.status, Match.Status.INVITED)

    def test_consent_is_not_the_start(self):
        accept_match(self.match, self.second)

        self.match.refresh_from_db()
        # Согласие получено, но за столом ещё никого: таймеры не идут.
        self.assertEqual(self.match.status, Match.Status.LOBBY)
        self.assertIsNone(open_question(self.match).opened_at)

    def test_one_player_is_not_enough(self):
        accept_match(self.match, self.second)

        join_match(self.match, self.first)

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.LOBBY)

    def test_second_player_starts_the_match(self):
        accept_match(self.match, self.second)
        join_match(self.match, self.first)

        join_match(self.match, self.second)

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.ACTIVE)
        self.assertIsNotNone(open_question(self.match).opened_at)

    def test_moves_are_refused_while_waiting(self):
        accept_match(self.match, self.second)
        join_match(self.match, self.first)
        question = self.match.questions.first()
        MatchQuestion.objects.filter(pk=question.pk).update(opened_at=timezone.now())
        question.refresh_from_db()

        with self.assertRaises(ValidationError):
            submit_quiz_answer(self.match, self.first, question, 0)

    def test_joining_twice_changes_nothing(self):
        accept_match(self.match, self.second)
        sit_down(self.match, self.first, self.second)
        started = self.match.started_at

        join_match(self.match, self.first)

        self.match.refresh_from_db()
        self.assertEqual(self.match.started_at, started)


class LobbyCancelTests(TestCase):
    def setUp(self):
        self.first = make_student("cancel-one")
        self.second = make_student("cancel-two")
        make_theory()
        befriend(self.first, self.second)
        self.match = create_match(
            self.first, mode=Match.Mode.QUIZ, opponent=self.second
        )

    def test_creator_cancels_the_wait(self):
        cancel_match(self.match, self.first)

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.CANCELLED)

    def test_only_the_creator_cancels(self):
        with self.assertRaises(ValidationError):
            cancel_match(self.match, self.second)

    def test_running_match_cannot_be_cancelled(self):
        accept_match(self.match, self.second)
        sit_down(self.match, self.first, self.second)

        # Начатую партию бросать нечестно: в ней уже есть результат.
        with self.assertRaises(ValidationError):
            cancel_match(self.match, self.first)

    def test_forgotten_lobby_expires(self):
        accept_match(self.match, self.second)
        Match.objects.filter(pk=self.match.pk).update(
            created_at=timezone.now() - timedelta(seconds=LOBBY_TTL_SECONDS + 5)
        )
        self.match.refresh_from_db()

        advance(self.match)

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.CANCELLED)


class LobbySweepTests(TestCase):
    """Партию, к которой не подошёл никто, снимает уборка."""

    def setUp(self):
        self.first = make_student("sweep-one")
        self.second = make_student("sweep-two")
        make_theory()
        befriend(self.first, self.second)

    def test_forgotten_matches_are_swept(self):
        from .tasks import sweep_arena

        match = create_match(self.first, mode=Match.Mode.QUIZ, opponent=self.second)
        Match.objects.filter(pk=match.pk).update(
            created_at=timezone.now() - timedelta(seconds=LOBBY_TTL_SECONDS + 60)
        )

        sweep_arena()

        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.CANCELLED)

    def test_fresh_wait_is_left_alone(self):
        from .tasks import sweep_arena

        match = create_match(self.first, mode=Match.Mode.QUIZ, opponent=self.second)

        sweep_arena()

        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.INVITED)

    def test_running_match_is_never_swept(self):
        from .tasks import sweep_arena

        match = create_match(self.first, mode=Match.Mode.QUIZ, bot_level=2)
        sit_down(match, self.first)
        Match.objects.filter(pk=match.pk).update(
            created_at=timezone.now() - timedelta(hours=3)
        )

        sweep_arena()

        match.refresh_from_db()
        self.assertEqual(match.status, Match.Status.ACTIVE)


class LobbyApiTests(TestCase):
    def setUp(self):
        self.student = make_student("lobby-api")
        make_theory()
        self.client.force_login(self.student.user)
        self.match = create_match(self.student, mode=Match.Mode.BOARD, bot_level=2)

    def test_state_shows_the_wait_without_naming_the_viewer(self):
        state = self.client.get(f"/api/arena/matches/{self.match.id}/").json()

        self.assertEqual(state["status"], "lobby")
        self.assertIsNone(state["board"])
        # Себя в «кого ждём» игрок видеть не должен: он уже здесь.
        self.assertEqual(state["lobby"]["waiting_for"], [])
        self.assertFalse(state["lobby"]["joined"])
        self.assertTrue(state["lobby"]["can_cancel"])

    def test_join_through_the_api_starts_the_match(self):
        response = self.client.post(f"/api/arena/matches/{self.match.id}/join/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "active")
        self.assertIsNotNone(response.json()["board"])

    def test_cancel_through_the_api(self):
        response = self.client.post(f"/api/arena/matches/{self.match.id}/cancel/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")

    def test_cancel_of_a_running_match_is_refused(self):
        self.client.post(f"/api/arena/matches/{self.match.id}/join/")

        response = self.client.post(f"/api/arena/matches/{self.match.id}/cancel/")

        self.assertEqual(response.status_code, 409)


class PollCostTests(TestCase):
    """Опрос состояния должен быть дешёвым: экран спрашивает часто."""

    def setUp(self):
        self.student = make_student("poll-cost")
        make_theory()
        self.match = create_match(self.student, mode=Match.Mode.QUIZ, bot_level=1)
        # Бот не должен ходить во время замера: иначе меряем не опрос, а ход.
        self.match.questions.update(bot_time_ms=120_000)
        sit_down(self.match, self.student)
        self.client.force_login(self.student.user)
        self.url = f"/api/arena/matches/{self.match.id}/"

    def test_unchanged_state_answers_304(self):
        first = self.client.get(self.url)
        tag = first["ETag"]

        again = self.client.get(self.url, headers={"if-none-match": tag})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(again.status_code, 304)

    def test_304_is_much_cheaper_than_the_full_state(self):
        tag = self.client.get(self.url)["ETag"]

        with CaptureQueriesContext(connection) as full:
            self.client.get(self.url)
        with CaptureQueriesContext(connection) as short:
            self.client.get(self.url, headers={"if-none-match": tag})

        self.assertLess(len(short), len(full) / 2)

    def test_a_move_changes_the_tag(self):
        tag = self.client.get(self.url)["ETag"]
        question = open_question(self.match)
        index = next(
            i for i, option in enumerate(question.options)
            if question.check_answer(str(option))
        )
        submit_quiz_answer(self.match, self.student, question, index)

        again = self.client.get(self.url, headers={"if-none-match": tag})

        # Состояние изменилось — экран обязан получить его целиком.
        self.assertEqual(again.status_code, 200)

    def test_quiet_poll_writes_nothing(self):
        self.client.get(self.url)

        with CaptureQueriesContext(connection) as captured:
            self.client.get(self.url)

        writes = [
            query for query in captured.captured_queries
            if query["sql"].strip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]
        self.assertEqual(writes, [])


class BoardPollTests(TestCase):
    """Ход соперника виден без перезагрузки, а лишней работы не делается."""

    def setUp(self):
        self.first = make_student("poll-board-one")
        self.second = make_student("poll-board-two")
        make_theory()
        befriend(self.first, self.second)
        self.match = create_match(
            self.first, mode=Match.Mode.BOARD, opponent=self.second
        )
        accept_match(self.match, self.second)
        sit_down(self.match, self.first, self.second)

    def test_rival_pick_changes_the_state_number(self):
        before = Match.objects.get(pk=self.match.pk).revision

        pick_cell(self.match, self.first, self.match.questions.first())

        self.assertGreater(Match.objects.get(pk=self.match.pk).revision, before)

    def test_waiting_for_the_rival_move_is_quiet(self):
        pick_cell(self.match, self.first, self.match.questions.first())
        before = Match.objects.get(pk=self.match.pk).revision

        # Соперник думает — сервер не должен ничего менять при опросе.
        advance(Match.objects.get(pk=self.match.pk))

        self.assertEqual(Match.objects.get(pk=self.match.pk).revision, before)

    def test_participant_state_is_visible_to_the_rival(self):
        self.client.force_login(self.second.user)
        pick_cell(self.match, self.first, self.match.questions.first())

        state = self.client.get(f"/api/arena/matches/{self.match.id}/").json()

        self.assertEqual(state["board"]["turn"], "rival")
        self.assertIsNotNone(state["board"]["open"])
        self.assertFalse(state["board"]["open"]["mine"])
