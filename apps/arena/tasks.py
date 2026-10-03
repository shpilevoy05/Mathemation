"""Уборка в арене: брошенные ожидания и заявки очереди.

Партия, которую открыл один игрок, снимается сама при обращении к ней. Но если
её не открыл никто, обращаться некому — такие ожидания и подбирает эта задача.
Без неё «Идут сейчас» превращается в кладбище партий, которые никогда не были.
"""

from celery import shared_task


@shared_task
def sweep_arena() -> dict:
    """Снять просроченные ожидания и брошенные заявки на соперника."""
    from .services import sweep_lobbies
    from .matchmaking import expire_stale

    return {"lobbies": sweep_lobbies(), "tickets": expire_stale()}
