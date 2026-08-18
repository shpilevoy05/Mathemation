"""Подбор случайного соперника и рейтинг.

Играть интересно с равным. Поэтому у игрока есть рейтинг, а очередь ищет
сначала ровню и только потом — ближайшего из доступных: окно поиска
расширяется со временем ожидания, как в шахматных клубах.

Стартовый рейтинг берётся из прогноза балла: платформа уже знает про ученика
достаточно, чтобы не бросать его в первую попавшуюся партию. Дальше рейтинг
двигают только партии с людьми — бот не рейтингованный соперник, и набивать
о него рейтинг нельзя.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import ArenaProfile, Match, MatchmakingTicket

# Окно подбора: сначала ищем близких по рейтингу, затем расширяем поиск.
BASE_WINDOW = 120
WINDOW_STEP = 60          # на сколько окно растёт за каждые…
WINDOW_STEP_SECONDS = 10  # …столько секунд ожидания
MAX_WINDOW = 1200
# Заявка старше этого срока считается брошенной: вкладку закрыли.
TICKET_TTL_SECONDS = 180
# Коэффициент Эло: партия короткая, поэтому шаг небольшой.
K_FACTOR = 24


def _seed_rating(student) -> int:
    """Стартовый рейтинг из прогноза балла.

    Ноль баллов — 800, сотня — 1600. Это не «сила игрока в арене», а разумная
    первая догадка: лучше начать рядом со своим уровнем, чем с середины.
    """
    from apps.progress.services import forecast_interval

    try:
        scaled = int(forecast_interval(student)["scaled"])
    except Exception:  # прогноза может не быть у новичка
        scaled = 50
    return int(800 + max(0, min(100, scaled)) * 8)


def get_profile(student) -> ArenaProfile:
    profile = ArenaProfile.objects.filter(student=student).first()
    if profile is not None:
        return profile
    return ArenaProfile.objects.create(student=student, rating=_seed_rating(student))


def window_for(ticket: MatchmakingTicket, now=None) -> int:
    """Насколько широко ищем соперника прямо сейчас."""
    now = now or timezone.now()
    waited = max(0, int((now - ticket.created_at).total_seconds()))
    return min(MAX_WINDOW, BASE_WINDOW + (waited // WINDOW_STEP_SECONDS) * WINDOW_STEP)


def expire_stale(now=None) -> int:
    """Убрать брошенные заявки: закрытая вкладка не должна ловить соперника."""
    now = now or timezone.now()
    cutoff = now - timezone.timedelta(seconds=TICKET_TTL_SECONDS)
    return MatchmakingTicket.objects.filter(
        status=MatchmakingTicket.Status.WAITING, created_at__lt=cutoff
    ).update(status=MatchmakingTicket.Status.CANCELLED, resolved_at=now)


def _candidates(ticket: MatchmakingTicket):
    return (
        MatchmakingTicket.objects.select_for_update(skip_locked=True)
        .filter(
            status=MatchmakingTicket.Status.WAITING,
            mode=ticket.mode,
            ege_task_number=ticket.ege_task_number,
        )
        .exclude(student=ticket.student)
        .exclude(pk=ticket.pk)
        .select_related("student__user")
    )


@transaction.atomic
def join_queue(student, *, mode: str, ege_task_number: int | None = None) -> MatchmakingTicket:
    """Встать в очередь и сразу попробовать найти пару."""
    from .services import create_match

    expire_stale()
    profile = get_profile(student)

    # Одна заявка на игрока: повторное нажатие продолжает ждать, а не плодит
    # очередь из одного и того же человека.
    existing = MatchmakingTicket.objects.filter(
        student=student, status=MatchmakingTicket.Status.WAITING
    ).first()
    if existing is not None:
        if existing.mode == mode and existing.ege_task_number == ege_task_number:
            ticket = existing
        else:
            existing.status = MatchmakingTicket.Status.CANCELLED
            existing.resolved_at = timezone.now()
            existing.save(update_fields=["status", "resolved_at"])
            ticket = MatchmakingTicket.objects.create(
                student=student, mode=mode, ege_task_number=ege_task_number,
                rating=profile.rating,
            )
    else:
        ticket = MatchmakingTicket.objects.create(
            student=student, mode=mode, ege_task_number=ege_task_number,
            rating=profile.rating,
        )

    rival = find_rival(ticket)
    if rival is None:
        return ticket

    match = create_match(
        student, mode=mode, opponent=rival.student,
        ege_task_number=ege_task_number, ranked=True,
    )
    # Случайная партия начинается сразу: оба уже согласились игрой в очередь.
    match.status = Match.Status.ACTIVE
    match.save(update_fields=["status"])
    for row in (ticket, rival):
        row.status = MatchmakingTicket.Status.MATCHED
        row.match = match
        row.resolved_at = timezone.now()
        row.save(update_fields=["status", "match", "resolved_at"])
    return ticket


def find_rival(ticket: MatchmakingTicket, now=None) -> MatchmakingTicket | None:
    """Ближайший по рейтингу соперник внутри текущего окна поиска.

    Окно у обеих сторон своё: тот, кто ждёт дольше, ищет шире. Пара считается
    подходящей, если разница укладывается хотя бы в одно из окон — иначе
    новичок в очереди блокировал бы того, кто ждёт пять минут.
    """
    now = now or timezone.now()
    my_window = window_for(ticket, now)
    best, best_gap = None, None
    for candidate in _candidates(ticket):
        gap = abs(candidate.rating - ticket.rating)
        if gap > max(my_window, window_for(candidate, now)):
            continue
        if best_gap is None or gap < best_gap:
            best, best_gap = candidate, gap
    return best


@transaction.atomic
def leave_queue(student) -> int:
    return MatchmakingTicket.objects.filter(
        student=student, status=MatchmakingTicket.Status.WAITING
    ).update(status=MatchmakingTicket.Status.CANCELLED, resolved_at=timezone.now())


def bot_level_for(student) -> int:
    """Уровень бота, равный игроку: чем нужен, когда живого соперника нет."""
    rating = get_profile(student).rating
    for level, ceiling in ((1, 900), (2, 1100), (3, 1300), (4, 1500)):
        if rating < ceiling:
            return level
    return 5


def expected_score(rating: int, rival_rating: int) -> float:
    """Ожидание Эло: доля очков, которую «должен» взять игрок."""
    return 1 / (1 + 10 ** ((rival_rating - rating) / 400))


@transaction.atomic
def apply_rating(match: Match) -> None:
    """Пересчитать рейтинг после рейтинговой партии двух людей."""
    if not match.is_ranked or match.against_bot:
        return
    from .services import winner_of

    participants = list(match.participants.select_related("student"))
    if len(participants) != 2 or any(p.student_id is None for p in participants):
        return

    champion = winner_of(match)
    first, second = participants
    profiles = {p.pk: get_profile(p.student) for p in participants}
    outcome = {}
    for participant in participants:
        if champion is None:
            outcome[participant.pk] = 0.5
        else:
            outcome[participant.pk] = 1.0 if champion.pk == participant.pk else 0.0

    ratings = {p.pk: profiles[p.pk].rating for p in participants}
    for participant in participants:
        rival = second if participant.pk == first.pk else first
        profile = profiles[participant.pk]
        expected = expected_score(ratings[participant.pk], ratings[rival.pk])
        change = round(K_FACTOR * (outcome[participant.pk] - expected))
        profile.rating = max(100, min(3000, profile.rating + change))
        profile.matches_played += 1
        profile.wins += 1 if outcome[participant.pk] == 1.0 else 0
        profile.save(update_fields=["rating", "matches_played", "wins", "updated_at"])
