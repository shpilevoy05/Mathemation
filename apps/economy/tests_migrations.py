"""Уход «Ракеты»: вещь удаляется, владелец не остаётся с пустым кружком."""

from django.test import TestCase

from apps.knowledge.tests import make_student

from .catalog import load_cosmetics
from .migrations import _rocket
from .models import InventoryItem, ShopItem
from .services import cosmetic_codes


class RemoveRocketTests(TestCase):
    def setUp(self):
        load_cosmetics()
        self.student = make_student("rocket-owner")
        self.legacy = ShopItem.objects.create(
            title="Аватар «Ракета»", slot="avatar", code="rocket", price_coins=90
        )

    def own(self, *, equipped: bool) -> InventoryItem:
        return InventoryItem.objects.create(
            student=self.student, item=self.legacy, is_equipped=equipped
        )

    def test_item_disappears(self):
        self.own(equipped=False)

        _rocket.remove(ShopItem, InventoryItem)

        self.assertFalse(ShopItem.objects.filter(code="rocket").exists())
        self.assertFalse(InventoryItem.objects.filter(item_id=self.legacy.pk).exists())

    def test_owner_gets_a_base_avatar_instead(self):
        self.own(equipped=True)

        _rocket.remove(ShopItem, InventoryItem)

        # Без замены ученик остался бы с буквой вместо картинки и без причины.
        self.assertEqual(cosmetic_codes(self.student)["avatar"], "sigma")

    def test_other_avatars_are_left_alone(self):
        owl = ShopItem.objects.get(slot="avatar", code="owl")
        InventoryItem.objects.create(student=self.student, item=owl, is_equipped=True)
        self.own(equipped=False)

        _rocket.remove(ShopItem, InventoryItem)

        self.assertEqual(cosmetic_codes(self.student)["avatar"], "owl")

    def test_running_twice_is_safe(self):
        self.own(equipped=True)
        _rocket.remove(ShopItem, InventoryItem)

        _rocket.remove(ShopItem, InventoryItem)

        self.assertFalse(ShopItem.objects.filter(code="rocket").exists())
