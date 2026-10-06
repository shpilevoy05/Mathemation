"""Правила трёх режимов арены: нарешивание на время, квиз и «своя игра»."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.knowledge.tests import make_student
from apps.practice.models import Attempt

from .bot import choose_cell
from .models import Match, MatchParticipant, MatchQuestion
from .services import (
    accept_friend_request,
    accept_match,
    advance,
    create_match,
    next_question,
    open_cell,
    open_question,
    participant_for,
    pick_cell,
    send_friend_request,
    start_run,
    submit_answer,
    submit_board_answer,
    submit_quiz_answer,
)
from .tests import make_pool, make_theory, sit_down


def befriend(first, second):
    accept_friend_request(send_friend_request(first, second), second)


def backdate(question: MatchQuestion, seconds: int) -> MatchQuestion:
    """Отмотать таймер вопроса назад: тест не ждёт полминуты вживую."""
    MatchQuestion.objects.filter(pk=question.pk).update(
        opened_at=timezone.now() - timedelta(seconds=seconds)
    )
    question.refresh_from_db()
    return question


class SpeedLimitTests(TestCase):
    """Нарешивание: до набора задач или на время — это два разных состязания."""

    def setUp(self):
        self.student = make_student("speed-player")
        make_pool(count=30)

    def test_questions_limit_keeps_a_fixed_set(self):
        match = create_match(self.student, mode=Match.Mode.SPEED, bot_level=2)

        self.assertEqual(match.limit_kind, Match.Limit.QUESTIONS)
        self.assertEqual(match.questions.count(), 8)

    def test_time_limit_takes_a_deeper_bank(self):
        match = create_match(
            self.student, mode=Match.Mode.SPEED, bot_level=2,
            limit_kind=Match.Limit.TIME, time_limit_seconds=120,
        )

        # На время задачи кончаться не должны: партия кончается по таймеру.
        self.assertEqual(match.time_limit_seconds, 120)
        self.assertGreater(match.questions.count(), 8)

    def test_personal_clock_starts_with_the_player(self):
        match = create_match(
            self.student, mode=Match.Mode.SPEED, bot_level=2,
            limit_kind=Match.Limit.TIME, time_limit_seconds=120,
        )
        me = participant_for(match, self.student)
        self.assertIsNone(me.started_at)

        start_run(match, self.student)

        # Отсчёт идёт от первого вопроса игрока: открывший вкладку позже не
        # должен начинать с минусом.
        self.assertIsNotNone(participant_for(match, self.student).started_at)

    def test_answer_after_the_buzzer_is_refused(self):
        match = create_match(
            self.student, mode=Match.Mode.SPEED, bot_level=2,
            limit_kind=Match.Limit.TIME, time_limit_seconds=60,
        )
        sit_down(match, self.student)
        me = participant_for(match, self.student)
        start_run(match, self.student)
        MatchParticipant.objects.filter(pk=me.pk).update(
            started_at=timezone.now() - timedelta(seconds=61)
        )
        question = next_question(match, me)

        with self.assertRaises(ValidationError):
            submit_answer(match, self.student, question, question.correct_answer, 1000)

        self.assertIsNotNone(participant_for(match, self.student).finished_at)

    def test_bot_only_gets_what_fits_the_limit(self):
        match = create_match(
            self.student, mode=Match.Mode.SPEED, bot_level=1,
            limit_kind=Match.Limit.TIME, time_limit_seconds=60,
        )
        bot = match.participants.get(is_bot=True)

        # Бот ограничен тем же таймером, что и человек: успел — значит успел.
        self.assertLessEqual(bot.total_time_ms, 60_000)
        self.assertLess(bot.answers.count(), match.questions.count())


class QuizTests(TestCase):
    """Квиз: общий вопрос, четыре варианта, забирает тот, кто первым нажал верный."""

    def setUp(self):
        self.first = make_student("quiz-one")
        self.second = make_student("quiz-two")
        make_theory()
        befriend(self.first, self.second)
        self.match = create_match(
            self.first, mode=Match.Mode.QUIZ, opponent=self.second
        )
        accept_match(self.match, self.second)
        sit_down(self.match, self.first, self.second)

    def correct_index(self, question) -> int:
        return next(
            index for index, option in enumerate(question.options)
            if question.check_answer(str(option))
        )

    def wrong_index(self, question) -> int:
        return next(
            index for index, option in enumerate(question.options)
            if not question.check_answer(str(option))
        )

    def test_theory_questions_come_with_four_options(self):
        for question in self.match.questions.all():
            self.assertEqual(len(question.options), 4)
            self.assertIsNotNone(question.theory_id)

    def test_first_correct_click_takes_the_question(self):
        question = open_question(self.match)

        submit_quiz_answer(self.match, self.first, question, self.correct_index(question))

        question.refresh_from_db()
        self.assertEqual(question.resolved_by.student_id, self.first.pk)
        self.assertEqual(participant_for(self.match, self.first).score, question.points)

    def test_taken_question_is_closed_for_the_rival(self):
        question = open_question(self.match)
        submit_quiz_answer(self.match, self.first, question, self.correct_index(question))

        with self.assertRaises(ValidationError):
            submit_quiz_answer(self.match, self.second, question, 0)

    def test_next_question_opens_after_the_previous_is_taken(self):
        first_question = open_question(self.match)
        submit_quiz_answer(
            self.match, self.first, first_question, self.correct_index(first_question)
        )

        second_question = open_question(self.match)

        self.assertNotEqual(second_question.pk, first_question.pk)
        self.assertIsNotNone(second_question.opened_at)

    def test_a_miss_costs_the_right_to_answer_but_not_points(self):
        question = open_question(self.match)

        submit_quiz_answer(self.match, self.first, question, self.wrong_index(question))

        self.assertEqual(participant_for(self.match, self.first).score, 0)
        with self.assertRaises(ValidationError):
            submit_quiz_answer(
                self.match, self.first, question, self.correct_index(question)
            )

    def test_rival_still_can_take_it_after_a_miss(self):
        question = open_question(self.match)
        submit_quiz_answer(self.match, self.first, question, self.wrong_index(question))

        submit_quiz_answer(self.match, self.second, question, self.correct_index(question))

        question.refresh_from_db()
        self.assertEqual(question.resolved_by.student_id, self.second.pk)

    def test_question_burns_when_both_miss(self):
        question = open_question(self.match)
        submit_quiz_answer(self.match, self.first, question, self.wrong_index(question))
        submit_quiz_answer(self.match, self.second, question, self.wrong_index(question))

        question.refresh_from_db()
        self.assertIsNotNone(question.resolved_at)
        self.assertIsNone(question.resolved_by)

    def test_question_burns_on_timeout(self):
        question = backdate(open_question(self.match), 31)

        advance(self.match)

        question.refresh_from_db()
        self.assertIsNotNone(question.resolved_at)
        self.assertIsNone(question.resolved_by)

    def test_theory_answers_do_not_reach_the_attempt_log(self):
        question = open_question(self.match)
        submit_quiz_answer(self.match, self.first, question, self.correct_index(question))

        # «Знаю определение» — не попытка решить задачу: в журнал попыток
        # такие ответы не идут, иначе статистика решений станет ложью.
        self.assertFalse(Attempt.objects.filter(student=self.first).exists())

    def test_match_ends_when_questions_run_out(self):
        for _ in range(self.match.questions.count()):
            self.match.refresh_from_db()
            question = open_question(self.match)
            if question is None or self.match.is_over:
                break
            submit_quiz_answer(
                self.match, self.first, question, self.correct_index(question)
            )

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.FINISHED)


class QuizBotTests(TestCase):
    """Бот в квизе жмёт по расписанию, разыгранному до начала партии."""

    def setUp(self):
        self.student = make_student("quiz-bot")
        make_theory()
        self.match = create_match(self.student, mode=Match.Mode.QUIZ, bot_level=3)
        sit_down(self.match, self.student)
        self.bot = self.match.participants.get(is_bot=True)

    def test_schedule_is_rolled_at_creation(self):
        for question in self.match.questions.all():
            self.assertIsNotNone(question.bot_correct)
            self.assertGreater(question.bot_time_ms, 0)

    def test_bot_takes_the_question_when_its_time_comes(self):
        question = open_question(self.match)
        MatchQuestion.objects.filter(pk=question.pk).update(
            bot_correct=True, bot_time_ms=3000
        )
        backdate(question, 5)

        advance(self.match)

        question.refresh_from_db()
        self.assertEqual(question.resolved_by_id, self.bot.pk)
        self.bot.refresh_from_db()
        self.assertEqual(self.bot.score, question.points)

    def test_bot_does_not_hurry_before_its_time(self):
        question = open_question(self.match)
        MatchQuestion.objects.filter(pk=question.pk).update(
            bot_correct=True, bot_time_ms=20_000
        )

        advance(self.match)

        question.refresh_from_db()
        self.assertIsNone(question.resolved_at)

    def test_player_beats_the_bot_by_being_faster(self):
        question = open_question(self.match)
        MatchQuestion.objects.filter(pk=question.pk).update(
            bot_correct=True, bot_time_ms=25_000
        )
        question.refresh_from_db()
        index = next(
            i for i, option in enumerate(question.options)
            if question.check_answer(str(option))
        )

        submit_quiz_answer(self.match, self.student, question, index)

        question.refresh_from_db()
        self.assertEqual(question.resolved_by.student_id, self.student.pk)

    def test_bot_that_misses_does_not_block_the_player(self):
        question = open_question(self.match)
        MatchQuestion.objects.filter(pk=question.pk).update(
            bot_correct=False, bot_time_ms=1000
        )
        backdate(question, 3)
        advance(self.match)
        question.refresh_from_db()
        self.assertIsNone(question.resolved_at)

        index = next(
            i for i, option in enumerate(question.options)
            if question.check_answer(str(option))
        )
        submit_quiz_answer(self.match, self.student, question, index)

        question.refresh_from_db()
        self.assertEqual(question.resolved_by.student_id, self.student.pk)


class BoardTests(TestCase):
    """«Своя игра»: ход по очереди, цена клетки — и приз, и штраф."""

    def setUp(self):
        self.first = make_student("board-one")
        self.second = make_student("board-two")
        make_theory()
        befriend(self.first, self.second)
        self.match = create_match(
            self.first, mode=Match.Mode.BOARD, opponent=self.second
        )
        accept_match(self.match, self.second)
        sit_down(self.match, self.first, self.second)
        self.me = participant_for(self.match, self.first)
        self.rival = participant_for(self.match, self.second)

    def free_cell(self, points: int | None = None) -> MatchQuestion:
        cells = self.match.questions.filter(resolved_at__isnull=True)
        if points is not None:
            cells = cells.filter(points=points)
        return cells.first()

    def test_board_has_columns_by_topic_and_prices_by_difficulty(self):
        columns = {question.column for question in self.match.questions.all()}
        titles = {question.topic_title for question in self.match.questions.all()}

        self.assertGreaterEqual(len(columns), 3)
        self.assertEqual(len(titles), len(columns))
        for question in self.match.questions.all():
            self.assertIn(question.points, (100, 200, 300, 400, 500))

    def test_first_turn_belongs_to_the_challenger(self):
        self.assertEqual(self.match.turn_participant_id, self.me.pk)

    def test_rival_cannot_pick_out_of_turn(self):
        with self.assertRaises(ValidationError):
            pick_cell(self.match, self.second, self.free_cell())

    def test_correct_answer_pays_the_price_and_keeps_the_turn(self):
        cell = pick_cell(self.match, self.first, self.free_cell())

        submit_board_answer(self.match, self.first, cell, cell.correct_answer)

        self.me.refresh_from_db()
        self.match.refresh_from_db()
        self.assertEqual(self.me.score, cell.points)
        self.assertEqual(self.match.turn_participant_id, self.me.pk)

    def test_wrong_answer_costs_the_price_and_passes_the_turn(self):
        cell = pick_cell(self.match, self.first, self.free_cell())

        submit_board_answer(self.match, self.first, cell, "мимо")

        self.me.refresh_from_db()
        self.match.refresh_from_db()
        self.assertEqual(self.me.score, -cell.points)
        self.assertEqual(self.match.turn_participant_id, self.rival.pk)

    def test_score_may_go_below_zero(self):
        cell = pick_cell(self.match, self.first, self.free_cell())
        submit_board_answer(self.match, self.first, cell, "мимо")

        self.me.refresh_from_db()
        self.assertLess(self.me.score, 0)

    def test_silence_costs_the_turn_but_not_points(self):
        cell = pick_cell(self.match, self.first, self.free_cell())
        backdate(cell, 31)

        advance(self.match)

        cell.refresh_from_db()
        self.me.refresh_from_db()
        self.match.refresh_from_db()
        self.assertIsNotNone(cell.resolved_at)
        self.assertIsNone(cell.resolved_by)
        self.assertEqual(self.me.score, 0)
        self.assertEqual(self.match.turn_participant_id, self.rival.pk)

    def test_a_taken_cell_cannot_be_picked_again(self):
        cell = pick_cell(self.match, self.first, self.free_cell())
        submit_board_answer(self.match, self.first, cell, cell.correct_answer)

        with self.assertRaises(ValidationError):
            pick_cell(self.match, self.first, cell)

    def test_two_open_cells_are_impossible(self):
        pick_cell(self.match, self.first, self.free_cell())

        with self.assertRaises(ValidationError):
            pick_cell(self.match, self.first, self.free_cell())

    def test_rival_cannot_answer_someone_elses_cell(self):
        cell = pick_cell(self.match, self.first, self.free_cell())

        with self.assertRaises(ValidationError):
            submit_board_answer(self.match, self.second, cell, cell.correct_answer)

    def test_board_ends_when_the_cells_run_out(self):
        MatchQuestion.objects.filter(match=self.match).exclude(
            pk=self.free_cell().pk
        ).update(resolved_at=timezone.now())
        cell = pick_cell(self.match, self.first, self.free_cell())

        submit_board_answer(self.match, self.first, cell, cell.correct_answer)

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.Status.FINISHED)


class BoardReboundTests(TestCase):
    """Ошибка отдаёт клетку сопернику вместе с ответом."""

    def setUp(self):
        self.first = make_student("rebound-one")
        self.second = make_student("rebound-two")
        make_theory()
        befriend(self.first, self.second)
        self.match = create_match(
            self.first, mode=Match.Mode.BOARD, opponent=self.second
        )
        accept_match(self.match, self.second)
        sit_down(self.match, self.first, self.second)
        self.me = participant_for(self.match, self.first)
        self.rival = participant_for(self.match, self.second)
        self.cell = pick_cell(self.match, self.first, self.match.questions.first())

    def miss(self):
        submit_board_answer(self.match, self.first, self.cell, "мимо")
        self.cell.refresh_from_db()
        self.match.refresh_from_db()

    def test_miss_hands_the_cell_over_instead_of_burning_it(self):
        self.miss()

        self.assertIsNone(self.cell.resolved_at)
        self.assertEqual(self.cell.rebound_by_id, self.rival.pk)
        self.assertEqual(self.match.turn_participant_id, self.rival.pk)

    def test_rival_sees_the_wrong_answer(self):
        self.miss()
        self.client.force_login(self.second.user)

        state = self.client.get(f"/api/arena/matches/{self.match.id}/").json()

        self.assertTrue(state["board"]["open"]["rebound"])
        self.assertTrue(state["board"]["open"]["mine"])
        self.assertEqual(state["board"]["open"]["wrong_answer"]["answer"], "мимо")
        self.assertFalse(state["board"]["open"]["wrong_answer"]["is_correct"])
        self.assertIn("мимо", state["board"]["open"]["rebound_note"])

    def test_the_first_one_cannot_answer_twice(self):
        self.miss()

        with self.assertRaises(ValidationError):
            submit_board_answer(self.match, self.first, self.cell, self.cell.correct_answer)

    def test_successful_rebound_takes_the_price(self):
        self.miss()

        submit_board_answer(self.match, self.second, self.cell, self.cell.correct_answer)

        self.cell.refresh_from_db()
        self.rival.refresh_from_db()
        self.me.refresh_from_db()
        self.match.refresh_from_db()
        self.assertEqual(self.cell.resolved_by_id, self.rival.pk)
        self.assertEqual(self.rival.score, self.cell.points)
        self.assertEqual(self.me.score, -self.cell.points)
        self.assertEqual(self.match.turn_participant_id, self.rival.pk)

    def test_both_wrong_costs_both_and_leaves_the_turn_to_the_second(self):
        self.miss()

        submit_board_answer(self.match, self.second, self.cell, "тоже мимо")

        self.cell.refresh_from_db()
        self.me.refresh_from_db()
        self.rival.refresh_from_db()
        self.match.refresh_from_db()
        self.assertIsNotNone(self.cell.resolved_at)
        self.assertIsNone(self.cell.resolved_by)
        self.assertEqual(self.me.score, -self.cell.points)
        self.assertEqual(self.rival.score, -self.cell.points)
        # Ход остаётся за тем, кто отвечал вторым.
        self.assertEqual(self.match.turn_participant_id, self.rival.pk)

    def test_rebound_gets_its_own_timer(self):
        self.miss()
        # Первый таймер давно истёк, но перехват получил свои полминуты.
        MatchQuestion.objects.filter(pk=self.cell.pk).update(
            opened_at=timezone.now() - timedelta(seconds=120)
        )

        advance(self.match)

        self.cell.refresh_from_db()
        self.assertIsNone(self.cell.resolved_at)

    def test_silent_rebound_burns_the_cell_and_keeps_the_turn(self):
        self.miss()
        MatchQuestion.objects.filter(pk=self.cell.pk).update(
            rebound_at=timezone.now() - timedelta(seconds=31)
        )

        advance(self.match)

        self.cell.refresh_from_db()
        self.match.refresh_from_db()
        self.assertIsNotNone(self.cell.resolved_at)
        self.assertIsNone(self.cell.resolved_by)
        self.assertEqual(self.match.turn_participant_id, self.rival.pk)

    def test_silence_of_the_first_is_not_a_rebound(self):
        # Молчание — не ответ: передавать сопернику нечего.
        backdate(self.cell, 31)

        advance(self.match)

        self.cell.refresh_from_db()
        self.match.refresh_from_db()
        self.assertIsNotNone(self.cell.resolved_at)
        self.assertIsNone(self.cell.rebound_by_id)
        self.assertEqual(self.match.turn_participant_id, self.rival.pk)

    def test_played_cells_show_both_answers(self):
        self.miss()
        submit_board_answer(self.match, self.second, self.cell, "тоже мимо")
        self.client.force_login(self.first.user)

        log = self.client.get(f"/api/arena/matches/{self.match.id}/").json()["board"]["log"]

        self.assertEqual(len(log), 1)
        self.assertEqual(len(log[0]["answers"]), 2)
        self.assertTrue(log[0]["correct_answer"])


class BoardBotReboundTests(TestCase):
    """Бот перехватывает и отдаёт перехват по заранее разыгранному знанию."""

    def setUp(self):
        self.student = make_student("rebound-bot")
        make_theory()
        self.match = create_match(self.student, mode=Match.Mode.BOARD, bot_level=3)
        sit_down(self.match, self.student)
        self.bot = self.match.participants.get(is_bot=True)
        self.me = participant_for(self.match, self.student)

    def test_bot_takes_the_rebound_when_it_knows(self):
        cell = self.match.questions.first()
        MatchQuestion.objects.filter(pk=cell.pk).update(
            bot_correct=True, bot_time_ms=1000
        )
        cell.refresh_from_db()
        pick_cell(self.match, self.student, cell)
        submit_board_answer(self.match, self.student, cell, "мимо")
        MatchQuestion.objects.filter(pk=cell.pk).update(
            rebound_at=timezone.now() - timedelta(seconds=3)
        )

        advance(self.match)

        cell.refresh_from_db()
        self.bot.refresh_from_db()
        self.assertEqual(cell.resolved_by_id, self.bot.pk)
        self.assertEqual(self.bot.score, cell.points)

    def test_bot_that_does_not_know_loses_points_too(self):
        cell = self.match.questions.first()
        MatchQuestion.objects.filter(pk=cell.pk).update(
            bot_correct=False, bot_time_ms=1000
        )
        cell.refresh_from_db()
        pick_cell(self.match, self.student, cell)
        submit_board_answer(self.match, self.student, cell, "мимо")
        MatchQuestion.objects.filter(pk=cell.pk).update(
            rebound_at=timezone.now() - timedelta(seconds=3)
        )

        advance(self.match)

        cell.refresh_from_db()
        self.bot.refresh_from_db()
        self.match.refresh_from_db()
        self.assertIsNone(cell.resolved_by)
        self.assertEqual(self.bot.score, -cell.points)
        self.assertEqual(self.match.turn_participant_id, self.bot.pk)

    def test_bot_miss_is_visible_to_the_player(self):
        # Какую клетку выберет бот, решает его стратегия, поэтому «не знаю»
        # ставим всей доске.
        self.match.questions.update(bot_correct=False, bot_time_ms=0)
        self.match.turn_participant = self.bot
        self.match.save(update_fields=["turn_participant"])

        advance(self.match)
        self.client.force_login(self.student.user)
        state = self.client.get(f"/api/arena/matches/{self.match.id}/").json()

        # Бот ошибся вслух: игрок видит его ответ и перехватывает клетку.
        self.assertTrue(state["board"]["open"]["rebound"])
        self.assertTrue(state["board"]["open"]["wrong_answer"]["answer"])
        self.assertFalse(state["board"]["open"]["wrong_answer"]["is_me"])
        self.assertTrue(state["board"]["open"]["mine"])


class BoardBotTests(TestCase):
    def setUp(self):
        self.student = make_student("board-bot")
        make_theory()

    def match_with(self, level: int) -> Match:
        match = create_match(self.student, mode=Match.Mode.BOARD, bot_level=level)
        return sit_down(match, self.student)

    def test_strong_bot_starts_with_the_expensive_cells(self):
        match = self.match_with(5)
        cells = list(match.questions.all())

        picked = choose_cell(cells, 5, seed=1)

        self.assertEqual(picked.points, max(cell.points for cell in cells))

    def test_weak_bot_starts_with_the_cheap_ones(self):
        match = self.match_with(1)
        cells = list(match.questions.all())

        picked = choose_cell(cells, 1, seed=1)

        self.assertEqual(picked.points, min(cell.points for cell in cells))

    def test_bot_picks_and_answers_on_its_turn(self):
        match = self.match_with(3)
        bot = match.participants.get(is_bot=True)
        match.turn_participant = bot
        match.save(update_fields=["turn_participant"])
        match.questions.update(bot_correct=True, bot_time_ms=1000)

        advance(match)
        cell = open_cell(match)
        self.assertIsNotNone(cell)
        backdate(cell, 3)
        advance(match)

        bot.refresh_from_db()
        self.assertGreater(bot.score, 0)

    def test_bot_keeps_the_turn_after_a_correct_answer(self):
        match = self.match_with(3)
        bot = match.participants.get(is_bot=True)
        match.turn_participant = bot
        match.save(update_fields=["turn_participant"])
        match.questions.update(bot_correct=True, bot_time_ms=0)

        advance(match)
        match.refresh_from_db()

        # Бот, который знает ответ, продолжает выбирать — как в телеигре.
        self.assertEqual(match.turn_participant_id, bot.pk)

    def test_bot_mistake_returns_the_turn_to_the_player(self):
        match = self.match_with(3)
        bot = match.participants.get(is_bot=True)
        me = match.participants.get(student=self.student)
        match.turn_participant = bot
        match.save(update_fields=["turn_participant"])
        match.questions.update(bot_correct=False, bot_time_ms=0)

        advance(match)
        match.refresh_from_db()

        self.assertEqual(match.turn_participant_id, me.pk)


class MatchStateApiTests(TestCase):
    """Состояние партии: соперник виден целиком во всех режимах."""

    def setUp(self):
        self.student = make_student("state-player")
        make_pool(count=30)
        make_theory()
        self.client.force_login(self.student.user)

    def state(self, match) -> dict:
        return self.client.get(f"/api/arena/matches/{match.id}/").json()

    def started(self, **kwargs) -> Match:
        match = create_match(self.student, **kwargs)
        return sit_down(match, self.student)

    def test_speed_state_shows_the_rival_card(self):
        match = self.started(mode=Match.Mode.SPEED, bot_level=2)

        rival = self.state(match)["opponent"]

        self.assertTrue(rival["is_bot"])
        for key in ("title", "letter", "avatar", "frame", "score", "answered"):
            self.assertIn(key, rival)

    def test_quiz_state_carries_the_open_question(self):
        match = self.started(mode=Match.Mode.QUIZ, bot_level=2)

        quiz = self.state(match)["quiz"]

        self.assertEqual(len(quiz["question"]["options"]), 4)
        self.assertLessEqual(quiz["question"]["seconds_left"], 30)
        self.assertFalse(quiz["locked"])

    def test_board_state_carries_the_grid(self):
        match = self.started(mode=Match.Mode.BOARD, bot_level=2)

        board = self.state(match)["board"]

        self.assertGreaterEqual(len(board["columns"]), 3)
        self.assertEqual(board["turn"], "me")
        self.assertIsNone(board["open"])
        self.assertTrue(
            all(cell["state"] == "free" for column in board["columns"]
                for cell in column["cells"])
        )

    def test_board_pick_and_answer_through_the_api(self):
        match = self.started(mode=Match.Mode.BOARD, bot_level=2)
        cell = match.questions.first()

        picked = self.client.post(
            f"/api/arena/matches/{match.id}/pick/",
            {"question_id": cell.pk}, content_type="application/json",
        )
        self.assertEqual(picked.status_code, 200)
        self.assertIsNotNone(picked.json()["board"]["open"])

        answered = self.client.post(
            f"/api/arena/matches/{match.id}/board/",
            {"question_id": cell.pk, "answer": cell.correct_answer},
            content_type="application/json",
        )

        self.assertEqual(answered.status_code, 200)
        self.assertTrue(answered.json()["last_answer"]["is_correct"])
        self.assertEqual(answered.json()["me"]["score"], cell.points)

    def test_quiz_answer_through_the_api(self):
        match = self.started(mode=Match.Mode.QUIZ, bot_level=1)
        match.questions.update(bot_time_ms=60_000)
        question = open_question(match)
        index = next(
            i for i, option in enumerate(question.options)
            if question.check_answer(str(option))
        )

        response = self.client.post(
            f"/api/arena/matches/{match.id}/quiz/",
            {"question_id": question.pk, "option": index},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["last_answer"]["is_correct"])

    def test_late_click_gets_a_refusal_and_a_fresh_state(self):
        match = self.started(mode=Match.Mode.QUIZ, bot_level=5)
        question = open_question(match)
        MatchQuestion.objects.filter(pk=question.pk).update(
            bot_correct=True, bot_time_ms=1000
        )
        backdate(question, 3)

        response = self.client.post(
            f"/api/arena/matches/{match.id}/quiz/",
            {"question_id": question.pk, "option": 0},
            content_type="application/json",
        )

        # Отказ — нормальный ход игры: вопрос забрал соперник. Клиент получает
        # актуальное состояние, а не пустую ошибку.
        self.assertEqual(response.status_code, 409)
        self.assertIn("detail", response.json())
        self.assertIn("quiz", response.json())

    def test_time_mode_starts_the_clock_through_the_api(self):
        match = create_match(
            self.student, mode=Match.Mode.SPEED, bot_level=2,
            limit_kind=Match.Limit.TIME, time_limit_seconds=120,
        )

        response = self.client.post(f"/api/arena/matches/{match.id}/join/")

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(response.json()["seconds_left"], 120)
        self.assertIsNotNone(participant_for(match, self.student).started_at)
