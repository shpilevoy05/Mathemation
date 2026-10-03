"""Ночное обслуживание подписок."""

from celery import shared_task


@shared_task
def expire_subscriptions_task():
    """Перевести истёкшие подписки в expired.

    Доступ и без этого закрывается по `ends_at`, но статус нужен отчётам и
    панели: «активных подписок» не должно быть больше, чем оплаченных.
    """
    from .services import expire_subscriptions

    return expire_subscriptions()
