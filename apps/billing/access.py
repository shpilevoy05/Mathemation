"""Доступ к платной части продукта.

Гейт отделён от биллинга намеренно: платёж отвечает на вопрос «заплатили ли»,
а этот модуль — «можно ли прямо сейчас открыть занятие». Между ними стоит
пробный период, бесплатная часть витрины и роли сотрудников, и смешивать это с
жизненным циклом платежа нельзя — иначе любое изменение тарифа задевает доступ.

Разрез «бесплатно/платно» не зашит в код: список бесплатных возможностей и
длина пробного периода живут в настройках, потому что маркетинг меняет его
чаще, чем выходит релиз. По умолчанию гейт выключен (`BILLING_ENFORCED=0`):
пока эквайринг не подключён, закрывать доступ нечем, а включение — отдельное
осознанное решение владельца продукта.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone


class Feature:
    """Возможности, за которые берут деньги."""

    LESSONS = "lessons"
    PRACTICE = "practice"
    MOCKS = "mocks"
    EXPERT_REVIEW = "expert_review"
    AI_HINTS = "ai_hints"


FEATURE_TITLES = {
    Feature.LESSONS: "Занятия и конспекты",
    Feature.PRACTICE: "Решение задач и отработка",
    Feature.MOCKS: "Пробные экзамены",
    Feature.EXPERT_REVIEW: "Проверка экспертом",
    Feature.AI_HINTS: "Подсказки наставника",
}

# Причины отказа: интерфейс показывает по ним разный текст.
LOCKED_NO_SUBSCRIPTION = "no_subscription"
LOCKED_EXPIRED = "expired"


@dataclass(frozen=True)
class Access:
    """Ответ гейта. `reason` объясняет и разрешение, и отказ."""

    allowed: bool
    reason: str
    feature: str = ""
    ends_at: object = None
    days_left: int = 0

    @property
    def title(self) -> str:
        return FEATURE_TITLES.get(self.feature, "")


def free_features() -> set[str]:
    return set(getattr(settings, "FREE_FEATURES", ()) or ())


def is_enforced() -> bool:
    return bool(getattr(settings, "BILLING_ENFORCED", False))


def trial_days() -> int:
    return int(getattr(settings, "TRIAL_DAYS", 0) or 0)


def _trial_left(student, now) -> int:
    """Сколько дней пробного периода осталось. Считаем от регистрации ученика."""
    days = trial_days()
    if days <= 0:
        return 0
    joined = getattr(student.user, "date_joined", None)
    if joined is None:
        return 0
    ends_at = joined + timedelta(days=days)
    if ends_at <= now:
        return 0
    # Остаток округляем вверх: «остался 1 день» честнее, чем «0», пока доступ есть.
    return max(1, -((now - ends_at).days))


def _active_subscription(student):
    from .models import Subscription

    now = timezone.now()
    return (
        student.subscriptions.filter(
            status=Subscription.Status.ACTIVE, ends_at__gt=now
        )
        .order_by("-ends_at")
        .first()
    )


def _ever_subscribed(student) -> bool:
    from .models import Subscription

    return student.subscriptions.exclude(status=Subscription.Status.PENDING).exists()


def subscription_state(student) -> dict:
    """Состояние подписки для интерфейса: активна ли, до какого дня, пробный период."""
    now = timezone.now()
    subscription = _active_subscription(student) if student is not None else None
    trial_left = _trial_left(student, now) if student is not None else 0
    days_left = 0
    if subscription is not None and subscription.ends_at:
        days_left = max(0, (subscription.ends_at - now).days)
    return {
        "enforced": is_enforced(),
        "subscription": subscription,
        "is_active": subscription is not None,
        "ends_at": subscription.ends_at if subscription is not None else None,
        "days_left": days_left,
        "tariff": subscription.tariff if subscription is not None else None,
        "trial_days_left": trial_left,
        "in_trial": trial_left > 0 and subscription is None,
    }


def feature_access(user, feature: str) -> Access:
    """Можно ли пользователю открыть возможность `feature`.

    Сотрудники (методист, эксперт, администратор) проходят всегда: им нужно
    видеть продукт целиком, а денег они не платят.
    """
    if not is_enforced() or feature in free_features():
        return Access(True, "free", feature)
    if not getattr(user, "is_authenticated", False):
        return Access(False, LOCKED_NO_SUBSCRIPTION, feature)

    student = getattr(user, "student_profile", None)
    if student is None:
        # Не ученик — либо сотрудник, либо родитель: гейт не про них.
        return Access(True, "staff", feature)

    subscription = _active_subscription(student)
    if subscription is not None:
        now = timezone.now()
        return Access(
            True, "subscription", feature,
            ends_at=subscription.ends_at,
            days_left=max(0, (subscription.ends_at - now).days),
        )

    trial_left = _trial_left(student, timezone.now())
    if trial_left > 0:
        return Access(True, "trial", feature, days_left=trial_left)

    reason = LOCKED_EXPIRED if _ever_subscribed(student) else LOCKED_NO_SUBSCRIPTION
    return Access(False, reason, feature)


def deny_payload(access: Access) -> dict:
    """Тело ответа API при отказе: клиенту нужен и повод, и куда идти дальше."""
    return {
        "detail": (
            "Подписка закончилась — продлите её, чтобы продолжить."
            if access.reason == LOCKED_EXPIRED
            else "Эта часть платформы доступна по подписке."
        ),
        "code": "subscription_required",
        "feature": access.feature,
        "feature_title": access.title,
        "pricing_url": "/pricing/",
    }
