"""Внутренняя валюта и магазин косметики.

Три правила, из которых следует вся модель:

1. Валюта зарабатывается только учебными событиями и начисляется через
   :mod:`apps.economy.services` — иначе баланс накручивается повторными
   вызовами и его нельзя объяснить ученику или родителю.
2. Каждое движение денег — запись в реестре с ключом идемпотентности. Баланс
   кошелька производный: он всегда равен сумме записей.
3. Косметика не влияет на обучение: у товаров нет связи с mastery, планом и
   прогнозом. Иначе платный (или гриндовый) предмет начинает менять оценку
   знаний ребёнка.
"""

from __future__ import annotations

from django.db import models


class Wallet(models.Model):
    student = models.OneToOneField(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="wallet"
    )
    balance = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(balance__gte=0), name="wallet_balance_non_negative"
            )
        ]

    def __str__(self):
        return f"Кошелёк {self.student.user.username}: {self.balance}"


class LedgerEntry(models.Model):
    """Движение по кошельку. Реестр не редактируется и не удаляется."""

    class Reason(models.TextChoices):
        # Основной источник: то же событие, за которое начислен XP.
        XP_AWARD = "xp_award"
        DAILY_CHALLENGE = "daily_challenge"
        HOMEWORK_DONE = "homework_done"
        LESSON_DONE = "lesson_done"
        MOCK_COMPLETED = "mock_completed"
        MISTAKE_RESOLVED = "mistake_resolved"
        PURCHASE = "purchase"
        ADMIN_GRANT = "admin_grant"
        REFUND = "refund"

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="entries")
    amount = models.IntegerField()  # + начисление, − списание
    reason = models.CharField(max_length=32, choices=Reason.choices)
    # Ключ идемпотентности: идентификатор события (задание дня + дата, покупка,
    # закрытая ошибка). Повторное начисление за то же событие невозможно.
    reference = models.CharField(max_length=64)
    balance_after = models.IntegerField()
    comment = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="granted_coins",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["wallet", "reason", "reference"], name="uniq_ledger_event"
            )
        ]


class ShopCategory(models.Model):
    title = models.CharField(max_length=200)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "title"]
        verbose_name_plural = "shop categories"

    def __str__(self):
        return self.title


class ShopItem(models.Model):
    """Косметический предмет: аватар, рамка, тема оформления, значок."""

    class Slot(models.TextChoices):
        AVATAR = "avatar"
        FRAME = "frame"
        THEME = "theme"
        BADGE = "badge"

    category = models.ForeignKey(
        ShopCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="items"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    slot = models.CharField(max_length=16, choices=Slot.choices, default=Slot.AVATAR)
    image_url = models.URLField(max_length=500, blank=True)
    price_coins = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    available_from = models.DateTimeField(null=True, blank=True)
    available_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["slot", "price_coins", "title"]

    def __str__(self):
        return f"{self.title} ({self.price_coins})"

    def is_available(self, now=None) -> bool:
        from django.utils import timezone

        now = now or timezone.now()
        if not self.is_active:
            return False
        if self.available_from and now < self.available_from:
            return False
        if self.available_to and now > self.available_to:
            return False
        return True


class InventoryItem(models.Model):
    """Купленный предмет и его надетость."""

    student = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="inventory"
    )
    item = models.ForeignKey(ShopItem, on_delete=models.PROTECT, related_name="owners")
    is_equipped = models.BooleanField(default=False)
    acquired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-acquired_at"]
        constraints = [
            models.UniqueConstraint(fields=["student", "item"], name="uniq_student_item")
        ]
