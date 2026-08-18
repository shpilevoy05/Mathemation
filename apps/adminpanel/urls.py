"""Маршруты панели: API под /api/admin/ и страница под /panel/."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api
from .views import panel_view

router = DefaultRouter()
router.register("lessons", api.LessonViewSet, basename="panel-lesson")
router.register("theory-blocks", api.TheoryBlockViewSet, basename="panel-theory")
router.register("assignments", api.AssignmentViewSet, basename="panel-assignment")
router.register(
    "assignment-versions", api.AssignmentVersionViewSet, basename="panel-assignment-version"
)
router.register("matches", api.MatchViewSet, basename="panel-match")
router.register("friendships", api.FriendshipViewSet, basename="panel-friendship")
router.register("solution-paths", api.SolutionPathViewSet, basename="panel-solution-path")
router.register("solution-steps", api.SolutionStepViewSet, basename="panel-solution-step")
router.register("homeworks", api.HomeworkViewSet, basename="panel-homework")
router.register("homework-tasks", api.HomeworkTaskViewSet, basename="panel-homework-task")
router.register("daily-challenges", api.DailyChallengeViewSet, basename="panel-daily")
router.register("students", api.StudentViewSet, basename="panel-student")
router.register("groups", api.StudentGroupViewSet, basename="panel-group")
router.register("invites", api.InviteViewSet, basename="panel-invite")
router.register("shop-categories", api.ShopCategoryViewSet, basename="panel-shop-category")
router.register("shop-items", api.ShopItemViewSet, basename="panel-shop-item")
router.register("wallets", api.WalletViewSet, basename="panel-wallet")
router.register("ledger", api.LedgerEntryViewSet, basename="panel-ledger")
router.register("inventory", api.InventoryItemViewSet, basename="panel-inventory")
router.register("tariffs", api.TariffViewSet, basename="panel-tariff")
router.register("addons", api.AddOnViewSet, basename="panel-addon")
router.register("payment-methods", api.PaymentMethodViewSet, basename="panel-payment-method")
router.register("promotions", api.PromotionViewSet, basename="panel-promotion")
router.register("subscriptions", api.SubscriptionViewSet, basename="panel-subscription")
router.register("payments", api.PaymentViewSet, basename="panel-payment")
router.register("clusters", api.TopicClusterViewSet, basename="panel-cluster")
router.register("nodes", api.KnowledgeNodeViewSet, basename="panel-node")
router.register("dependencies", api.KnowledgeDependencyViewSet, basename="panel-dependency")
router.register("exam-profiles", api.ExamProfileViewSet, basename="panel-exam-profile")
router.register("exam-tasks", api.ExamTaskViewSet, basename="panel-exam-task")
router.register(
    "forecast-observations", api.ForecastObservationViewSet,
    basename="panel-forecast-observation",
)
router.register("plans", api.StudyPlanViewSet, basename="panel-plan")
router.register("plan-items", api.StudyPlanItemViewSet, basename="panel-plan-item")
router.register("plan-changes", api.PlanChangeLogViewSet, basename="panel-plan-change")

api_urls = [path("", include(router.urls))]
page_urls = [path("", panel_view, name="admin-panel")]
