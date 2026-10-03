"""Правила арены: дружба, три режима партии, подсчёт результата, награда.

Режимы устроены по-разному, и это осознанно:

* **нарешивание** — гонка по задачам. Оба играют одновременно, каждый в своём
  темпе; побеждает тот, кто решил больше (или быстрее — смотря какой лимит);
* **квиз** — гонка по одному общему вопросу: четыре варианта, забирает тот, кто
  первым нажал верный. Промах не штрафуется очками, но лишает права ответа;
* **своя игра** — ход по очереди. Игрок выбирает клетку, отвечает за 30 секунд,
  верный ответ приносит цену клетки, неверный её списывает и передаёт ход.

Общее правило одно: считает сервер. Клиент присылает выбранный вариант или
текст ответа, всё остальное — время, очки, чей ход, кто успел раньше —
вычисляется здесь. Иначе первая же партия превратится в состязание по правке
JavaScript.
"""

from __future__ import annotations

import random

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.content.models import Assignment, TheoryQuestion
from apps.practice.models import Attempt

from .bot import bot_run, choose_cell, clamp_level, theory_run
from .models import Friendship, Match, MatchAnswer, MatchParticipant, MatchQuestion

QUESTION_COUNTS = {Match.Mode.SPEED: 8, Match.Mode.QUIZ: 6, Match.Mode.BOARD: 6}
# Нарешивание «на время»: банк берётся с запасом — сколько успеешь, столько
# и твоё. Лимит по умолчанию — три минуты.
SPEED_TIME_POOL = 24
MIN_SPEED_TIME_POOL = 6
DEFAULT_TIME_LIMIT = 180
# Теория отвечается быстро, поэтому у неё свой таймер: полминуты на вопрос.
THEORY_SECONDS = 30
# Доска «своей игры»: пять тем по пять цен.
BOARD_COLUMNS = 5
BOARD_PRICES = (100, 200, 300, 400, 500)
MIN_BOARD_CELLS = 6
# Цена вопроса в квизе и в нарешивании — одинаковая: там решает скорость,
# а не сложность.
FLAT_POINTS = 100
# Сколько ждём игрока, который согласился, но так и не открыл экран. После
# этого партия отменяется: висящий вызов хуже отсутствующего.
LOBBY_TTL_SECONDS = 300
# Сколько партия ждёт молчащего игрока, прежде чем счесть, что он ушёл.
# Экран отмечается каждые пару секунд, так что минута — это уже закрытая
# вкладка, а не задержка сети.
ABSENT_SECONDS = 60
# Сколько задач можно заказать в нарешивании «до набора».
MIN_QUESTION_COUNT, MAX_QUESTION_COUNT = 4, 20
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


# --- Банк вопросов ---

def question_pool(ege_task_number: int | None = None):
    """Задачи для партии: короткий ответ, который платформа умеет проверить."""
    pool = Assignment.objects.filter(
        exam_part=Assignment.Part.PART1,
        arena_enabled=True,
    ).exclude(correct_answer="")
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


def theory_pool(*, with_options: bool = False):
    """Вопросы по теории. Для квиза нужны те, у которых есть четыре варианта."""
    pool = TheoryQuestion.objects.filter(is_active=True).select_related("cluster")
    if with_options:
        # Наличие вариантов проверяем в Python: JSON-длина в SQLite не ищется.
        return [row for row in pool if len(row.options or []) == 4]
    return list(pool)


# --- Сборка партии ---

def clamp_question_count(count: int | None) -> int:
    """Сколько задач в партии. По умолчанию — восемь: партия на перемену."""
    if not count:
        return QUESTION_COUNTS[Match.Mode.SPEED]
    return max(MIN_QUESTION_COUNT, min(MAX_QUESTION_COUNT, int(count)))


def _build_speed(match: Match, ege_task_number: int | None,
                 question_count: int | None = None) -> None:
    """Набор задач для нарешивания. В режиме «на время» банк берётся с запасом."""
    on_time = match.limit_kind == Match.Limit.TIME
    count = SPEED_TIME_POOL if on_time else clamp_question_count(question_count)
    pool = list(question_pool(ege_task_number)[: count * 4])
    # На время банк берётся с запасом, но требовать полный запас нельзя:
    # партия кончается по таймеру, а не по последней задаче.
    if len(pool) < (MIN_SPEED_TIME_POOL if on_time else count):
        raise ValidationError("Для такой партии пока не хватает задач.")
    chosen = random.sample(pool, min(count, len(pool)))
    for order, assignment in enumerate(chosen, start=1):
        MatchQuestion.objects.create(
            match=match, order=order, assignment=assignment, points=FLAT_POINTS,
            topic_title=getattr(
                getattr(assignment.lesson, "node", None), "title", ""
            ) or assignment.title,
        )


def _build_quiz(match: Match, rng: random.Random) -> None:
    """Шесть вопросов по теории, у каждого — четыре варианта.

    Порядок вариантов фиксируется здесь и хранится в партии: оба игрока должны
    видеть одно и то же, иначе «кто первый нажал» ничего не значит.
    """
    pool = theory_pool(with_options=True)
    if len(pool) < QUESTION_COUNTS[Match.Mode.QUIZ]:
        raise ValidationError("Для квиза пока не хватает вопросов по теории.")
    chosen = _spread_by_cluster(pool, QUESTION_COUNTS[Match.Mode.QUIZ], rng)
    for order, question in enumerate(chosen, start=1):
        options = list(question.options)
        rng.shuffle(options)
        MatchQuestion.objects.create(
            match=match, order=order, theory=question, points=FLAT_POINTS,
            options=options, topic_title=question.cluster.title,
        )


def _spread_by_cluster(pool: list, count: int, rng: random.Random) -> list:
    """Разложить вопросы по разным темам: квиз из шести вопросов об одном
    и том же — это не квиз, а опрос по одной теме."""
    by_cluster: dict[int, list] = {}
    for question in pool:
        by_cluster.setdefault(question.cluster_id, []).append(question)
    order = list(by_cluster)
    rng.shuffle(order)
    chosen: list = []
    while len(chosen) < count and order:
        for cluster_id in list(order):
            bucket = by_cluster[cluster_id]
            if not bucket:
                order.remove(cluster_id)
                continue
            chosen.append(bucket.pop(rng.randrange(len(bucket))))
            if len(chosen) == count:
                break
    return chosen


def _build_board(match: Match, rng: random.Random) -> None:
    """Доска «своей игры»: до пяти случайных тем, в каждой цены от 100 до 500.

    Цена клетки — это сложность вопроса, а не украшение: за 500 спрашивают то,
    что знает не каждый. Если в теме нет вопроса нужной сложности, берётся
    ближайший по сложности, а если и его нет — клетка на доске не появляется.
    """
    by_cluster: dict[int, list] = {}
    for question in theory_pool():
        by_cluster.setdefault(question.cluster_id, []).append(question)
    clusters = [ids for ids, rows in by_cluster.items() if rows]
    rng.shuffle(clusters)
    clusters = clusters[:BOARD_COLUMNS]

    order = 0
    for column, cluster_id in enumerate(clusters):
        bucket = list(by_cluster[cluster_id])
        for price in BOARD_PRICES:
            wanted = price // 100
            fitting = [row for row in bucket if row.difficulty == wanted]
            if not fitting:
                fitting = sorted(bucket, key=lambda row: abs(row.difficulty - wanted))[:1]
            if not fitting:
                continue
            question = fitting[rng.randrange(len(fitting))]
            bucket.remove(question)
            order += 1
            MatchQuestion.objects.create(
                match=match, order=order, theory=question, points=price,
                column=column, topic_title=question.cluster.title,
            )
    if match.questions.count() < MIN_BOARD_CELLS:
        raise ValidationError("Для «своей игры» пока не хватает вопросов по теории.")


@transaction.atomic
def create_match(student, *, mode: str, opponent=None, bot_level: int | None = None,
                 ege_task_number: int | None = None,
                 seconds_per_question: int = 90, ranked: bool = False,
                 limit_kind: str = Match.Limit.QUESTIONS,
                 time_limit_seconds: int | None = None,
                 question_count: int | None = None) -> Match:
    """Создать партию против друга или бота.

    Набор вопросов общий для обеих сторон: сравнивать результаты, полученные на
    разных вопросах, бессмысленно.
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

    # Профили создаются на границе создания партии, чтобы страницы списков
    # могли только пакетно читать их и не писать в базу во время GET.
    from .matchmaking import get_profile

    get_profile(student)
    if opponent is not None:
        get_profile(opponent)

    theory = mode in (Match.Mode.QUIZ, Match.Mode.BOARD)
    if theory:
        # У теории свой таймер и свой счёт: лимит «на время» к ней неприменим.
        limit_kind, time_limit_seconds = Match.Limit.QUESTIONS, 0
        seconds_per_question = THEORY_SECONDS
    elif limit_kind == Match.Limit.TIME:
        time_limit_seconds = int(time_limit_seconds or DEFAULT_TIME_LIMIT)

    match = Match.objects.create(
        mode=mode,
        created_by=student,
        bot_level=clamp_level(bot_level) if bot_level is not None else None,
        ege_task_number=ege_task_number,
        seconds_per_question=seconds_per_question,
        limit_kind=limit_kind,
        time_limit_seconds=int(time_limit_seconds or 0),
        is_ranked=ranked,
        # Партия не начинается в момент создания: сначала за стол должны сесть
        # оба. С ботом это одно нажатие, с человеком — согласие и вход.
        status=Match.Status.LOBBY if bot_level is not None else Match.Status.INVITED,
    )
    rng = random.Random(match.pk * 7919)
    if mode == Match.Mode.QUIZ:
        _build_quiz(match, rng)
    elif mode == Match.Mode.BOARD:
        _build_board(match, rng)
    else:
        _build_speed(match, ege_task_number, question_count)

    me = MatchParticipant.objects.create(match=match, student=student)
    if bot_level is not None:
        # Бот за столом всегда: ему нечего открывать.
        bot = MatchParticipant.objects.create(
            match=match, is_bot=True, joined_at=timezone.now()
        )
        play_bot(match, bot)
    else:
        MatchParticipant.objects.create(match=match, student=opponent)

    if mode == Match.Mode.BOARD:
        # Первый ход — за тем, кто позвал: вызов и есть заявка сыграть первым.
        match.turn_participant = me
        match.save(update_fields=["turn_participant"])
    return match


def play_bot(match: Match, participant: MatchParticipant) -> None:
    """Разыграть игру бота заранее и целиком.

    В нарешивании ответы записываются сразу: партия идёт параллельно, и
    результат бота не зависит от хода человека. В теории записывается
    расписание — «этот вопрос бот знает и ответит через N мс», — потому что там
    ходы общие и момент ответа важен. Оба варианта разыграны до первого хода
    человека: подстроиться бот не может.
    """
    questions = list(match.questions.select_related("assignment", "theory"))
    seed = match.pk * 7919
    if match.is_theory:
        for row in theory_run(questions, match.bot_level, seed, mode=match.mode):
            question = row["question"]
            question.bot_correct = row["is_correct"]
            question.bot_time_ms = row["time_ms"]
            question.save(update_fields=["bot_correct", "bot_time_ms"])
        return

    limit_ms = match.time_limit_seconds * 1000 if match.limit_kind == Match.Limit.TIME else None
    score = correct = total_time = 0
    for row in bot_run(questions, match.bot_level, seed=seed):
        # В режиме «на время» бот успевает ровно столько, сколько влезло в
        # лимит: остальные вопросы он просто не увидел, как и человек.
        if limit_ms is not None and total_time + row["time_ms"] > limit_ms:
            break
        MatchAnswer.objects.create(
            participant=participant, question=row["question"],
            is_correct=row["is_correct"], time_ms=row["time_ms"],
            points_delta=row["question"].points if row["is_correct"] else 0,
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


# --- Общие помощники ---

def participant_for(match: Match, student) -> MatchParticipant | None:
    return match.participants.filter(student=student).first()


def opponent_of(match: Match, student) -> MatchParticipant | None:
    return match.participants.exclude(student=student).first()


def bot_participant(match: Match) -> MatchParticipant | None:
    return match.participants.filter(is_bot=True).first()


def next_question(match: Match, participant: MatchParticipant) -> MatchQuestion | None:
    """Следующий неотвеченный вопрос участника (нарешивание)."""
    answered = set(participant.answers.values_list("question_id", flat=True))
    return match.questions.exclude(pk__in=answered).select_related("assignment").first()


def open_question(match: Match) -> MatchQuestion | None:
    """Текущий общий вопрос: в квизе — первый неразыгранный по порядку."""
    return (
        match.questions.filter(resolved_at__isnull=True)
        .select_related("theory")
        .order_by("order")
        .first()
    )


def open_cell(match: Match) -> MatchQuestion | None:
    """Открытая клетка «своей игры»: выбрана и ещё не разыграна."""
    return (
        match.questions.filter(resolved_at__isnull=True, opened_at__isnull=False)
        .select_related("theory", "picked_by", "rebound_by")
        .first()
    )


def _elapsed_ms(since) -> int:
    return int((timezone.now() - since).total_seconds() * 1000)


def _time_left(match: Match, question: MatchQuestion) -> int:
    """Сколько секунд осталось на открытый вопрос.

    У перехвата свои полминуты: соперник получает клетку уже с чужим ответом
    на руках, но думать ему тоже надо.
    """
    started = question.clock_from
    if started is None:
        return match.seconds_per_question
    left = match.seconds_per_question - _elapsed_ms(started) / 1000
    return max(0, int(round(left)))


def _pass_turn(match: Match) -> None:
    other = match.participants.exclude(pk=match.turn_participant_id).first()
    match.turn_participant = other
    match.save(update_fields=["turn_participant"])


def _resolve(question: MatchQuestion, participant: MatchParticipant | None) -> None:
    question.resolved_by = participant
    question.resolved_at = timezone.now()
    question.save(update_fields=["resolved_by", "resolved_at"])


def _score(participant: MatchParticipant, delta: int, *, correct: bool, time_ms: int) -> None:
    participant.score += delta
    participant.total_time_ms += max(0, time_ms)
    if correct:
        participant.correct_count += 1
    participant.save(update_fields=["score", "total_time_ms", "correct_count"])


def _open_next_quiz_question(match: Match) -> MatchQuestion | None:
    """Открыть следующий вопрос квиза и запустить его таймер."""
    question = open_question(match)
    if question is None:
        return None
    if question.opened_at is None:
        question.opened_at = timezone.now()
        question.save(update_fields=["opened_at"])
    return question


# --- Ход времени ---

def advance(match: Match) -> Match:
    """Продвинуть партию: закрыть просроченное и дать сходить боту.

    Отдельного «часовщика» у партии нет — время двигается на каждом обращении
    к ней. Это честно: и человек, и бот ограничены одними и теми же часами
    сервера, а решение бота («знаю» или «нет») разыграно заранее и от момента
    обращения не зависит.

    Подавляющее большинство обращений — это опрос экрана, при котором двигать
    нечего. Поэтому сначала дешёвая проверка «есть ли что делать», и только
    потом транзакция: открывать её на каждый опрос значит платить за запись
    там, где идёт чтение.
    """
    if not needs_advance(match):
        return match
    return _advance_locked(match)


@transaction.atomic
def _advance_locked(match: Match) -> Match:
    if match.is_waiting:
        expire_lobby(match)
        return match
    if match.status != Match.Status.ACTIVE:
        return match
    _drop_absent(match)
    match.refresh_from_db()
    if match.status != Match.Status.ACTIVE:
        return match
    if match.mode == Match.Mode.QUIZ:
        _advance_quiz(match)
    elif match.mode == Match.Mode.BOARD:
        _advance_board(match)
    else:
        _advance_speed(match)
    match.refresh_from_db()
    # Догонять больше нечем — партия окончена, даже если вопросы остались.
    if match.status == Match.Status.ACTIVE and outcome_decided(match):
        _finish_everyone(match)
    return match


def needs_advance(match: Match, now=None) -> bool:
    """Есть ли в партии что-то, что должно было случиться к этой секунде.

    Ответ считается по срокам, а не по данным целиком: истёк ли таймер вопроса,
    подошло ли время хода бота, кончились ли вопросы. Один-два лёгких запроса
    вместо полной сборки состояния.
    """
    now = now or timezone.now()
    if match.is_waiting:
        return (now - match.created_at).total_seconds() >= LOBBY_TTL_SECONDS
    if match.status != Match.Status.ACTIVE:
        return False
    # Пропажа игрока — тоже событие: партия заканчивается победой оставшегося.
    # Стоит это одного запроса и пары чтений кеша, зато закрытая вкладка не
    # оставляет соперника ждать вечно.
    if _absent_participants(match, now):
        return True
    if match.mode == Match.Mode.SPEED:
        if match.limit_kind != Match.Limit.TIME:
            return False
        deadline = now - timezone.timedelta(seconds=match.time_limit_seconds)
        return match.participants.filter(
            finished_at__isnull=True, started_at__lte=deadline
        ).exists()

    limit_ms = match.seconds_per_question * 1000
    if match.mode == Match.Mode.QUIZ:
        row = (
            match.questions.filter(resolved_at__isnull=True)
            .order_by("order")
            .values("opened_at", "bot_time_ms")
            .first()
        )
        if row is None or row["opened_at"] is None:
            # Вопросы кончились (пора закрывать партию) или следующий ещё не
            # открыт — и то и другое делает `advance`.
            return True
        waited = (now - row["opened_at"]).total_seconds() * 1000
        due = min(row["bot_time_ms"], limit_ms) if match.against_bot else limit_ms
        return waited >= due

    cell = (
        match.questions.filter(resolved_at__isnull=True, opened_at__isnull=False)
        .values("opened_at", "rebound_at", "bot_time_ms",
                "picked_by__is_bot", "rebound_by__is_bot")
        .first()
    )
    if cell is not None:
        started = cell["rebound_at"] or cell["opened_at"]
        answering_is_bot = (
            cell["rebound_by__is_bot"]
            if cell["rebound_at"] is not None
            else cell["picked_by__is_bot"]
        )
        waited = (now - started).total_seconds() * 1000
        due = min(cell["bot_time_ms"], limit_ms) if answering_is_bot else limit_ms
        return waited >= due
    # Открытой клетки нет: ход бота или конец партии — оба случая двигает
    # `advance`, ход человека ждёт его самого.
    bot = bot_participant(match)
    if bot is not None and match.turn_participant_id == bot.pk:
        return True
    return not match.questions.filter(resolved_at__isnull=True).exists()


def _advance_speed(match: Match) -> None:
    """Режим «на время»: у кого истёк личный лимит, тот закончил."""
    if match.limit_kind != Match.Limit.TIME:
        return
    limit_ms = match.time_limit_seconds * 1000
    for participant in match.participants.filter(finished_at__isnull=True):
        if participant.started_at and _elapsed_ms(participant.started_at) >= limit_ms:
            finish_participant(match, participant)


def _advance_quiz(match: Match) -> None:
    bot = bot_participant(match)
    for _ in range(match.questions.count() + 1):
        question = _open_next_quiz_question(match)
        if question is None:
            _finish_everyone(match)
            return
        # Бот нажимает по расписанию: раньше — не может, позже — не станет.
        if bot is not None and not bot.answers.filter(question=question).exists():
            waited = _elapsed_ms(question.opened_at)
            if waited >= question.bot_time_ms:
                _bot_answers_quiz(match, bot, question)
                if question.resolved_at is not None:
                    continue
        if _time_left(match, question) <= 0:
            # Никто не успел: вопрос сгорает, очки не достаются никому.
            _resolve(question, None)
            continue
        if not match.participants.exclude(
            pk__in=question.answers.values_list("participant_id", flat=True)
        ).exists():
            # Ответили все и все мимо — держать вопрос до таймера незачем.
            _resolve(question, None)
            continue
        return


def _bot_answers_quiz(match: Match, bot: MatchParticipant, question: MatchQuestion) -> None:
    correct = bool(question.bot_correct)
    index = _correct_option(question)
    chosen = index if correct else _wrong_option(question, index)
    MatchAnswer.objects.create(
        participant=bot, question=question, chosen_option=chosen,
        submitted_answer=str((question.options or [""])[chosen or 0])[:300],
        is_correct=correct, time_ms=question.bot_time_ms,
        points_delta=question.points if correct else 0,
    )
    _score(bot, question.points if correct else 0, correct=correct,
           time_ms=question.bot_time_ms)
    if correct:
        _resolve(question, bot)


def _advance_board(match: Match) -> None:
    bot = bot_participant(match)
    for _ in range(match.questions.count() * 2 + 1):
        cell = open_cell(match)
        if cell is not None:
            answering = cell.rebound_by or cell.picked_by
            if answering is None or cell.answers.filter(participant=answering).exists():
                return
            waited = _elapsed_ms(cell.clock_from)
            if answering.is_bot and waited >= cell.bot_time_ms:
                _bot_answers_board(match, answering, cell)
                continue
            if _time_left(match, cell) <= 0:
                # Время вышло: очки не списываются — за молчание не штрафуют.
                # Ход уходит сопернику, но только если это был не перехват:
                # перехватывающий уже получил право хода вместе с клеткой.
                rebound = cell.rebound_by_id is not None
                _resolve(cell, None)
                if not rebound:
                    _pass_turn(match)
                continue
            return
        remaining = list(match.questions.filter(resolved_at__isnull=True))
        if not remaining:
            _finish_everyone(match)
            return
        if bot is not None and match.turn_participant_id == bot.pk:
            picked = choose_cell(remaining, match.bot_level, seed=match.pk * 104729 + len(remaining))
            picked.picked_by = bot
            picked.opened_at = timezone.now()
            picked.save(update_fields=["picked_by", "opened_at"])
            continue
        return


def _bot_answers_board(match: Match, bot: MatchParticipant, cell: MatchQuestion) -> None:
    """Ход бота по клетке — своей или перехваченной.

    Знает он её или нет, разыграно при создании партии: увидев чужой неверный
    ответ, бот не становится умнее. Иначе перехват превращался бы в подсказку.
    """
    correct = bool(cell.bot_correct)
    delta = cell.points if correct else -cell.points
    MatchAnswer.objects.create(
        participant=bot, question=cell,
        submitted_answer=cell.correct_answer[:300] if correct else _bot_miss(cell),
        is_correct=correct, time_ms=cell.bot_time_ms, points_delta=delta,
    )
    _score(bot, delta, correct=correct, time_ms=cell.bot_time_ms)
    _settle_cell(match, cell, bot, is_correct=correct)


def _bot_miss(cell: MatchQuestion) -> str:
    """Что бот пишет, когда не знает: соперник должен видеть ответ, а не пустоту."""
    options = [str(option) for option in (cell.options or [])
               if not cell.check_answer(str(option))]
    if options:
        return random.Random(cell.pk).choice(options)[:300]
    return "не знаю"


def _correct_option(question: MatchQuestion) -> int | None:
    for index, option in enumerate(question.options or []):
        if question.check_answer(str(option)):
            return index
    return None


def _wrong_option(question: MatchQuestion, correct_index: int | None) -> int | None:
    for index in range(len(question.options or [])):
        if index != correct_index:
            return index
    return None


def _finish_everyone(match: Match) -> None:
    for participant in match.participants.filter(finished_at__isnull=True):
        participant.finished_at = timezone.now()
        participant.save(update_fields=["finished_at"])
    finish_match(match)


# --- Приглашения ---

@transaction.atomic
def accept_match(match: Match, student) -> Match:
    """Принять вызов друга: до этого партия ждёт согласия."""
    if participant_for(match, student) is None or match.created_by_id == student.pk:
        raise ValidationError("Этот вызов адресован другому человеку.")
    if match.status != Match.Status.INVITED:
        return match
    # Согласие — ещё не начало партии: ждём, пока оба откроют экран.
    return open_lobby(match)


@transaction.atomic
def open_lobby(match: Match) -> Match:
    """Согласие получено — партия ждёт, пока оба откроют экран."""
    if match.status == Match.Status.INVITED:
        match.status = Match.Status.LOBBY
        match.save(update_fields=["status"])
    return match


@transaction.atomic
def join_match(match: Match, student) -> Match:
    """Игрок сел за стол. Когда сели все — партия начинается.

    Именно здесь, а не при создании: таймер, общий вопрос и очередь хода не
    должны идти у того, кто ещё не открыл экран. Иначе вызов, отправленный на
    ночь глядя, к утру оказывается проигранным.
    """
    participant = participant_for(match, student)
    if participant is None or match.is_over:
        return match
    if participant.joined_at is None:
        participant.joined_at = timezone.now()
        participant.save(update_fields=["joined_at"])
    if match.status == Match.Status.LOBBY and everyone_joined(match):
        activate_match(match)
    if match.status == Match.Status.ACTIVE and match.limit_kind == Match.Limit.TIME:
        # Часы игрока идут с той секунды, как он оказался в начавшейся партии.
        start_run(match, student)
    return match


def everyone_joined(match: Match) -> bool:
    """Все ли за столом. Бот сидит за ним с момента создания партии."""
    return not match.participants.filter(joined_at__isnull=True).exists()


@transaction.atomic
def activate_match(match: Match) -> Match:
    """Начать партию: с этой секунды идут таймеры и очередь хода.

    Здесь же открывается первый вопрос квиза: до старта он не должен быть
    виден, иначе один из игроков успеет подумать заранее.
    """
    if match.status != Match.Status.ACTIVE:
        match.status = Match.Status.ACTIVE
        match.started_at = timezone.now()
        match.save(update_fields=["status", "started_at"])
    if match.mode == Match.Mode.QUIZ:
        _open_next_quiz_question(match)
    if match.mode == Match.Mode.BOARD and match.turn_participant_id is None:
        first = match.participants.filter(student=match.created_by).first()
        match.turn_participant = first
        match.save(update_fields=["turn_participant"])
    return match


@transaction.atomic
def leave_match(match: Match, student) -> Match:
    """Выйти из партии. Оставшийся выигрывает.

    Ушедший проигрывает независимо от счёта: иначе выгодно закрывать вкладку,
    пока ведёшь. Пока партия не началась, выход — это не поражение, а отмена
    или отказ: результата ещё нет.
    """
    participant = participant_for(match, student)
    if participant is None:
        raise ValidationError("Вы не участник этой партии.")
    if match.is_over:
        return match
    if match.is_waiting:
        if match.created_by_id == student.pk:
            return cancel_match(match, student)
        return decline_match(match, student)

    now = timezone.now()
    participant.left_at = now
    participant.finished_at = participant.finished_at or now
    participant.save(update_fields=["left_at", "finished_at"])
    return finish_match(match)


def _absent_participants(match: Match, now=None):
    """Кто молчит дольше положенного — то есть закрыл вкладку.

    Присутствие хранится в кеше, а не в базе: отметка приходит с каждым опросом
    экрана, и платить за неё записью в базу нельзя. Пропажа отметки у игрока,
    который только что сел за стол, ничего не значит — ему дают ту же минуту.

    В партии с ботом никто никого не ждёт, поэтому там пропажу не ищем: это
    сэкономленный запрос на каждом опросе и ни одной потерянной партии.
    """
    if match.against_bot:
        return []
    now = now or timezone.now()
    absent = []
    for participant in match.participants.all():
        if participant.is_bot or participant.finished_at or participant.joined_at is None:
            continue
        if (now - participant.joined_at).total_seconds() < ABSENT_SECONDS:
            continue
        if not is_present(match, participant):
            absent.append(participant)
    return absent


def presence_key(match_pk: int, student_pk: int) -> str:
    # Ключ по ученику, а не по участнику: у отметки о присутствии тогда нет
    # лишнего запроса — идентификатор ученика известен из сессии.
    return f"arena:seen:{match_pk}:{student_pk}"


def note_presence(match: Match, student) -> None:
    """Отметить, что игрок смотрит на партию прямо сейчас."""
    from django.core.cache import cache

    if student is None:
        return
    cache.set(presence_key(match.pk, student.pk), 1, timeout=ABSENT_SECONDS)


def is_present(match: Match, participant) -> bool:
    from django.core.cache import cache

    if participant.is_bot:
        return True
    return cache.get(presence_key(match.pk, participant.student_id)) is not None


def _drop_absent(match: Match) -> None:
    """Закрыть партию за того, кто ушёл, не нажав «выйти»."""
    absent = _absent_participants(match)
    if not absent:
        return
    # Если ушли все, приписывать победу некому: партия просто закрывается.
    now = timezone.now()
    for participant in absent:
        participant.left_at = now
        participant.finished_at = participant.finished_at or now
        participant.save(update_fields=["left_at", "finished_at"])
    finish_match(match)


def max_gain(match: Match, participant: MatchParticipant) -> int:
    """Сколько очков игрок ещё может набрать при самом удачном раскладе."""
    if match.mode == Match.Mode.SPEED:
        answered = participant.answers.values_list("question_id", flat=True)
        rows = match.questions.exclude(pk__in=answered)
    else:
        rows = match.questions.filter(resolved_at__isnull=True)
    return sum(row.points for row in rows)


def outcome_decided(match: Match) -> bool:
    """Исход уже решён: догнать лидера никто не может.

    Партию, в которой всё ясно, не дотягивают до последнего вопроса. Особенно
    это заметно с ботом: его результат разыгран заранее, и заставлять человека
    дорешивать проигранную партию — способ отбить желание играть.
    """
    table = rank(match)
    if len(table) < 2:
        return False
    leader = table[0]
    for participant in table[1:]:
        if participant.score + max_gain(match, participant) >= leader.score:
            return False
    return True


@transaction.atomic
def cancel_match(match: Match, student) -> Match:
    """Отменить партию, которая так и не началась.

    Отменяет тот, кто её создал: ждать соперника вечно нельзя, а начатую
    партию бросать нечестно — в ней уже есть результат.
    """
    if match.created_by_id != student.pk:
        raise ValidationError("Отменить партию может только тот, кто её создал.")
    if not match.is_waiting:
        raise ValidationError("Партия уже идёт — отменить её нельзя.")
    match.status = Match.Status.CANCELLED
    match.finished_at = timezone.now()
    match.save(update_fields=["status", "finished_at"])
    return match


def sweep_lobbies(now=None) -> int:
    """Снять все ожидания, которые пережили свой срок.

    Партию, к которой подошёл хотя бы один игрок, снимает его же опрос. Эта
    уборка нужна для тех, к которым не подошёл никто: обращаться к ним некому,
    а висеть в списке они не должны.
    """
    now = now or timezone.now()
    cutoff = now - timezone.timedelta(seconds=LOBBY_TTL_SECONDS)
    return Match.objects.filter(
        status__in=[Match.Status.INVITED, Match.Status.LOBBY], created_at__lt=cutoff
    ).update(status=Match.Status.CANCELLED, finished_at=now)


def expire_lobby(match: Match, *, now=None) -> Match:
    """Снять партию, к которой соперник так и не подошёл."""
    if not match.is_waiting:
        return match
    now = now or timezone.now()
    waited = (now - match.created_at).total_seconds()
    if waited < LOBBY_TTL_SECONDS:
        return match
    match.status = Match.Status.CANCELLED
    match.finished_at = now
    match.save(update_fields=["status", "finished_at"])
    return match


def blocking_match_for_practice(student, assignment, *, now=None) -> Match | None:
    """Return a genuinely live arena match containing the assignment."""
    now = now or timezone.now()
    matches = (
        Match.objects.filter(
            participants__student=student,
            status__in=[Match.Status.ACTIVE, Match.Status.LOBBY],
            questions__assignment=assignment,
        )
        .distinct()
        .order_by("created_at")
    )
    for match in matches:
        if match.status == Match.Status.LOBBY:
            expire_lobby(match, now=now)
        if match.status in [Match.Status.ACTIVE, Match.Status.LOBBY]:
            return match
    return None


@transaction.atomic
def decline_match(match: Match, student) -> Match:
    if participant_for(match, student) is None or match.created_by_id == student.pk:
        raise ValidationError("Этот вызов адресован другому человеку.")
    match.status = Match.Status.DECLINED
    match.finished_at = timezone.now()
    match.save(update_fields=["status", "finished_at"])
    return match


# --- Ходы ---

def _playable(match: Match, student) -> MatchParticipant:
    participant = participant_for(match, student)
    if participant is None:
        raise ValidationError("Вы не участник этой партии.")
    if match.status == Match.Status.INVITED:
        raise ValidationError("Соперник ещё не принял вызов.")
    if match.status == Match.Status.LOBBY:
        raise ValidationError("Ждём, пока соперник откроет партию.")
    if match.is_over:
        raise ValidationError("Партия уже завершена.")
    if participant.finished_at is not None:
        raise ValidationError("Вы уже закончили эту партию.")
    return participant


@transaction.atomic
def start_run(match: Match, student) -> MatchParticipant:
    """Отметить начало личного отсчёта в режиме «на время».

    Часы игрока идут от его первого вопроса, а не от создания партии: тот, кто
    открыл вкладку позже, не должен начинать с минусом.
    """
    participant = participant_for(match, student)
    if participant is None or participant.started_at is not None:
        return participant
    participant.started_at = timezone.now()
    participant.save(update_fields=["started_at"])
    return participant


def submit_answer(match: Match, student, question: MatchQuestion, answer: str,
                  elapsed_ms: int) -> MatchAnswer:
    """Ответ в нарешивании: своя очередь вопросов у каждого игрока."""
    participant = _playable(match, student)
    if participant.answers.filter(question=question).exists():
        raise ValidationError("На этот вопрос вы уже ответили.")
    if match.limit_kind == Match.Limit.TIME:
        if participant.started_at is None:
            start_run(match, student)
            participant.refresh_from_db()
        if _elapsed_ms(participant.started_at) >= match.time_limit_seconds * 1000:
            # Партия для игрока закончилась раньше, чем пришёл ответ. Закрытие
            # остаётся в базе, а сам ответ не засчитывается.
            finish_participant(match, participant)
            raise ValidationError("Время партии вышло.")
    return _record_speed_answer(match, participant, question, answer, elapsed_ms)


@transaction.atomic
def _record_speed_answer(match: Match, participant: MatchParticipant,
                         question: MatchQuestion, answer: str,
                         elapsed_ms: int) -> MatchAnswer:
    match = Match.objects.select_for_update().get(pk=match.pk)
    participant.refresh_from_db()
    _playable(match, participant.student)
    if participant.answers.filter(question=question).exists():
        raise ValidationError("На этот вопрос вы уже ответили.")
    student = participant.student
    is_correct = question.check_answer(answer)
    # The sum is server wall time since play began. Client timings never rank players.
    since = participant.started_at or match.started_at or match.created_at
    time_ms = max(0, _elapsed_ms(since) - participant.total_time_ms)

    record = MatchAnswer.objects.create(
        participant=participant, question=question, submitted_answer=answer[:300],
        is_correct=is_correct, time_ms=time_ms,
        points_delta=question.points if is_correct else 0,
    )
    _score(participant, question.points if is_correct else 0,
           correct=is_correct, time_ms=time_ms)
    _log_attempt(student, question, answer, is_correct)

    if next_question(match, participant) is None:
        finish_participant(match, participant)
    elif outcome_decided(match):
        _finish_everyone(match)
    return record


def submit_quiz_answer(match: Match, student, question: MatchQuestion,
                       option: int) -> MatchAnswer:
    """Ответ в квизе: кто первым нажал верный вариант, тот и забрал вопрос.

    Перед проверкой партия «доигрывается» до текущего момента — если бот по
    расписанию нажал раньше, вопрос уже занят, и человек получит отказ, а не
    очки задним числом.
    """
    participant = _playable(match, student)
    advance(match)
    question.refresh_from_db()
    record = _record_quiz_answer(match, participant, question, option)
    # После хода партия доигрывается без дешёвой проверки: ход и есть событие,
    # а «все ответили — вопрос сгорел» по срокам не вычислить.
    _advance_locked(match)
    return record


@transaction.atomic
def _record_quiz_answer(match: Match, participant: MatchParticipant,
                        question: MatchQuestion, option: int) -> MatchAnswer:
    # Повторная проверка под блокировкой строки: два нажатия могут прийти
    # в одну и ту же миллисекунду, и забрать вопрос должен один.
    question = MatchQuestion.objects.select_for_update().get(pk=question.pk)
    if question.resolved_at is not None:
        raise ValidationError("Этот вопрос уже разыгран.")
    if question.opened_at is None:
        raise ValidationError("Вопрос ещё не открыт.")
    if participant.answers.filter(question=question).exists():
        raise ValidationError("Вы уже отвечали на этот вопрос.")
    options = question.options or []
    if not 0 <= option < len(options):
        raise ValidationError("Такого варианта нет.")

    time_ms = min(_elapsed_ms(question.opened_at), match.seconds_per_question * 1000)
    is_correct = question.check_answer(str(options[option]))
    record = MatchAnswer.objects.create(
        participant=participant, question=question, chosen_option=option,
        submitted_answer=str(options[option])[:300], is_correct=is_correct,
        time_ms=time_ms, points_delta=question.points if is_correct else 0,
    )
    # Промах очков не отнимает, но лишает права ответа: иначе выгодно жать по
    # всем вариантам подряд.
    _score(participant, question.points if is_correct else 0,
           correct=is_correct, time_ms=time_ms)
    if is_correct:
        _resolve(question, participant)
    return record


def pick_cell(match: Match, student, question: MatchQuestion) -> MatchQuestion:
    """Выбрать клетку в «своей игре». Выбирает тот, чей ход."""
    participant = _playable(match, student)
    advance(match)
    match.refresh_from_db()
    question.refresh_from_db()
    return _record_pick(match, participant, question)


@transaction.atomic
def _record_pick(match: Match, participant: MatchParticipant,
                 question: MatchQuestion) -> MatchQuestion:
    question = MatchQuestion.objects.select_for_update().get(pk=question.pk)
    if match.mode != Match.Mode.BOARD:
        raise ValidationError("Клетки есть только в «своей игре».")
    if match.turn_participant_id != participant.pk:
        raise ValidationError("Сейчас ход соперника.")
    if question.resolved_at is not None:
        raise ValidationError("Эта клетка уже разыграна.")
    if open_cell(match) is not None:
        raise ValidationError("Сначала доиграйте открытую клетку.")
    question.picked_by = participant
    question.opened_at = timezone.now()
    question.save(update_fields=["picked_by", "opened_at"])
    return question


def submit_board_answer(match: Match, student, question: MatchQuestion,
                        answer: str) -> MatchAnswer:
    """Ответ на клетку: верный приносит цену, неверный её списывает.

    Верный ответ оставляет ход за игроком — как в телевизионной игре: тот, кто
    знает, продолжает выбирать. Неверный передаёт ход сопернику.
    """
    participant = _playable(match, student)
    advance(match)
    question.refresh_from_db()
    record = _record_board_answer(match, participant, question, answer)
    _advance_locked(match)
    return record


@transaction.atomic
def _record_board_answer(match: Match, participant: MatchParticipant,
                         question: MatchQuestion, answer: str) -> MatchAnswer:
    question = MatchQuestion.objects.select_for_update().get(pk=question.pk)
    if question.resolved_at is not None:
        raise ValidationError("Эта клетка уже разыграна.")
    if question.answering_id != participant.pk:
        raise ValidationError("Сейчас на эту клетку отвечает соперник.")
    if participant.answers.filter(question=question).exists():
        raise ValidationError("Вы уже отвечали на эту клетку.")

    time_ms = min(_elapsed_ms(question.clock_from), match.seconds_per_question * 1000)
    is_correct = question.check_answer(answer)
    delta = question.points if is_correct else -question.points
    record = MatchAnswer.objects.create(
        participant=participant, question=question, submitted_answer=answer[:300],
        is_correct=is_correct, time_ms=time_ms, points_delta=delta,
    )
    _score(participant, delta, correct=is_correct, time_ms=time_ms)
    _settle_cell(match, question, participant, is_correct=is_correct)
    return record


def _settle_cell(match: Match, cell: MatchQuestion, participant: MatchParticipant,
                 *, is_correct: bool) -> None:
    """Что происходит с клеткой после ответа.

    Верный ответ закрывает клетку и приносит её цену. Неверный — списывает цену
    и отдаёт клетку сопернику: он видит и вопрос, и чужой ответ, и получает
    свои полминуты. Если ошиблись оба, цену теряют оба, а клетка сгорает.

    Право хода после ошибки уходит вместе с клеткой: дальше выбирает тот, кто
    отвечал вторым, — и когда он перехватил, и когда тоже промахнулся.
    """
    if is_correct:
        _resolve(cell, participant)
        return
    if cell.rebound_by_id is not None:
        # Перехват тоже мимо: клетка сгорает, ход остаётся у перехватившего.
        _resolve(cell, None)
        return
    rival = match.participants.exclude(pk=participant.pk).first()
    if rival is None:
        _resolve(cell, None)
        return
    cell.rebound_by = rival
    cell.rebound_at = timezone.now()
    cell.save(update_fields=["rebound_by", "rebound_at"])
    if match.turn_participant_id != rival.pk:
        _pass_turn(match)


def _log_attempt(student, question: MatchQuestion, answer: str, is_correct: bool) -> None:
    """Ответы по задачам попадают в общий журнал попыток — но освоение не двигают.

    Вопросы по теории в журнал не идут вовсе: «знаю определение» — это не
    попытка решить задачу, и смешивать их в одной таблице нельзя.
    """
    if not question.assignment_id:
        return
    Attempt.objects.create(
        student=student, assignment=question.assignment,
        context=Attempt.Context.ARENA, submitted_answer=answer[:200],
        is_correct=is_correct,
    )


# --- Итоги ---

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
    """Итог: сначала оставшиеся за столом, потом очки, потом время.

    Ушедший оказывается ниже любого, кто доиграл, каким бы ни был счёт: партия,
    брошенная в выигрышной позиции, — это не победа.
    """
    return sorted(
        match.participants.select_related("student__user"),
        key=lambda participant: (
            participant.left_at is not None,
            -participant.score,
            participant.total_time_ms,
        ),
    )


def winner_of(match: Match) -> MatchParticipant | None:
    """Победитель или None при полной ничьей: очки и время совпали."""
    table = rank(match)
    if len(table) < 2:
        return table[0] if table else None
    first, second = table[0], table[1]
    # Кто-то вышел: победа тому, кто остался, без сравнения счёта.
    if first.left_at is None and second.left_at is not None:
        return first
    if first.left_at is not None:
        return None
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
