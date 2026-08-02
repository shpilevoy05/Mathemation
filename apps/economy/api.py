"""Кабинет ученика: кошелёк, витрина, покупки и примерка."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import views
from rest_framework.response import Response

from apps.accounts.api import get_student

from .models import InventoryItem, ShopItem
from .services import active_boost, equip, equipped_items, get_wallet, purchase, storefront


def _item_payload(item: ShopItem, owned_ids: set[int], equipped_ids: set[int]) -> dict:
    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "slot": item.slot,
        "image_url": item.image_url,
        "price_coins": item.price_coins,
        "owned": item.id in owned_ids,
        "equipped": item.id in equipped_ids,
    }


class WalletView(views.APIView):
    """GET /api/wallet/ — баланс и последние движения."""

    def get(self, request):
        student = get_student(request)
        wallet = get_wallet(student)
        entries = wallet.entries.all()[:20]
        return Response({
            "balance": wallet.balance,
            "entries": [
                {
                    "amount": entry.amount,
                    "reason": entry.reason,
                    "comment": entry.comment,
                    "balance_after": entry.balance_after,
                    "created_at": entry.created_at,
                }
                for entry in entries
            ],
        })


class ShopView(views.APIView):
    """GET /api/shop/ — витрина с отметками «куплено» и «надето»."""

    def get(self, request):
        student = get_student(request)
        inventory = InventoryItem.objects.filter(student=student).select_related("item")
        owned_ids = {inv.item_id for inv in inventory}
        equipped_ids = {inv.item_id for inv in inventory if inv.is_equipped}
        return Response({
            "balance": get_wallet(student).balance,
            "items": [
                _item_payload(item, owned_ids, equipped_ids) for item in storefront()
            ],
        })


class BuyItemView(views.APIView):
    """POST /api/shop/items/<id>/buy/"""

    def post(self, request, item_id: int):
        student = get_student(request)
        item = get_object_or_404(ShopItem, pk=item_id)
        try:
            inventory = purchase(student, item)
        except DjangoValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=400)
        # Расходник не попадает в инвентарь: он сработал сразу, и надевать
        # его нечем — клиенту важно отличать эти два случая.
        boost = active_boost(student)
        return Response({
            "balance": get_wallet(student).balance,
            "owned": inventory is not None,
            "consumable": inventory is None,
            "effect": item.effect,
            "streak_freezes": (
                student.gamification_profile.streak_freezes
                if hasattr(student, "gamification_profile") else 0
            ),
            "boost_percent": boost.bonus_percent if boost else 0,
        }, status=201)


class EquipItemView(views.APIView):
    """POST /api/shop/items/<id>/equip/ — в слоте носится один предмет."""

    def post(self, request, item_id: int):
        student = get_student(request)
        item = get_object_or_404(ShopItem, pk=item_id)
        try:
            equip(student, item)
        except DjangoValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=400)
        return Response({
            "equipped": {slot: inv.item_id for slot, inv in equipped_items(student).items()}
        })
