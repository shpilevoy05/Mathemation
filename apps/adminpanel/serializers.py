"""Сериализаторы панели администратора.

Панель редактирует доменные модели напрямую, поэтому сериализаторы плоские.
Всё, что меняет деньги, состояние подписки или баланс, идёт не через запись
полей, а через явные действия во вьюсетах — иначе редактирование строки
таблицы обходило бы правила домена.
"""

from rest_framework import serializers

from apps.accounts.models import Invite, StudentGroup, StudentProfile
from apps.billing.models import Payment, Subscription, Tariff
from apps.content.models import (
    Assignment,
    AssignmentVersion,
    DailyChallenge,
    Homework,
    HomeworkTask,
    Lesson,
    TheoryBlock,
)
from apps.economy.models import InventoryItem, LedgerEntry, ShopCategory, ShopItem, Wallet
from apps.knowledge.models import KnowledgeDependency, KnowledgeNode, TopicCluster
from apps.planning.models import PlanChangeLog, StudyPlan, StudyPlanItem


class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = "__all__"


class TheoryBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = TheoryBlock
        fields = "__all__"


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assignment
        fields = "__all__"


class AssignmentVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssignmentVersion
        fields = "__all__"
        # Версии не редактируются: правка — это новая версия.
        read_only_fields = [
            field.name for field in AssignmentVersion._meta.fields if field.name != "id"
        ]


class HomeworkTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeworkTask
        fields = "__all__"


class HomeworkSerializer(serializers.ModelSerializer):
    tasks = HomeworkTaskSerializer(many=True, read_only=True)

    class Meta:
        model = Homework
        fields = "__all__"


class DailyChallengeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyChallenge
        fields = "__all__"


class StudentSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    balance = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = [
            "id", "username", "is_active", "target_score", "start_score",
            "weekly_hours", "exam_date", "forecast_calibration", "balance",
        ]

    def get_balance(self, obj) -> int:
        wallet = getattr(obj, "wallet", None)
        return wallet.balance if wallet else 0


class StudentGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentGroup
        fields = "__all__"


class InviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invite
        fields = ["id", "code", "role", "group", "expires_at", "used_by", "used_at"]
        read_only_fields = ["code", "used_by", "used_at"]


class ShopCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopCategory
        fields = "__all__"


class ShopItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopItem
        fields = "__all__"


class LedgerEntrySerializer(serializers.ModelSerializer):
    student = serializers.CharField(source="wallet.student.user.username", read_only=True)

    class Meta:
        model = LedgerEntry
        fields = [
            "id", "student", "amount", "reason", "reference",
            "balance_after", "comment", "created_at",
        ]


class WalletSerializer(serializers.ModelSerializer):
    student = serializers.CharField(source="student.user.username", read_only=True)

    class Meta:
        model = Wallet
        fields = ["id", "student", "balance", "updated_at"]


class InventoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryItem
        fields = "__all__"


class TariffSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tariff
        fields = "__all__"
        # Цена меняется только новой версией тарифа (действие new_version).
        read_only_fields = ["version"]


class SubscriptionSerializer(serializers.ModelSerializer):
    student = serializers.CharField(source="student.user.username", read_only=True)

    class Meta:
        model = Subscription
        fields = ["id", "student", "tariff", "status", "starts_at", "ends_at", "created_at"]


class PaymentSerializer(serializers.ModelSerializer):
    student = serializers.CharField(source="student.user.username", read_only=True)
    payer = serializers.CharField(source="payer.username", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "student", "payer", "tariff", "amount_rub", "status",
            "provider", "provider_payment_id", "receipt_url", "created_at",
            "paid_at", "refunded_at",
        ]
        read_only_fields = fields


class TopicClusterSerializer(serializers.ModelSerializer):
    class Meta:
        model = TopicCluster
        fields = "__all__"


class KnowledgeNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeNode
        fields = "__all__"


class KnowledgeDependencySerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeDependency
        fields = "__all__"

    def validate(self, attrs):
        # Цикл ловится моделью, но сообщение должно дойти до формы панели.
        dependency = KnowledgeDependency(**attrs)
        dependency.clean()
        return attrs


class StudyPlanSerializer(serializers.ModelSerializer):
    student = serializers.CharField(source="student.user.username", read_only=True)

    class Meta:
        model = StudyPlan
        fields = ["id", "student", "target_score", "status", "created_at"]


class StudyPlanItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyPlanItem
        fields = "__all__"


class PlanChangeLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanChangeLog
        fields = "__all__"
