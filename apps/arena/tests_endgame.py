"""Конец партии: решённый исход, выход игрока и пропажа из-за закрытой вкладки."""

from datetime import timedelta

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.knowledge.tests import make_student

from .models import Match, MatchParticipant
from .services import (
    ABSENT_SECONDS,
    accept_match,
    advance,
    clamp_question_count,
    create_match,
    join_match,
    leave_match,
    next_question,
    note_presence,
    outcome_decided,
    participant_for,
    presence_key,
    rank,
    submit_answer,
    winner_of,
)
from .tests import make_pool, make_theory, sit_down
from .tests_modes import befriend


class DecidedOutcomeTests(TestCase):
    """Партию, в которой всё решено, не дотягивают до последнего вопроса."""

    def setUp(self):
        self.student = make_student("decided-player")
        make_pool(count=20)
        self.match = create_match(
            self.student, mode=Match.Mode.SPEED, bot_level=1, question_count=4
        )
        sit_down(self.match, self.student)
        self.me = participant_for(self.match, self.student)
        self.bot = self.match.participants.get(is_bot=True)

    def set_bot_score(self, score: int):
        MatchParticipant.objects.filter(pk=self.bot.pk).update(score=score)
        self.bot.refresh_from_db()

    def answer_next(self, *, correct: bool):
        question = next_question(self.match, self.me)
        value = question.assignment.correct_answer if correct else "мимо"
        submit_answer(self.match, self.student, question, value, 2000)
        self.match.refresh_from_db()
        self.me.refresh_from_db()

    def test_bot_win_ends_the_match_early(self):
        # Бот забрал всё; догнать его нельзя даже идеальной игрой.
        self.set_bot_score(400)
        self.answer_next(correct=False)

        self.assertEqual(self.match.status, Match.Status.FINISHED)
        self.assertEqual(winner_of(self.match).pk, self.bot.pk)

    def test_finished_match_refuses_further_answers(self):
        self.set_bot_score(400)
        self.answer_next(correct=False)
        question = self.match.questions.last()

        with self.assertRaises(ValidationError):
            submit_answer(self.match, self.student, question, "1", 1000)

    def test_finished_match_cannot_be_rejoined(self):
        self.set_bot_score(400)
        self.answer_next(correct=False)

        join_match(self.match, self.student)

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.FINISHED)

    def test_match_goes_on_while_the_gap_is_reachable(self):
        self.set_bot_score(200)

        self.answer_next(correct=True)

        # 100 против 200 и три задачи впереди — догнать можно.
        self.assertEqual(self.match.status, Match.Status.ACTIVE)
        self.assertFalse(outcome_decided(self.match))

    def test_player_win_ends_the_match_too(self):
        self.set_bot_score(0)

        self.answer_next(correct=True)

        # Бот закончил с нулём: оставшиеся задачи ничего не меняют, и держать
        # человека за партией, которая уже выиграна, незачем.
        self.assertEqual(self.match.status, Match.Status.FINISHED)
        self.assertEqual(winner_of(self.match).student_id, self.student.pk)


class LeaveTests(TestCase):
    """Ушедший проигрывает, оставшийся выигрывает."""

    def setUp(self):
        self.first = make_student("leave-one")
        self.second = make_student("leave-two")
        make_theory()
        befriend(self.first, self.second)
        self.match = create_match(
            self.first, mode=Match.Mode.QUIZ, opponent=self.second
        )
        accept_match(self.match, self.second)
        sit_down(self.match, self.first, self.second)

    def test_leaving_finishes_the_match(self):
        leave_match(self.match, self.second)

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.FINISHED)

    def test_the_one_who_stayed_wins(self):
        leave_match(self.match, self.second)

        self.assertEqual(winner_of(self.match).student_id, self.first.pk)

    def test_leading_leaver_still_loses(self):
        MatchParticipant.objects.filter(
            match=self.match, student=self.second
        ).update(score=500)

        leave_match(self.match, self.second)

        # Брошенная партия — не победа, каким бы ни был счёт.
        self.assertEqual(winner_of(self.match).student_id, self.first.pk)
        self.assertEqual(rank(self.match)[0].student_id, self.first.pk)

    def test_leaver_cannot_play_on(self):
        leave_match(self.match, self.second)

        with self.assertRaises(ValidationError):
            leave_match(self.match, self.second)
            join_match(self.match, self.second)
            raise ValidationError("партия должна быть закрыта")

    def test_leaving_a_waiting_match_is_not_a_defeat(self):
        fresh = create_match(self.first, mode=Match.Mode.QUIZ, opponent=self.second)

        leave_match(fresh, self.first)

        fresh.refresh_from_db()
        # Результата ещё не было: это отмена, а не поражение.
        self.assertEqual(fresh.status, Match.Status.CANCELLED)


class AbsenceTests(TestCase):
    """Закрытая вкладка — тот же выход, только без нажатия кнопки."""

    def setUp(self):
        cache.clear()
        self.first = make_student("absent-one")
        self.second = make_student("absent-two")
        make_theory()
        befriend(self.first, self.second)
        self.match = create_match(
            self.first, mode=Match.Mode.QUIZ, opponent=self.second
        )
        accept_match(self.match, self.second)
        sit_down(self.match, self.first, self.second)

    def age_out(self, student):
        """Сделать вид, что игрок сидит давно и давно молчит."""
        MatchParticipant.objects.filter(match=self.match, student=student).update(
            joined_at=timezone.now() - timedelta(seconds=ABSENT_SECONDS + 30)
        )

    def test_silent_player_loses_the_match(self):
        self.age_out(self.first)
        self.age_out(self.second)
        note_presence(self.match, self.first)

        advance(self.match)

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.FINISHED)
        self.assertEqual(winner_of(self.match).student_id, self.first.pk)

    def test_a_player_who_just_sat_down_is_not_dropped(self):
        # Отметки присутствия ещё нет, но игрок только что вошёл.
        advance(self.match)

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.ACTIVE)

    def test_polling_keeps_the_player_in(self):
        self.age_out(self.first)
        self.age_out(self.second)
        for student in (self.first, self.second):
            note_presence(self.match, student)

        advance(self.match)

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.ACTIVE)

    def test_state_request_marks_presence(self):
        self.age_out(self.first)
        self.age_out(self.second)
        self.client.force_login(self.second.user)

        self.client.get(f"/api/arena/matches/{self.match.id}/")

        self.assertTrue(cache.get(presence_key(self.match.pk, self.second.pk)))


class LeaveApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.student = make_student("leave-api")
        make_theory()
        self.match = create_match(self.student, mode=Match.Mode.BOARD, bot_level=2)
        sit_down(self.match, self.student)
        self.client.force_login(self.student.user)

    def test_leave_through_the_api(self):
        response = self.client.post(f"/api/arena/matches/{self.match.id}/leave/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "finished")

    def test_moves_after_leaving_are_refused(self):
        self.client.post(f"/api/arena/matches/{self.match.id}/leave/")
        cell = self.match.questions.first()

        response = self.client.post(
            f"/api/arena/matches/{self.match.id}/pick/",
            {"question_id": cell.pk}, content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)


class QuestionCountTests(TestCase):
    """Длину нарешивания выбирает игрок."""

    def setUp(self):
        self.student = make_student("count-player")
        make_pool(count=40)

    def test_count_is_respected(self):
        match = create_match(
            self.student, mode=Match.Mode.SPEED, bot_level=2, question_count=12
        )

        self.assertEqual(match.questions.count(), 12)

    def test_default_is_eight(self):
        match = create_match(self.student, mode=Match.Mode.SPEED, bot_level=2)

        self.assertEqual(match.questions.count(), 8)

    def test_count_is_clamped(self):
        self.assertEqual(clamp_question_count(1), 4)
        self.assertEqual(clamp_question_count(99), 20)
        self.assertEqual(clamp_question_count(None), 8)

    def test_api_takes_the_count(self):
        self.client.force_login(self.student.user)

        created = self.client.post(
            "/api/arena/matches/",
            {"mode": "speed", "bot_level": 2, "question_count": 16},
            content_type="application/json",
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["questions_total"], 16)

    def test_queue_does_not_mix_lengths(self):
        from .matchmaking import join_queue

        other = make_student("count-other")
        join_queue(self.student, mode=Match.Mode.SPEED, question_count=8)

        ticket = join_queue(other, mode=Match.Mode.SPEED, question_count=16)

        # «До восьми» и «до шестнадцати» — разные состязания.
        self.assertIsNone(ticket.match_id)


class BotLevelChoiceTests(TestCase):
    """Сложность бота выбирается в любом режиме, включая запасного соперника."""

    def setUp(self):
        self.student = make_student("level-player")
        make_pool(count=20)
        make_theory()
        self.client.force_login(self.student.user)

    def test_level_is_kept_for_every_mode(self):
        for mode in (Match.Mode.SPEED, Match.Mode.QUIZ, Match.Mode.BOARD):
            with self.subTest(mode=mode):
                match = create_match(self.student, mode=mode, bot_level=5)
                self.assertEqual(match.bot_level, 5)

    def test_queue_fallback_takes_the_chosen_level(self):
        response = self.client.post(
            "/api/arena/queue/bot/",
            {"mode": "quiz", "bot_level": 1}, content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["bot_level"], 1)
