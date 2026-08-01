from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts import views as account_views
from apps.accounts.api import MeView, TargetScoreView
from apps.ai_mentor.api import HintView, ParentAiLogView
from apps.billing import pages as billing_pages
from apps.content.api import AssignmentViewSet, LessonViewSet, TrackView
from apps.content.student_api import (
    DailyChallengeView,
    MyHomeworkView,
    SubmitHomeworkView,
)
from apps.diagnostics.api import DiagnosticListView, StartDiagnosticView, SubmitDiagnosticView
from apps.economy.api import BuyItemView, EquipItemView, ShopView, WalletView
from apps.expert_review.api import (
    ExpertReviewFinishView,
    ExpertReviewListView,
    SolutionFileView,
    SubmitSolutionView,
)
from apps.gamification.api import GamificationView
from apps.knowledge.api import KnowledgeMapView, NodeDetailView
from apps.mocks.api import MockListView, StartMockView, SubmitMockView
from apps.planning.api import (
    AcknowledgeChangeView,
    AcknowledgeTrajectoryTransitionView,
    CompleteItemView,
    PlanChangesView,
    PlanView,
    TodayPlanView,
    TrajectoryView,
    WeekPlanView,
)
from apps.practice.api import (
    BacklogView,
    CompleteReviewView,
    DueReviewsView,
    NodePracticeView,
    SubmitAttemptView,
)
from apps.progress.api import ForecastView, ParentReportView, ProgressView
from apps.web import views as web_views

router = DefaultRouter()
router.register("lessons", LessonViewSet)
router.register("assignments", AssignmentViewSet)

api_urls = [
    path("", include(router.urls)),
    path("me/", MeView.as_view()),
    path("me/target/", TargetScoreView.as_view()),
    path("knowledge-map/", KnowledgeMapView.as_view()),
    path("nodes/<int:node_id>/", NodeDetailView.as_view()),
    path("nodes/<int:node_id>/practice/", NodePracticeView.as_view()),
    path("track/", TrackView.as_view()),
    path("assignments/<int:assignment_id>/attempt/", SubmitAttemptView.as_view()),
    path("assignments/<int:assignment_id>/hint/", HintView.as_view()),
    path("backlog/", BacklogView.as_view()),
    path("reviews/due/", DueReviewsView.as_view()),
    path("reviews/<int:review_id>/complete/", CompleteReviewView.as_view()),
    path("plan/", PlanView.as_view()),
    path("plan/today/", TodayPlanView.as_view()),
    path("plan/week/", WeekPlanView.as_view()),
    path("plan/items/<int:item_id>/complete/", CompleteItemView.as_view()),
    path("plan/changes/", PlanChangesView.as_view()),
    path("plan/changes/<int:change_id>/ack/", AcknowledgeChangeView.as_view()),
    path("trajectory/", TrajectoryView.as_view()),
    path(
        "trajectory/transitions/<int:transition_id>/ack/",
        AcknowledgeTrajectoryTransitionView.as_view(),
    ),
    path("diagnostics/", DiagnosticListView.as_view()),
    path("diagnostics/<int:test_id>/start/", StartDiagnosticView.as_view()),
    path("diagnostics/results/<int:result_id>/submit/", SubmitDiagnosticView.as_view()),
    path("mocks/", MockListView.as_view()),
    path("mocks/<int:exam_id>/start/", StartMockView.as_view()),
    path("mocks/results/<int:result_id>/submit/", SubmitMockView.as_view()),
    path("expert-reviews/", ExpertReviewListView.as_view()),
    path("expert-reviews/submit/", SubmitSolutionView.as_view()),
    path("expert-reviews/<int:review_id>/finish/", ExpertReviewFinishView.as_view()),
    path(
        "expert-reviews/<int:review_id>/file/",
        SolutionFileView.as_view(),
        name="expert-review-file",
    ),
    path("homework/", MyHomeworkView.as_view()),
    path("homework/<int:submission_id>/submit/", SubmitHomeworkView.as_view()),
    path("daily/", DailyChallengeView.as_view()),
    path("wallet/", WalletView.as_view()),
    path("shop/", ShopView.as_view()),
    path("shop/items/<int:item_id>/buy/", BuyItemView.as_view()),
    path("shop/items/<int:item_id>/equip/", EquipItemView.as_view()),
    path("progress/", ProgressView.as_view()),
    path("forecast/", ForecastView.as_view()),
    path("parent/report/", ParentReportView.as_view()),
    path("parent/ai-log/", ParentAiLogView.as_view()),
    path("gamification/", GamificationView.as_view()),
]

from apps.adminpanel.urls import api_urls as panel_api_urls, page_urls as panel_page_urls

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/admin/", include(panel_api_urls)),
    path("panel/", include(panel_page_urls)),
    path("api/", include(api_urls)),
    path("api-auth/", include("rest_framework.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("pricing/", billing_pages.pricing, name="pricing"),
    path("invite/", account_views.register_by_invite, name="register"),
    path("invite/<str:code>/", account_views.register_by_invite, name="register_by_invite"),
    path("", web_views.dashboard, name="dashboard"),
    path("map/", web_views.knowledge_map, name="knowledge_map"),
    path("map/node/<int:node_id>/", web_views.knowledge_node, name="knowledge_node"),
    path("track/", web_views.track, name="track"),
    path("lesson/<int:node_id>/", web_views.lesson, name="lesson"),
    path("practice/backlog/", web_views.practice_backlog, name="practice_backlog"),
    path("shop/", web_views.shop, name="shop"),
    path("homework/", web_views.homework, name="homework"),
    path("daily/", web_views.daily_challenge, name="daily_challenge"),
    path("forecast/", web_views.forecast, name="forecast"),
    path("mocks/", web_views.mocks, name="mocks"),
    path("mocks/run/<int:result_id>/", web_views.mock_run, name="mock_run"),
    path("mocks/result/<int:result_id>/", web_views.mock_result, name="mock_result"),
    path("parent/", web_views.parent_dashboard, name="parent_dashboard"),
    path("expert/", web_views.expert_queue, name="expert_queue"),
    path("expert/review/<int:review_id>/", web_views.expert_review, name="expert_review"),
    path("methodist/", web_views.methodist_dashboard, name="methodist_dashboard"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
