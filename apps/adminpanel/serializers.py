"""Сериализаторы панели администратора.

Панель редактирует доменные модели напрямую, поэтому сериализаторы плоские.
Всё, что меняет деньги, состояние подписки или баланс, идёт не через запись
полей, а через явные действия во вьюсетах — иначе редактирование строки
таблицы обходило бы правила домена.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import Invite, StudentGroup, StudentProfile
from apps.billing.models import (
    AddOn,
    Payment,
    PaymentMethod,
    Promotion,
    Subscription,
    Tariff,
)
from apps.content.models import (
    Assignment,
    AssignmentVersion,
    DailyChallenge,
    Homework,
    HomeworkTask,
    Lesson,
    SolutionPath,
    SolutionStep,
    TheoryBlock,
)
from apps.arena.models import Friendship, Match
from apps.economy.models import InventoryItem, LedgerEntry, ShopCategory, ShopItem, Wallet
from apps.knowledge.models import KnowledgeDependency, KnowledgeNode, TopicCluster
from apps.exams.models import ExamProfile, ExamTask
from apps.planning.models import PlanChangeLog, StudyPlan, StudyPlanItem
from apps.progress.models import ForecastObservation


class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = "__all__"

    def validate_video_url(self, value):
        """Ссылку проверяем здесь же: панель — обычный путь заполнения урока,
        и правило про разрешённые хосты не должно действовать только в админке.
        """
        from apps.content.video import validate_video_url

        try:
            validate_video_url(value)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages)
        return value


class TheoryBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = TheoryBlock
        fields = "__all__"


class AssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assignment
        fields = "__all__"

    def validate(self, attrs):
        """Эталон ответа должен разбираться — иначе задача тихо ломается.

        Проверяем здесь же, а не только в админке: панель — обычный путь
        заполнения задачи.
        """
        merged = {**({} if self.instance is None else {
            "answer_type": self.instance.answer_type,
            "answer_spec": self.instance.answer_spec,
        }), **attrs}
        assignment = Assignment(
            answer_type=merged.get("answer_type", Assignment.AnswerType.TEXT),
            answer_spec=merged.get("answer_spec") or {},
        )
        try:
            assignment.clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                error.message_dict if hasattr(error, "message_dict") else error.messages
            )
        return attrs


class SolutionPathSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolutionPath
        fields = "__all__"


class SolutionStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolutionStep
        fields = "__all__"

    def validate_node(self, node):
        """Шаг указывает на навык: у папки нет ни практики, ни своего освоения."""
        if node.is_group:
            raise serializers.ValidationError(
                "Шаг должен указывать на навык, а не на папку навыков."
            )
        return node


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
            "weekly_hours", "exam_date", "primary_calibration",
            "primary_error_variance", "calibration_samples", "balance",
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
        # Цена и версия правкой строки не меняются: изменение цены — это новая
        # версия тарифа (действие «Новая цена»), иначе у оплаченного периода
        # задним числом поменялись бы условия.
        read_only_fields = ["version", "price_rub"]


class AddOnSerializer(serializers.ModelSerializer):
    price_per_unit = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = AddOn
        fields = [
            "id", "code", "kind", "title", "description", "price_rub",
            "quantity", "unit_label", "is_active", "order", "price_per_unit",
        ]


class PaymentMethodSerializer(serializers.ModelSerializer):
    is_placeholder = serializers.BooleanField(read_only=True)

    class Meta:
        model = PaymentMethod
        fields = [
            "id", "code", "title", "description", "instructions",
            "provider_key", "is_active", "order", "is_placeholder",
        ]


class PromotionSerializer(serializers.ModelSerializer):
    is_running = serializers.SerializerMethodField()

    class Meta:
        model = Promotion
        fields = [
            "id", "title", "description", "code", "kind", "value", "tariff_codes",
            "starts_at", "ends_at", "max_uses", "used_count", "is_active",
            "created_at", "is_running",
        ]
        # Счётчик применений двигает домен при создании платежа, не редактор.
        read_only_fields = ["used_count", "created_at"]

    def get_is_running(self, promotion) -> bool:
        return promotion.is_running()


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


class ExamProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamProfile
        fields = "__all__"


class ExamTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamTask
        fields = "__all__"


class ForecastObservationSerializer(serializers.ModelSerializer):
    student = serializers.CharField(source="student.user.username", read_only=True)

    class Meta:
        model = ForecastObservation
        fields = [
            "id", "student", "mock_result", "predicted_primary", "actual_primary",
            "error", "calibration_after", "created_at",
        ]


class MatchSerializer(serializers.ModelSerializer):
    """Партии только читаются: результат — история, а не настройка."""

    created_by = serializers.CharField(source="created_by.user.username", read_only=True)

    class Meta:
        model = Match
        fields = [
            "id", "mode", "status", "created_by", "bot_level",
            "ege_task_number", "created_at", "finished_at",
        ]
        read_only_fields = fields


class FriendshipSerializer(serializers.ModelSerializer):
    from_student = serializers.CharField(source="from_student.user.username", read_only=True)
    to_student = serializers.CharField(source="to_student.user.username", read_only=True)

    class Meta:
        model = Friendship
        fields = ["id", "from_student", "to_student", "status", "created_at"]
        read_only_fields = fields
