"""Лиги: месячное соревнование по опыту в когортах по двадцать человек.

Зачем это в учебной платформе: опыт сам по себе — счётчик, который перестаёт
радовать через неделю. Соревнование даёт ему смысл: место в таблице меняется
каждый день, а месяц — достаточно короткий срок, чтобы отстающий не считал
сезон потерянным.

Четыре правила, из которых выведено остальное:

* участие добровольное и по умолчанию выключено. Часть учеников таблица с
  чужими результатами демотивирует, а платформа обещает готовить к экзамену,
  а не выигрывать соревнования;
* когорта — двадцать мест. Соревноваться со всей платформой бессмысленно:
  в таблице из тысячи имён место не двигается;
* пока людей мало, свободные места занимают заполнители. Они помечены как
  боты, не выдаются за людей и всегда стоят ниже самого слабого живого
  участника: соревнование должно быть видимым, но не выдуманным;
* очки сезона — это тот же XP, что и в остальном кабинете. Отдельной валюты
  для лиг нет, иначе появится способ «фармить лигу» вместо учёбы.
"""

from __future__ import annotations

import random
from calendar import monthrange
from datetime import date

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    GamificationProfile,
    League,
    LeagueCohort,
    LeagueMember,
    LeagueSeason,
    LeagueTrophy,
    next_league,
)

COHORT_SIZE = 20
# Сколько мест уходит в следующую лигу и сколько получают сигмы.
PROMOTION_PLACES = 10
COIN_PRIZES = {1: 200, 2: 120, 3: 80, 4: 50, 5: 30}
# Награда за призовую тройку — в каждой лиге, но своя.
#
# Сигмы получают пятеро, а вещь — только тройка: иначе награда перестаёт быть
# наградой. Чем выше лига, тем дороже вещь: в Дельте призовое место занимает
# любой, кто просто занимался, в Сигме — тот, кто выиграл у сильнейших.
FREEZE, BOOST = "freeze", "boost"

# Награда за призовую тройку. Набор один и тот же — ускоритель опыта и
# заморозки серии, — но чем выше лига, тем он длиннее и щедрее: в Дельте
# призовое место занимает тот, кто просто занимался, в Омеге и выше — тот, кто
# выиграл у сильных. Первое место получает и ускоритель, и заморозки, второе —
# ускоритель, третье — заморозки.
BOOST_PERCENT = 50
LEAGUE_PRIZE_SCALE: dict[str, tuple[int, int]] = {
    # лига: (часы ускорителя, сколько заморозок)
    League.DELTA: (12, 1),
    League.GAMMA: (24, 2),
    League.OMEGA: (48, 3),
    League.BETA: (48, 3),
    League.ALPHA: (48, 3),
    League.SIGMA: (48, 3),
}
# Трофей — знак в списке наград — дают начиная с Бетты: в младших лигах
# призовое место стоит слишком дёшево, чтобы оставлять по нему память.
TROPHY_FROM = League.BETA

PRIZE_PLACES = [1, 2, 3]
# Насколько заполнитель отстаёт от самого слабого живого участника.
FILLER_STEP = 12


def season_bounds(day: date | None = None) -> tuple[date, date]:
    """Границы сезона — календарный месяц."""
    day = day or timezone.localdate()
    last = monthrange(day.year, day.month)[1]
    return date(day.year, day.month, 1), date(day.year, day.month, last)


def current_season(day: date | None = None, *, create: bool = True) -> LeagueSeason | None:
    """Сезон, идущий в этот день. Создаётся по требованию — расписание может
    и не сработать, а ученик уже нажал «участвовать»."""
    starts_on, ends_on = season_bounds(day)
    season = LeagueSeason.objects.filter(starts_on=starts_on).first()
    if season is not None or not create:
        return season
    return LeagueSeason.objects.create(starts_on=starts_on, ends_on=ends_on)


# --- Участие ---

def _profile(student) -> GamificationProfile:
    profile, _ = GamificationProfile.objects.get_or_create(student=student)
    return profile


@transaction.atomic
def enable_leagues(student) -> LeagueMember:
    """Включить участие и посадить ученика в когорту своей лиги."""
    profile = _profile(student)
    if not profile.leagues_enabled:
        profile.leagues_enabled = True
        profile.save(update_fields=["leagues_enabled"])
    return join_cohort(student)


@transaction.atomic
def disable_leagues(student) -> None:
    """Выйти из соревнования.

    Место в когорте освобождается и занимается заполнителем: соперники не
    должны гнаться за тем, кто уже ушёл. Набранный опыт при этом никуда не
    девается — он общий, а не «лиговый».
    """
    profile = _profile(student)
    profile.leagues_enabled = False
    profile.save(update_fields=["leagues_enabled"])
    season = current_season(create=False)
    if season is None:
        return
    for member in LeagueMember.objects.filter(cohort__season=season, student=student):
        cohort = member.cohort
        member.delete()
        fill_cohort(cohort)


def membership_for(student, season: LeagueSeason | None = None) -> LeagueMember | None:
    season = season or current_season(create=False)
    if season is None:
        return None
    return (
        LeagueMember.objects.filter(cohort__season=season, student=student)
        .select_related("cohort")
        .first()
    )


@transaction.atomic
def join_cohort(student, season: LeagueSeason | None = None) -> LeagueMember:
    """Найти ученику место в когорте его лиги.

    Сначала занимается место заполнителя: живой соперник всегда лучше бота.
    Когда живых становится двадцать, открывается следующая когорта.
    """
    season = season or current_season()
    existing = membership_for(student, season)
    if existing is not None:
        return existing

    profile = _profile(student)
    league = profile.league
    cohort = _cohort_with_room(season, league)
    filler = cohort.members.filter(is_filler=True).order_by("-filler_index").first()
    if filler is not None:
        filler.delete()
    member = LeagueMember.objects.create(cohort=cohort, student=student)
    fill_cohort(cohort)
    return member


def _cohort_with_room(season: LeagueSeason, league: str) -> LeagueCohort:
    for cohort in season.cohorts.filter(league=league).order_by("index"):
        if cohort.members.filter(is_filler=False).count() < COHORT_SIZE:
            return cohort
    index = season.cohorts.filter(league=league).count()
    cohort = LeagueCohort.objects.create(season=season, league=league, index=index)
    fill_cohort(cohort)
    return cohort


def fill_cohort(cohort: LeagueCohort) -> int:
    """Добить когорту заполнителями до двадцати мест."""
    taken = cohort.members.count()
    created = 0
    used = set(
        cohort.members.filter(is_filler=True).values_list("filler_index", flat=True)
    )
    index = 0
    while taken + created < COHORT_SIZE:
        while index in used:
            index += 1
        LeagueMember.objects.create(cohort=cohort, is_filler=True, filler_index=index)
        used.add(index)
        created += 1
    return created


# --- Очки сезона ---

def add_league_xp(student, amount: int) -> None:
    """Записать опыт в зачёт сезона.

    Вызывается из начисления XP. Если ученик не участвует, не делает ничего —
    поэтому включение лиг не меняет ни одной другой механики.
    """
    if amount <= 0:
        return
    profile = GamificationProfile.objects.filter(student=student).first()
    if profile is None or not profile.leagues_enabled:
        return
    season = current_season(create=False)
    if season is None or not season.is_active:
        return
    member = membership_for(student, season) or join_cohort(student, season)
    # Прибавка выражением базы: начисления идут параллельно, и читать-писать
    # значение в Python значило бы терять очки на гонках.
    LeagueMember.objects.filter(pk=member.pk).update(xp=F("xp") + amount)


# --- Таблица ---

def filler_xp(member: LeagueMember, floor_xp: int) -> int:
    """Опыт заполнителя: всегда ниже самого слабого живого участника.

    Считается на лету и никуда не пишется: как только в когорту приходит живой
    человек со слабым результатом, боты обязаны оказаться под ним.
    """
    rng = random.Random(member.pk * 7919 + member.filler_index)
    gap = FILLER_STEP * (member.filler_index + 1) + rng.randint(0, FILLER_STEP - 1)
    return max(0, floor_xp - gap)


def standings(cohort: LeagueCohort, student=None) -> list[dict]:
    """Таблица когорты с местами, зонами и наградами."""
    members = list(cohort.members.select_related("student__user"))
    live = [member for member in members if not member.is_filler]
    floor_xp = min((member.xp for member in live), default=0)

    rows = []
    for member in members:
        xp = filler_xp(member, floor_xp) if member.is_filler else member.xp
        rows.append({
            "member": member,
            "title": member.title,
            "is_filler": member.is_filler,
            "is_me": student is not None and member.student_id == student.pk,
            "xp": xp,
        })
    # Заполнители при равенстве очков стоят ниже живых: место в таблице должно
    # доставаться человеку.
    rows.sort(key=lambda row: (-row["xp"], row["is_filler"], row["member"].pk))
    for place, row in enumerate(rows, start=1):
        row["place"] = place
        row["promotes"] = place <= PROMOTION_PLACES
        row["coins"] = COIN_PRIZES.get(place, 0)
    return rows


def league_state(student) -> dict:
    """Всё, что нужно экрану лиги: своя лига, таблица, сроки, трофеи."""
    profile = _profile(student)
    season = current_season(create=False)
    membership = membership_for(student, season) if season else None
    rows = standings(membership.cohort, student) if membership else []
    my_row = next((row for row in rows if row["is_me"]), None)
    today = timezone.localdate()
    return {
        "enabled": profile.leagues_enabled,
        "league": profile.league,
        "league_label": League(profile.league).label,
        "season": season,
        "days_left": (season.ends_on - today).days if season else 0,
        "rows": rows,
        "place": my_row["place"] if my_row else None,
        "xp": my_row["xp"] if my_row else 0,
        "cohort_index": membership.cohort.index + 1 if membership else None,
        "promotion_places": PROMOTION_PLACES,
        "coin_prizes": COIN_PRIZES,
        "trophies": list(
            LeagueTrophy.objects.filter(student=student).select_related("season")[:10]
        ),
        # Что дают за призовые места именно в этой лиге: обещание должно быть
        # видно до конца сезона, а не после.
        "place_prizes": [
            {"place": place, "title": prize_title(profile.league, place)}
            for place in PRIZE_PLACES
        ],
    }


# --- Закрытие сезона ---

@transaction.atomic
def close_season(season: LeagueSeason) -> dict:
    """Подвести итоги: повышения, сигмы и особые награды за первое место."""
    if not season.is_active:
        return {"cohorts": 0, "promoted": 0, "rewarded": 0}

    promoted = rewarded = 0
    for cohort in season.cohorts.all():
        for row in standings(cohort):
            member = row["member"]
            member.place = row["place"]
            if member.is_filler:
                member.save(update_fields=["place"])
                continue
            member.promoted = row["promotes"]
            member.coins_awarded = row["coins"]
            member.save(update_fields=["place", "promoted", "coins_awarded"])
            if member.promoted:
                _promote(member)
                promoted += 1
            if row["coins"]:
                _pay(member, cohort, row["coins"])
                rewarded += 1
            if row["place"] in PRIZE_PLACES:
                _place_prize(member, cohort, season, row["place"])
    season.status = LeagueSeason.Status.CLOSED
    season.closed_at = timezone.now()
    season.save(update_fields=["status", "closed_at"])
    return {"cohorts": season.cohorts.count(), "promoted": promoted, "rewarded": rewarded}


def _promote(member: LeagueMember) -> None:
    profile = _profile(member.student)
    profile.league = next_league(member.cohort.league)
    profile.save(update_fields=["league"])


def _pay(member: LeagueMember, cohort: LeagueCohort, coins: int) -> None:
    from apps.economy.models import LedgerEntry
    from apps.economy.services import grant
    from apps.events.models import Event
    from apps.events.services import log_event

    grant(
        member.student, coins, LedgerEntry.Reason.XP_AWARD,
        reference=f"league:{cohort.season_id}:{cohort.pk}:{member.place}",
        comment=f"Лига {cohort.get_league_display()}: {member.place} место",
    )
    log_event(
        Event.Type.LEAGUE_FINISHED, student=member.student,
        league=cohort.league, place=member.place, coins=coins,
        promoted=member.promoted, season=str(cohort.season_id),
    )


def prize_parts(league: str, place: int) -> list[tuple[str, int]]:
    """Из чего состоит награда: список действий вида («boost», часы)."""
    scale = LEAGUE_PRIZE_SCALE.get(league)
    if scale is None or place not in PRIZE_PLACES:
        return []
    hours, freezes = scale
    if place == 1:
        return [(BOOST, hours), (FREEZE, freezes)]
    if place == 2:
        return [(BOOST, hours)]
    return [(FREEZE, freezes)]


def has_trophy(league: str) -> bool:
    """Даёт ли лига трофей — память о призовом месте."""
    from apps.gamification.models import LEAGUE_ORDER

    return LEAGUE_ORDER.index(league) >= LEAGUE_ORDER.index(TROPHY_FROM)


def prize_title(league: str, place: int) -> str:
    """Как награда называется для человека."""
    names = []
    for kind, value in prize_parts(league, place):
        if kind == BOOST:
            names.append(f"ускоритель опыта +{BOOST_PERCENT}% на {value} ч")
        elif kind == FREEZE:
            names.append(
                f"{value} заморозки серии" if value > 1 else "заморозка серии"
            )
    if not names:
        return ""
    if has_trophy(league):
        names.append("трофей")
    title = " и ".join(names)
    return title[0].upper() + title[1:]


def _place_prize(member: LeagueMember, cohort: LeagueCohort, season: LeagueSeason,
                 place: int) -> str:
    """Выдать награду за призовое место и записать её в список наград."""
    parts = prize_parts(cohort.league, place)
    if not parts:
        return ""

    for kind, value in parts:
        if kind == FREEZE:
            profile = _profile(member.student)
            profile.streak_freezes += int(value)
            profile.save(update_fields=["streak_freezes"])
        elif kind == BOOST:
            from datetime import timedelta

            from apps.economy.models import XpBoost

            now = timezone.now()
            XpBoost.objects.create(
                student=member.student, bonus_percent=BOOST_PERCENT,
                starts_at=now, ends_at=now + timedelta(hours=int(value)),
            )

    prize = prize_title(cohort.league, place)
    LeagueTrophy.objects.get_or_create(
        student=member.student, season=season, league=cohort.league,
        defaults={"place": place, "prize": prize, "trophy": has_trophy(cohort.league)},
    )
    return prize


@transaction.atomic
def rotate_seasons(day: date | None = None) -> dict:
    """Закрыть сезоны, у которых кончился срок, и открыть текущий."""
    day = day or timezone.localdate()
    closed = 0
    for season in LeagueSeason.objects.filter(
        status=LeagueSeason.Status.ACTIVE, ends_on__lt=day
    ):
        close_season(season)
        closed += 1
    season = current_season(day)
    # Ученики, которые остались в игре, переезжают в когорты нового сезона
    # при первом же начислении опыта — отдельный переезд не нужен.
    return {"closed": closed, "season": season.pk}
