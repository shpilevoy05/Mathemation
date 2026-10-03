from rest_framework import views
from rest_framework.response import Response

from apps.accounts.api import get_student

from .services import gamification_snapshot


class GamificationView(views.APIView):
    """Current XP, streak and this week's quests."""

    def get(self, request):
        return Response(gamification_snapshot(get_student(request)))


def league_payload(student) -> dict:
    """Состояние лиги для экрана и для скрипта — один и тот же объект."""
    from .leagues import league_state

    state = league_state(student)
    return {
        "enabled": state["enabled"],
        "league": state["league"],
        "league_label": state["league_label"],
        "days_left": state["days_left"],
        "place": state["place"],
        "xp": state["xp"],
        "cohort": state["cohort_index"],
        "promotion_places": state["promotion_places"],
        "rows": [
            {
                "place": row["place"],
                "title": row["title"],
                "xp": row["xp"],
                "is_me": row["is_me"],
                "is_filler": row["is_filler"],
                "promotes": row["promotes"],
                "coins": row["coins"],
            }
            for row in state["rows"]
        ],
        "trophies": [
            {
                "league": trophy.get_league_display(),
                "prize": trophy.prize,
                "season": trophy.season.starts_on.strftime("%m.%Y"),
            }
            for trophy in state["trophies"]
        ],
    }


class LeagueView(views.APIView):
    """GET — своя лига и таблица когорты."""

    def get(self, request):
        return Response(league_payload(get_student(request)))


class LeagueOptInView(views.APIView):
    """POST — включить участие, DELETE — выйти из соревнования.

    Выключено по умолчанию и выключается в одно нажатие: соревнование, из
    которого нельзя уйти, — это давление, а не мотивация.
    """

    def post(self, request):
        from .leagues import enable_leagues

        student = get_student(request)
        enable_leagues(student)
        return Response(league_payload(student), status=201)

    def delete(self, request):
        from .leagues import disable_leagues

        student = get_student(request)
        disable_leagues(student)
        return Response(league_payload(student))

