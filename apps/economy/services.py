"""Начисления, списания и покупки. Единственный вход в кошелёк."""

from __future__ import annotations

from datetime import timedelta
from math import ceil

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import InventoryItem, LedgerEntry, ShopItem, Wallet, XpBoost


def get_wallet(student) -> Wallet:
    wallet, _ = Wallet.objects.get_or_create(student=student)
    return wallet


@transaction.atomic
def record(student, *, amount: int, reason: str, reference: str,
           comment: str = "", created_by=None) -> LedgerEntry:
    """Записать движение по кошельку. Идемпотентно по (причина, reference).

    Повторный вызов за то же событие возвращает существующую запись и не
    меняет баланс: начисления приходят из джобов и обработчиков, которые
    могут выполниться дважды.
    """
    if amount == 0:
        raise ValidationError("Нулевое движение по кошельку не имеет смысла.")

    wallet = Wallet.objects.select_for_update().get_or_create(student=student)[0]
    existing = LedgerEntry.objects.filter(
        wallet=wallet, reason=reason, reference=reference
    ).first()
    if existing is not None:
        return existing

    new_balance = wallet.balance + amount
    if new_balance < 0:
        raise ValidationError("Недостаточно баллов.")

    wallet.balance = new_balance
    wallet.save(update_fields=["balance", "updated_at"])
    return LedgerEntry.objects.create(
        wallet=wallet, amount=amount, reason=reason, reference=reference,
        balance_after=new_balance, comment=comment, created_by=created_by,
    )


def grant(student, amount: int, reason: str, reference: str, **kwargs) -> LedgerEntry:
    if amount <= 0:
        raise ValidationError("Начисление должно быть положительным.")
    return record(student, amount=amount, reason=reason, reference=reference, **kwargs)


def spend(student, amount: int, reason: str, reference: str, **kwargs) -> LedgerEntry:
    if amount <= 0:
        raise ValidationError("Списание должно быть положительным.")
    return record(student, amount=-amount, reason=reason, reference=reference, **kwargs)


def reward_daily_challenge(student, challenge) -> LedgerEntry:
    """Награда за задание дня: одна на ученика и дату."""
    return grant(
        student,
        challenge.reward_coins,
        LedgerEntry.Reason.DAILY_CHALLENGE,
        reference=f"challenge:{challenge.date.isoformat()}",
        comment="Задание дня",
    )


def _reward_amount(key: str) -> int:
    from django.conf import settings

    return int(settings.COIN_REWARDS.get(key, 0))


def reward_for_xp(student, *, source: str, amount_xp: int, total_xp: int) -> LedgerEntry | None:
    """Монеты за то же событие, за которое начислен XP.

    XP — прогресс и стрики, монеты — покупки в магазине. Чтобы курсы не
    разъезжались, монеты считаются от XP одним коэффициентом. Ключ
    идемпотентности — итоговый XP: повторная обработка того же события даёт
    тот же итог и не платит дважды.
    """
    from django.conf import settings

    coins = int(round(amount_xp * settings.COINS_PER_XP))
    return _safe_grant(
        student, coins, LedgerEntry.Reason.XP_AWARD,
        reference=f"{source}:{total_xp}", comment="Награда за занятия",
    )


def reward_mistake_resolved(student, backlog_item) -> LedgerEntry | None:
    """Закрытая петля отработки: награда одна на пункт полки ошибок."""
    return _safe_grant(
        student,
        _reward_amount("mistake_resolved"),
        LedgerEntry.Reason.MISTAKE_RESOLVED,
        reference=f"backlog:{backlog_item.pk}",
        comment="Ошибка отработана",
    )


def reward_lesson_done(student, plan_item) -> LedgerEntry | None:
    """Пункт плана «урок» выполнен. Ключ — пункт плана, а не узел: повторное
    прохождение той же темы после забывания снова заслуживает награды."""
    return _safe_grant(
        student,
        _reward_amount("lesson_done"),
        LedgerEntry.Reason.LESSON_DONE,
        reference=f"plan-item:{plan_item.pk}",
        comment="Урок пройден",
    )


def reward_homework_done(student, homework) -> LedgerEntry | None:
    return _safe_grant(
        student,
        _reward_amount("homework_done"),
        LedgerEntry.Reason.HOMEWORK_DONE,
        reference=f"homework:{homework.pk}",
        comment=f"Домашка «{homework.title}»",
    )


def reward_mock_completed(student, mock_result) -> LedgerEntry | None:
    return _safe_grant(
        student,
        _reward_amount("mock_completed"),
        LedgerEntry.Reason.MOCK_COMPLETED,
        reference=f"mock-result:{mock_result.pk}",
        comment="Пробник пройден",
    )


def _safe_grant(student, amount: int, reason: str, reference: str, comment: str = ""):
    """Награда с нулевым размером — не ошибка: администратор мог её отключить."""
    if amount <= 0:
        return None
    return grant(student, amount, reason, reference, comment=comment)


@transaction.atomic
def purchase(student, item: ShopItem) -> InventoryItem | None:
    """Купить предмет.

    Косметику покупают один раз — она уходит в инвентарь. Расходник
    (заморозка стрика, ускоритель опыта) срабатывает сразу и покупается
    повторно, поэтому возвращается `None`: складывать его в инвентарь не во что.
    """
    if not item.is_available():
        raise ValidationError("Товар недоступен.")
    consumable = item.effect != ShopItem.Effect.NONE
    if not consumable and InventoryItem.objects.filter(student=student, item=item).exists():
        raise ValidationError("Этот предмет уже куплен.")

    spend(
        student,
        item.price_coins,
        LedgerEntry.Reason.PURCHASE,
        # Расходник покупается много раз, поэтому ключ идемпотентности
        # включает момент покупки, а не только сам предмет.
        reference=(
            f"item:{item.pk}:{timezone.now().timestamp():.0f}" if consumable
            else f"item:{item.pk}"
        ),
        comment=item.title,
    )
    if consumable:
        apply_effect(student, item)
        return None
    return InventoryItem.objects.create(student=student, item=item)


def apply_effect(student, item: ShopItem) -> None:
    """Выдать эффект расходника: заморозку стрика или ускоритель опыта."""
    from apps.gamification.models import GamificationProfile

    if item.effect == ShopItem.Effect.STREAK_FREEZE:
        profile, _ = GamificationProfile.objects.get_or_create(student=student)
        GamificationProfile.objects.filter(pk=profile.pk).update(
            streak_freezes=F("streak_freezes") + max(item.effect_value, 1)
        )
    elif item.effect == ShopItem.Effect.XP_BOOST:
        now = timezone.now()
        XpBoost.objects.create(
            student=student, item=item,
            bonus_percent=max(item.effect_value, 1),
            starts_at=now,
            ends_at=now + timedelta(hours=max(item.duration_hours, 1)),
        )


def active_boost(student, now=None) -> XpBoost | None:
    """Самый сильный действующий ускоритель. Ускорители не складываются."""
    now = now or timezone.now()
    return (
        XpBoost.objects.filter(student=student, starts_at__lte=now, ends_at__gt=now)
        .order_by("-bonus_percent")
        .first()
    )


def boosted_xp(student, amount: int, now=None) -> int:
    """XP с учётом ускорителя. Награда округляется вверх — в пользу ученика."""
    boost = active_boost(student, now)
    if boost is None or amount <= 0:
        return amount
    return amount + ceil(amount * boost.bonus_percent / 100)


@transaction.atomic
def equip(student, item: ShopItem) -> InventoryItem:
    """Надеть предмет; в одном слоте носится только один."""
    owned = InventoryItem.objects.filter(student=student, item=item).first()
    if owned is None:
        raise ValidationError("Предмет не куплен.")
    InventoryItem.objects.filter(
        student=student, item__slot=item.slot
    ).exclude(pk=owned.pk).update(is_equipped=False)
    owned.is_equipped = True
    owned.save(update_fields=["is_equipped"])
    return owned


def equipped_items(student) -> dict[str, InventoryItem]:
    return {
        inventory.item.slot: inventory
        for inventory in InventoryItem.objects.filter(
            student=student, is_equipped=True
        ).select_related("item")
    }


def storefront(now=None):
    """Витрина: активные товары, доступные по датам."""
    now = now or timezone.now()
    return [
        item
        for item in ShopItem.objects.select_related("category").filter(is_active=True)
        if item.is_available(now)
    ]


def wallet_summary(student) -> dict:
    wallet = get_wallet(student)
    return {
        "balance": wallet.balance,
        "earned": sum(
            entry.amount for entry in wallet.entries.all() if entry.amount > 0
        ),
        "spent": -sum(
            entry.amount for entry in wallet.entries.all() if entry.amount < 0
        ),
    }
