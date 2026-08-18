"""Правила арены: дружба, создание партии, подсчёт результата, награда."""

from __future__ import annotations

import random

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.content.models import Assignment
from apps.practice.models import Attempt

from .bot import bot_run, clamp_level
from .models import Friendship, Match, MatchAnswer, MatchParticipant, MatchQuestion

QUESTION_COUNTS = {Match.Mode.SPEED: 8, Match.Mode.QUIZ: 5, Match.Mode.BOARD: 6}
# Цена вопроса в «своей игре»: чем сложнее задача, тем дороже клетка.
BOARD_POINTS = {1: 100, 2: 200, 3: 300, 4: 400, 5: 500}
FLAT_POINTS = 100
# Награда за партию. Небольшая и с потолком: арена не должна становиться
# способом добывать сигмы вместо занятий.
XP_FOR_PLAYING = 15
XP_FOR_WIN = 25
COINS_FOR_WIN = 10
DAILY_REWARDED_MATCHES = 5


# --- Друзья ---

def friends_of(student):
    """Принятые друзья ученика — заявка могла идти в любую сторону."""
    from apps.accounts.models import StudentProfile

    accepted = Friendship.objects.filter(
        status=Friendship.Status.ACCEPTED
    ).filter(models.Q(from_student=student) | models.Q(to_student=student))
    ids = [
        row.to_student_id if row.from_student_id == student.pk else row.from_student_id
        for row in accepted
    ]
    return StudentProfile.objects.filter(pk__in=ids).select_related("user")


def existing_friendship(first, second) -> Friendship | None:
    return (
        Friendship.objects.filter(from_student=first, to_student=second).first()
        or Friendship.objects.filter(from_student=second, to_student=first).first()
    )


def are_friends(first, second) -> bool:
    link = existing_friendship(first, second)
    return link is not None and link.status == Friendship.Status.ACCEPTED


@transaction.atomic
def send_friend_request(student, other) -> Friendship:
    """Позвать в друзья. Повторная заявка не создаёт вторую запись."""
    if student.pk == other.pk:
        raise ValidationError("Нельзя добавить в друзья самого себя.")
    link = existing_friendship(student, other)
    if link is not None:
        if link.status == Friendship.Status.ACCEPTED:
            return link
        # Встречная заявка — это согласие: оба уже захотели дружить.
        if link.status == Friendship.Status.PENDING and link.to_student_id == student.pk:
            return accept_friend_request(link, student)
        link.from_student, link.to_student = student, other
        link.status = Friendship.Status.PENDING
        link.answered_at = None
        link.save(update_fields=["from_student", "to_student", "status", "answered_at"])
        return link
    return Friendship.objects.create(from_student=student, to_student=other)


@transaction.atomic
def accept_friend_request(link: Friendship, student) -> Friendship:
    if link.to_student_id != student.pk:
        raise ValidationError("Эту заявку принимает другой человек.")
    link.status = Friendship.Status.ACCEPTED
    link.answered_at = timezone.now()
    link.save(update_fields=["status", "answered_at"])
    return link


@transaction.atomic
def decline_friend_request(link: Friendship, student) -> Friendship:
    if link.to_student_id != student.pk:
        raise ValidationError("Эту заявку отклоняет другой человек.")
    link.status = Friendship.Status.DECLINED
    link.answered_at = timezone.now()
    link.save(update_fields=["status", "answered_at"])
    return link


# --- Партия ---

def question_pool(ege_task_number: int | None = None):
    """Задачи для партии: короткий ответ, который платформа умеет проверить."""
    pool = Assignment.objects.filter(exam_part=Assignment.Part.PART1).exclude(
        correct_answer=""
    )
    if ege_task_number:
        # Номера лежат списком в JSON, а `contains` по JSON есть не во всех
        # базах (в SQLite нет). Отбираем узлы в Python: их сотни, не миллионы.
        from apps.knowledge.models import KnowledgeNode

        node_ids = [
            node.pk
            for node in KnowledgeNode.objects.only("id", "ege_task_numbers")
            if ege_task_number in (node.ege_task_numbers or [])
        ]
        pool = pool.filter(skill_tags__node_id__in=node_ids)
    return pool.distinct()


def _points_for(mode: str, assignment) -> int:
    if mode == Match.Mode.BOARD:
        return BOARD_POINTS.get(int(assignment.difficulty), FLAT_POINTS)
    return FLAT_POINTS


@transaction.atomic
def create_match(student, *, mode: str, opponent=None, bot_level: int | None = None,
                 ege_task_number: int | None = None,
                 seconds_per_question: int = 90, ranked: bool = False) -> Match:
    """Создать партию против друга или бота.

    Набор задач общий для обеих сторон: сравнивать результаты, полученные на
    разных задачах, бессмысленно.
    """
    if opponent is None and bot_level is None:
        raise ValidationError("Нужен соперник: друг или бот.")
    if opponent is not None:
        if opponent.pk == student.pk:
            raise ValidationError("Нельзя играть против себя.")
        # Вызвать напрямую можно только друга; случайного соперника выдаёт
        # очередь подбора, и там знакомство не требуется.
        if not ranked and not are_friends(student, opponent):
            raise ValidationError(
                "Играть можно с друзьями — сначала добавьте друг друга."
            )

    count = QUESTION_COUNTS.get(mode, QUESTION_COUNTS[Match.Mode.SPEED])
    pool = list(question_pool(ege_task_number)[: count * 4])
    if len(pool) < count:
        raise ValidationError("Для такой партии пока не хватает задач.")
    chosen = random.sample(pool, count)

    match = Match.objects.create(
        mode=mode,
        created_by=student,
        bot_level=clamp_level(bot_level) if bot_level is not None else None,
        ege_task_number=ege_task_number,
        seconds_per_question=seconds_per_question,
        is_ranked=ranked,
        status=Match.Status.ACTIVE if bot_level is not None else Match.Status.INVITED,
        started_at=timezone.now(),
    )
    for order, assignment in enumerate(chosen, start=1):
        MatchQuestion.objects.create(
            match=match, order=order, assignment=assignment,
            points=_points_for(mode, assignment),
        )

    MatchParticipant.objects.create(match=match, student=student)
    if bot_level is not None:
        bot = MatchParticipant.objects.create(match=match, is_bot=True)
        play_bot(match, bot)
    else:
        MatchParticipant.objects.create(match=match, student=opponent)
    return match


def play_bot(match: Match, participant: MatchParticipant) -> None:
    """Разыграть партию бота сразу и целиком.

    Так соперник не подстраивается под человека: его результат существует ещё
    до того, как человек ответил на первый вопрос.
    """
    questions = list(match.questions.select_related("assignment"))
    score = correct = total_time = 0
    for row in bot_run(questions, match.bot_level, seed=match.pk * 7919):
        MatchAnswer.objects.create(
            participant=participant, question=row["question"],
            is_correct=row["is_correct"], time_ms=row["time_ms"],
        )
        total_time += row["time_ms"]
        if row["is_correct"]:
            correct += 1
            score += row["question"].points
    participant.score = score
    participant.correct_count = correct
    participant.total_time_ms = total_time
    participant.finished_at = timezone.now()
    participant.save(
        update_fields=["score", "correct_count", "total_time_ms", "finished_at"]
    )


def participant_for(match: Match, student) -> MatchParticipant | None:
    return match.participants.filter(student=student).first()


def opponent_of(match: Match, student) -> MatchParticipant | None:
    return match.participants.exclude(student=student).first()


def next_question(match: Match, participant: MatchParticipant) -> MatchQuestion | None:
    """Следующий неотвеченный вопрос участника."""
    answered = set(participant.answers.values_list("question_id", flat=True))
    return match.questions.exclude(pk__in=answered).select_related("assignment").first()


@transaction.atomic
def accept_match(match: Match, student) -> Match:
    """Принять вызов друга: до этого партия ждёт согласия."""
    if participant_for(match, student) is None or match.created_by_id == student.pk:
        raise ValidationError("Этот вызов адресован другому человеку.")
    if match.status != Match.Status.INVITED:
        return match
    match.status = Match.Status.ACTIVE
    match.started_at = timezone.now()
    match.save(update_fields=["status", "started_at"])
    return match


@transaction.atomic
def decline_match(match: Match, student) -> Match:
    if participant_for(match, student) is None or match.created_by_id == student.pk:
        raise ValidationError("Этот вызов адресован другому человеку.")
    match.status = Match.Status.DECLINED
    match.finished_at = timezone.now()
    match.save(update_fields=["status", "finished_at"])
    return match


@transaction.atomic
def submit_answer(match: Match, student, question: MatchQuestion, answer: str,
                  elapsed_ms: int) -> MatchAnswer:
    """Записать ответ игрока и, если вопросы кончились, закрыть его партию."""
    participant = participant_for(match, student)
    if participant is None:
        raise ValidationError("Вы не участник этой партии.")
    if match.status == Match.Status.INVITED and match.created_by_id != student.pk:
        raise ValidationError("Сначала примите вызов.")
    if match.status in (Match.Status.FINISHED, Match.Status.DECLINED):
        raise ValidationError("Партия уже завершена.")
    if participant.finished_at is not None:
        raise ValidationError("Вы уже закончили эту партию.")
    if participant.answers.filter(question=question).exists():
        raise ValidationError("На этот вопрос вы уже ответили.")

    verdict = question.assignment.check_answer(answer)
    is_correct = bool(verdict)
    # Время ограничено правилом партии: клиент может прислать что угодно, но
    # преимущества «нулевым» временем не получит.
    limit = match.seconds_per_question * 1000
    time_ms = max(0, min(int(elapsed_ms or 0), limit))

    record = MatchAnswer.objects.create(
        participant=participant, question=question, submitted_answer=answer[:300],
        is_correct=is_correct, time_ms=time_ms,
    )
    participant.total_time_ms += time_ms
    if is_correct:
        participant.correct_count += 1
        participant.score += question.points
    participant.save(update_fields=["total_time_ms", "correct_count", "score"])

    # Ответ попадает в общий журнал попыток, но освоение не двигает: скорость
    # под таймером — свидетельство собранности, а не понимания темы.
    Attempt.objects.create(
        student=student, assignment=question.assignment,
        context=Attempt.Context.ARENA, submitted_answer=answer[:200],
        is_correct=is_correct,
    )

    if next_question(match, participant) is None:
        finish_participant(match, participant)
    return record


@transaction.atomic
def finish_participant(match: Match, participant: MatchParticipant) -> MatchParticipant:
    """Закрыть партию для участника и, если закончили все, — всю партию."""
    if participant.finished_at is None:
        participant.finished_at = timezone.now()
        participant.save(update_fields=["finished_at"])
    if not match.participants.filter(finished_at__isnull=True).exists():
        finish_match(match)
    return participant


def rank(match: Match) -> list[MatchParticipant]:
    """Итог: больше очков, при равенстве — меньше времени."""
    return sorted(
        match.participants.select_related("student__user"),
        key=lambda participant: (-participant.score, participant.total_time_ms),
    )


def winner_of(match: Match) -> MatchParticipant | None:
    """Победитель или None при полной ничьей: очки и время совпали."""
    table = rank(match)
    if len(table) < 2:
        return table[0] if table else None
    first, second = table[0], table[1]
    if (first.score, first.total_time_ms) == (second.score, second.total_time_ms):
        return None
    return first


@transaction.atomic
def finish_match(match: Match) -> Match:
    if match.status == Match.Status.FINISHED:
        return match
    match.status = Match.Status.FINISHED
    match.finished_at = timezone.now()
    match.save(update_fields=["status", "finished_at"])
    from .matchmaking import apply_rating

    apply_rating(match)
    champion = winner_of(match)
    for participant in match.participants.all():
        if participant.student_id is None:
            continue
        _reward(
            match, participant,
            won=champion is not None and champion.pk == participant.pk,
        )
    return match


def rewarded_today(student) -> int:
    from apps.events.models import Event

    return Event.objects.filter(
        student=student,
        event_type=Event.Type.ARENA_MATCH_FINISHED,
        created_at__date=timezone.localdate(),
    ).count()


def _reward(match: Match, participant: MatchParticipant, *, won: bool) -> None:
    """Награда за партию: небольшая, с дневным потолком.

    Без потолка арена станет способом добывать сигмы вместо занятий — а она
    нужна, чтобы возвращать к занятиям, а не заменять их.
    """
    from apps.economy.models import LedgerEntry
    from apps.economy.services import grant
    from apps.events.models import Event
    from apps.events.services import log_event
    from apps.gamification.services import award_xp

    student = participant.student
    if rewarded_today(student) >= DAILY_REWARDED_MATCHES:
        log_event(
            Event.Type.ARENA_MATCH_FINISHED, student=student, match_id=match.pk,
            score=participant.score, won=won, rewarded=False,
        )
        return

    award_xp(student, XP_FOR_WIN if won else XP_FOR_PLAYING, source="arena_match")
    if won:
        grant(
            student, COINS_FOR_WIN, LedgerEntry.Reason.XP_AWARD,
            reference=f"match:{match.pk}", comment="Победа в партии",
        )
    log_event(
        Event.Type.ARENA_MATCH_FINISHED, student=student, match_id=match.pk,
        score=participant.score, won=won, rewarded=True,
    )
