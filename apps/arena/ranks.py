"""Pure rating-to-rank rules for the arena."""

from __future__ import annotations


RANKS = (
    {"code": "bronze", "title": "Бронза", "min_rating": 0},
    {"code": "silver", "title": "Серебро", "min_rating": 1100},
    {"code": "gold", "title": "Золото", "min_rating": 1300},
    {"code": "platinum", "title": "Платина", "min_rating": 1500},
    {"code": "diamond", "title": "Алмаз", "min_rating": 1700},
)


def rank_for_rating(rating: int) -> dict:
    """Return the current arena rank and progress toward the next one."""
    normalized_rating = rating if rating is not None and rating >= 0 else 0
    rank_index = max(
        index
        for index, rank in enumerate(RANKS)
        if normalized_rating >= rank["min_rating"]
    )
    rank = RANKS[rank_index]

    if rank_index == len(RANKS) - 1:
        next_rank = None
        points_to_next = None
        progress_percent = 100
    else:
        next_rank = RANKS[rank_index + 1]
        band_width = next_rank["min_rating"] - rank["min_rating"]
        points_to_next = next_rank["min_rating"] - normalized_rating
        progress_percent = round(
            (normalized_rating - rank["min_rating"]) * 100 / band_width
        )

    return {
        "code": rank["code"],
        "title": rank["title"],
        "min_rating": rank["min_rating"],
        "next_code": next_rank["code"] if next_rank else None,
        "next_title": next_rank["title"] if next_rank else None,
        "next_min_rating": next_rank["min_rating"] if next_rank else None,
        "points_to_next": points_to_next,
        "progress_percent": progress_percent,
    }
