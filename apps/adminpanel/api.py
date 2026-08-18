"""API панели администратора.

Всё под `IsPlatformAdmin`. Простые справочники редактируются как есть; всё,
что меняет деньги, подписку, баланс или выдачу домашки, вынесено в явные
действия — правила домена не должны обходиться правкой поля в таблице.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.models import Invite, StudentGroup, StudentProfile
from apps.accounts.permissions import IsPlatformAdmin
from apps.accounts.services import create_invite, deactivate_student, reactivate_student
from apps.billing.models import (
    AddOn,
    Payment,
    PaymentMethod,
    Promotion,
    Subscription,
    Tariff,
)
from apps.billing.services import new_tariff_version, refund_payment
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
from apps.content.services import (
    assign_homework,
    assign_homework_to_group,
    publish_assignment_version,
    publish_lesson,
    unpublish_lesson,
)
from apps.economy.models import InventoryItem, LedgerEntry, ShopCategory, ShopItem, Wallet
from apps.economy.services import grant
from apps.knowledge.models import KnowledgeDependency, KnowledgeNode, TopicCluster
from apps.exams.models import ExamProfile, ExamTask
from apps.planning.models import PlanChangeLog, StudyPlan, StudyPlanItem
from apps.progress.models import ForecastObservation
from apps.planning.services import log_plan_change

from . import serializers as panel
from .audit import log_admin_action


def _domain_errors(function, *args, **kwargs):
    """Ошибки домена показываем в форме панели, а не 500."""
    try:
        return function(*args, **kwargs)
    except DjangoValidationError as exc:
        raise ValidationError({"detail": " ".join(exc.messages)}) from exc


class PanelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsPlatformAdmin]


class LessonViewSet(PanelViewSet):
    queryset = Lesson.objects.select_related("node")
    serializer_class = panel.LessonSerializer

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        lesson = _domain_errors(publish_lesson, self.get_object())
        log_admin_action(request.user, "lesson.publish", target=f"lesson:{lesson.pk}",
                         title=lesson.title)
        return Response(self.get_serializer(lesson).data)

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        lesson = unpublish_lesson(self.get_object())
        log_admin_action(request.user, "lesson.unpublish", target=f"lesson:{lesson.pk}",
                         title=lesson.title)
        return Response(self.get_serializer(lesson).data)


class TheoryBlockViewSet(PanelViewSet):
    queryset = TheoryBlock.objects.select_related("lesson")
    serializer_class = panel.TheoryBlockSerializer


class AssignmentViewSet(PanelViewSet):
    queryset = Assignment.objects.prefetch_related("versions")
    serializer_class = panel.AssignmentSerializer

    @action(detail=True, methods=["post"], url_path="new-version")
    def new_version(self, request, pk=None):
        """Правка условия или ответа — новой версией, чтобы история попыток
        осталась верной."""
        version = _domain_errors(
            publish_assignment_version,
            self.get_object(),
            change_note=request.data.get("change_note", ""),
            created_by=request.user,
            **{
                field: request.data[field]
                for field in (
                    "statement", "correct_answer", "reference_solution",
                    "max_score", "difficulty",
                )
                if field in request.data
            },
        )
        return Response(
            panel.AssignmentVersionSerializer(version).data, status=status.HTTP_201_CREATED
        )


class MatchViewSet(PanelViewSet):
    from apps.arena.models import Match as _Match

    queryset = _Match.objects.select_related("created_by__user")
    serializer_class = panel.MatchSerializer
    http_method_names = ["get", "head", "options"]


class FriendshipViewSet(PanelViewSet):
    from apps.arena.models import Friendship as _Friendship

    queryset = _Friendship.objects.select_related("from_student__user", "to_student__user")
    serializer_class = panel.FriendshipSerializer
    http_method_names = ["get", "head", "options"]


class SolutionPathViewSet(PanelViewSet):
    queryset = SolutionPath.objects.select_related("assignment")
    serializer_class = panel.SolutionPathSerializer


class SolutionStepViewSet(PanelViewSet):
    queryset = SolutionStep.objects.select_related("path", "node")
    serializer_class = panel.SolutionStepSerializer


class AssignmentVersionViewSet(PanelViewSet):
    """История версий: только чтение, правки идут новой версией."""

    queryset = AssignmentVersion.objects.select_related("assignment")
    serializer_class = panel.AssignmentVersionSerializer
    http_method_names = ["get", "head", "options"]


class HomeworkViewSet(PanelViewSet):
    queryset = Homework.objects.prefetch_related("tasks")
    serializer_class = panel.HomeworkSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """Выдать домашку ученикам или группе целиком."""
        homework = self.get_object()
        group_id = request.data.get("group")
        student_ids = request.data.get("students") or []
        if group_id:
            group = StudentGroup.objects.filter(pk=group_id).first()
            if group is None:
                raise ValidationError({"group": "Группа не найдена."})
            submissions = _domain_errors(assign_homework_to_group, homework, group)
        else:
            students = StudentProfile.objects.filter(
                pk__in=student_ids, user__is_active=True
            )
            if not students:
                raise ValidationError({"students": "Не выбран ни один активный ученик."})
            submissions = _domain_errors(assign_homework, homework, list(students))
        log_admin_action(
            request.user, "homework.assign", target=f"homework:{homework.pk}",
            title=homework.title, assigned=len(submissions),
            group_id=group_id or None,
        )
        return Response({"assigned": len(submissions)}, status=status.HTTP_201_CREATED)


class HomeworkTaskViewSet(PanelViewSet):
    queryset = HomeworkTask.objects.select_related("homework", "assignment")
    serializer_class = panel.HomeworkTaskSerializer


class DailyChallengeViewSet(PanelViewSet):
    queryset = DailyChallenge.objects.select_related("assignment")
    serializer_class = panel.DailyChallengeSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class StudentViewSet(PanelViewSet):
    queryset = StudentProfile.objects.select_related("user", "wallet")
    serializer_class = panel.StudentSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        # Удаление увело бы за собой попытки, ошибки и работы второй части.
        student = deactivate_student(self.get_object())
        log_admin_action(request.user, "student.deactivate", target=f"student:{student.pk}",
                         student=student)
        return Response(self.get_serializer(student).data)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        student = reactivate_student(self.get_object())
        log_admin_action(request.user, "student.reactivate", target=f"student:{student.pk}",
                         student=student)
        return Response(self.get_serializer(student).data)

    @action(detail=True, methods=["post"], url_path="grant-coins")
    def grant_coins(self, request, pk=None):
        student = self.get_object()
        try:
            amount = int(request.data.get("amount", 0))
        except (TypeError, ValueError):
            raise ValidationError({"amount": "Нужно число."})
        comment = request.data.get("comment", "")
        reference = request.data.get("reference") or f"manual:{timezone.now().isoformat()}"
        entry = _domain_errors(
            grant, student, amount, LedgerEntry.Reason.ADMIN_GRANT, reference,
            comment=comment, created_by=request.user,
        )
        log_admin_action(
            request.user, "student.grant_coins", target=f"student:{student.pk}",
            student=student, amount=amount, comment=comment, reference=reference,
        )
        return Response({"balance": entry.balance_after})


class StudentGroupViewSet(PanelViewSet):
    queryset = StudentGroup.objects.prefetch_related("students")
    serializer_class = panel.StudentGroupSerializer


class InviteViewSet(PanelViewSet):
    queryset = Invite.objects.select_related("group")
    serializer_class = panel.InviteSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    def create(self, request, *args, **kwargs):
        invite = create_invite(
            request.user,
            role=request.data.get("role", "student"),
            group=StudentGroup.objects.filter(pk=request.data.get("group")).first(),
        )
        return Response(self.get_serializer(invite).data, status=status.HTTP_201_CREATED)


class ShopCategoryViewSet(PanelViewSet):
    queryset = ShopCategory.objects.all()
    serializer_class = panel.ShopCategorySerializer


class ShopItemViewSet(PanelViewSet):
    queryset = ShopItem.objects.select_related("category")
    serializer_class = panel.ShopItemSerializer


class WalletViewSet(PanelViewSet):
    queryset = Wallet.objects.select_related("student__user")
    serializer_class = panel.WalletSerializer
    http_method_names = ["get", "head", "options"]


class LedgerEntryViewSet(PanelViewSet):
    """Реестр только для чтения: движения не редактируются задним числом."""

    queryset = LedgerEntry.objects.select_related("wallet__student__user")
    serializer_class = panel.LedgerEntrySerializer
    http_method_names = ["get", "head", "options"]


class InventoryItemViewSet(PanelViewSet):
    queryset = InventoryItem.objects.select_related("student__user", "item")
    serializer_class = panel.InventoryItemSerializer
    http_method_names = ["get", "head", "options"]


class TariffViewSet(PanelViewSet):
    queryset = Tariff.objects.all()
    serializer_class = panel.TariffSerializer

    @action(detail=True, methods=["post"], url_path="new-version")
    def new_version(self, request, pk=None):
        """Изменение цены — новая версия тарифа, старая уходит в архив."""
        price = request.data.get("price_rub")
        if price in (None, ""):
            raise ValidationError({"price_rub": "Укажите цену."})
        previous = self.get_object()
        updated = _domain_errors(
            new_tariff_version, previous, price_rub=price,
            title=request.data.get("title", previous.title),
        )
        log_admin_action(
            request.user, "tariff.new_version", target=f"tariff:{updated.pk}",
            code=updated.code, version=updated.version,
            price_from=str(previous.price_rub), price_to=str(updated.price_rub),
        )
        return Response(self.get_serializer(updated).data, status=status.HTTP_201_CREATED)


class AddOnViewSet(PanelViewSet):
    """Докупки сверх тарифа."""

    queryset = AddOn.objects.all()
    serializer_class = panel.AddOnSerializer


class PaymentMethodViewSet(PanelViewSet):
    """Способы оплаты на витрине тарифов."""

    queryset = PaymentMethod.objects.all()
    serializer_class = panel.PaymentMethodSerializer


class PromotionViewSet(PanelViewSet):
    """Скидки и акции поверх версионированных цен."""

    queryset = Promotion.objects.all()
    serializer_class = panel.PromotionSerializer


class SubscriptionViewSet(PanelViewSet):
    queryset = Subscription.objects.select_related("student__user", "tariff")
    serializer_class = panel.SubscriptionSerializer
    http_method_names = ["get", "head", "options"]


class PaymentViewSet(PanelViewSet):
    queryset = Payment.objects.select_related("student__user", "payer", "tariff")
    serializer_class = panel.PaymentSerializer
    http_method_names = ["get", "post", "head", "options"]

    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        payment = _domain_errors(refund_payment, self.get_object())
        log_admin_action(
            request.user, "payment.refund", target=f"payment:{payment.pk}",
            student=payment.student, amount=str(payment.amount_rub),
        )
        return Response(self.get_serializer(payment).data)


class TopicClusterViewSet(PanelViewSet):
    queryset = TopicCluster.objects.all()
    serializer_class = panel.TopicClusterSerializer


class KnowledgeNodeViewSet(PanelViewSet):
    queryset = KnowledgeNode.objects.select_related("cluster")
    serializer_class = panel.KnowledgeNodeSerializer


class KnowledgeDependencyViewSet(PanelViewSet):
    queryset = KnowledgeDependency.objects.select_related("node", "prerequisite")
    serializer_class = panel.KnowledgeDependencySerializer


class StudyPlanViewSet(PanelViewSet):
    queryset = StudyPlan.objects.select_related("student__user")
    serializer_class = panel.StudyPlanSerializer
    http_method_names = ["get", "head", "options"]


class StudyPlanItemViewSet(PanelViewSet):
    queryset = StudyPlanItem.objects.select_related("plan__student__user", "node")
    serializer_class = panel.StudyPlanItemSerializer

    def _log_manual_change(self, item: StudyPlanItem, text: str) -> None:
        log_plan_change(
            item.plan.student,
            reason=PlanChangeLog.Reason.MANUAL,
            description=text,
            node=item.node,
        )

    def perform_create(self, serializer):
        item = serializer.save()
        self._log_manual_change(
            item, f"Куратор добавил в план пункт «{item.node or item.item_type}»."
        )

    def perform_update(self, serializer):
        item = serializer.save()
        self._log_manual_change(
            item, f"Куратор изменил пункт плана «{item.node or item.item_type}»."
        )

    def perform_destroy(self, instance):
        self._log_manual_change(
            instance, f"Куратор убрал из плана пункт «{instance.node or instance.item_type}»."
        )
        instance.delete()


class PlanChangeLogViewSet(PanelViewSet):
    queryset = PlanChangeLog.objects.select_related("plan__student__user", "node")
    serializer_class = panel.PlanChangeLogSerializer
    http_method_names = ["get", "head", "options"]


class ExamProfileViewSet(PanelViewSet):
    """Профиль экзамена на год: по нему считается прогноз."""

    queryset = ExamProfile.objects.prefetch_related("tasks")
    serializer_class = panel.ExamProfileSerializer


class ExamTaskViewSet(PanelViewSet):
    queryset = ExamTask.objects.select_related("profile")
    serializer_class = panel.ExamTaskSerializer


class ForecastObservationViewSet(PanelViewSet):
    """Пары «прогноз — факт»: по ним видно, калиброван ли прогноз."""

    queryset = ForecastObservation.objects.select_related("student__user")
    serializer_class = panel.ForecastObservationSerializer
    http_method_names = ["get", "head", "options"]
