"""Pure rating-to-league rules for the arena."""

from __future__ import annotations


LEAGUES = (
    {"code": "bronze", "title": "Бронза", "min_rating": 0},
    {"code": "silver", "title": "Серебро", "min_rating": 1100},
    {"code": "gold", "title": "Золото", "min_rating": 1300},
    {"code": "platinum", "title": "Платина", "min_rating": 1500},
    {"code": "diamond", "title": "Алмаз", "min_rating": 1700},
)


def league_for_rating(rating: int) -> dict:
    """Return the current league and progress toward the next one."""
    normalized_rating = rating if rating is not None and rating >= 0 else 0
    league_index = max(
        index
        for index, league in enumerate(LEAGUES)
        if normalized_rating >= league["min_rating"]
    )
    league = LEAGUES[league_index]

    if league_index == len(LEAGUES) - 1:
        next_league = None
        points_to_next = None
        progress_percent = 100
    else:
        next_league = LEAGUES[league_index + 1]
        band_width = next_league["min_rating"] - league["min_rating"]
        points_to_next = next_league["min_rating"] - normalized_rating
        progress_percent = round(
            (normalized_rating - league["min_rating"]) * 100 / band_width
        )

    return {
        "code": league["code"],
        "title": league["title"],
        "min_rating": league["min_rating"],
        "next_code": next_league["code"] if next_league else None,
        "next_title": next_league["title"] if next_league else None,
        "next_min_rating": next_league["min_rating"] if next_league else None,
        "points_to_next": points_to_next,
        "progress_percent": progress_percent,
    }
