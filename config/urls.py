from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, reverse_lazy
from rest_framework.routers import DefaultRouter

from config.health import healthz, readyz

from apps.accounts import views as account_views
from apps.accounts.api import MeView, TargetScoreView
from apps.ai_mentor.api import HintView, ParentAiLogView
from apps.arena.api import (
    BoardAnswerView,
    BotFallbackView,
    CreateMatchView,
    FriendAnswerView,
    FriendListView,
    FriendRequestView,
    MatchAnswerView,
    MatchInviteView,
    MatchCancelView,
    MatchJoinView,
    MatchLeaveView,
    MatchView,
    PickCellView,
    QueueView,
    QuizAnswerView,
)
from apps.billing import pages as billing_pages
from apps.billing.api import PaymentWebhookView, SubscriptionView
from apps.content.api import AssignmentViewSet, LessonViewSet, TrackView
from apps.content.lesson_api import LessonStageView, lesson_summary
from apps.content.video_api import LessonPlaybackView
from apps.content.student_api import (
    DailyChallengeView,
    MyHomeworkView,
    SubmitHomeworkView,
)
from apps.diagnostics.api import DiagnosticListView, StartDiagnosticView, SubmitDiagnosticView
from apps.economy.api import (
    BuyItemView,
    EquipItemView,
    ResetLookView,
    ShopView,
    UnequipItemView,
    WalletView,
)
from apps.expert_review.api import (
    ExpertReviewFinishView,
    ExpertReviewListView,
    SolutionFileView,
    SubmitSolutionView,
)
from apps.gamification.api import GamificationView, LeagueOptInView, LeagueView
from apps.knowledge.api import KnowledgeMapView, NodeDetailView
from apps.mocks.api import MockDraftView, MockListView, StartMockView, SubmitMockView
from apps.planning.api import (
    AcknowledgeChangeView,
    MoveItemView,
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
from apps.progress.api import (
    ApplyForecastView,
    ForecastView,
    ParentReportView,
    ProgressView,
)
from apps.web import views as web_views
from apps.legal import views as legal_views
from apps.legal.api import FeedbackView

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
    path("plan/items/<int:item_id>/move/", MoveItemView.as_view()),
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
    path("mocks/results/<int:result_id>/draft/", MockDraftView.as_view()),
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
    path("lessons/<int:node_id>/stages/", LessonStageView.as_view()),
    # Ссылка на видео выдаётся запросом, а не рендерится в HTML.
    path("lessons/<int:lesson_id>/playback/", LessonPlaybackView.as_view(), name="lesson-playback"),
    path("wallet/", WalletView.as_view()),
    path("shop/", ShopView.as_view()),
    path("shop/items/<int:item_id>/buy/", BuyItemView.as_view()),
    path("shop/items/<int:item_id>/equip/", EquipItemView.as_view()),
    path("shop/items/<int:item_id>/unequip/", UnequipItemView.as_view()),
    path("shop/reset-look/", ResetLookView.as_view()),
    path("progress/", ProgressView.as_view()),
    path("forecast/", ForecastView.as_view()),
    path("forecast/apply/", ApplyForecastView.as_view()),
    path("parent/report/", ParentReportView.as_view()),
    path("parent/ai-log/", ParentAiLogView.as_view()),
    path("gamification/", GamificationView.as_view()),
    path("leagues/", LeagueView.as_view()),
    path("leagues/participation/", LeagueOptInView.as_view()),
    path("arena/friends/", FriendListView.as_view()),
    path("arena/friends/request/", FriendRequestView.as_view()),
    path("arena/friends/<int:link_id>/<str:action>/", FriendAnswerView.as_view()),
    path("arena/queue/", QueueView.as_view()),
    path("arena/queue/bot/", BotFallbackView.as_view()),
    path("arena/matches/", CreateMatchView.as_view()),
    path("arena/matches/<int:match_id>/", MatchView.as_view()),
    path("arena/matches/<int:match_id>/answer/", MatchAnswerView.as_view()),
    path("arena/matches/<int:match_id>/quiz/", QuizAnswerView.as_view()),
    path("arena/matches/<int:match_id>/pick/", PickCellView.as_view()),
    path("arena/matches/<int:match_id>/board/", BoardAnswerView.as_view()),
    path("arena/matches/<int:match_id>/join/", MatchJoinView.as_view()),
    path("arena/matches/<int:match_id>/cancel/", MatchCancelView.as_view()),
    path("arena/matches/<int:match_id>/leave/", MatchLeaveView.as_view()),
    # Общий маршрут идёт последним: иначе «quiz» и «pick» попали бы в него
    # как названия действий над приглашением.
    path("arena/matches/<int:match_id>/<str:action>/", MatchInviteView.as_view()),
    path("billing/subscription/", SubscriptionView.as_view()),
    # Колбэк эквайринга: без сессии, проверяется подписью тела.
    path("billing/webhook/", PaymentWebhookView.as_view(), name="billing-webhook"),
]

from apps.adminpanel.urls import api_urls as panel_api_urls, page_urls as panel_page_urls

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    path("admin/", admin.site.urls),
    path("api/admin/", include(panel_api_urls)),
    path("panel/", include(panel_page_urls)),
    path("studio/", include("apps.studio.urls")),
    path("api/", include(api_urls)),
    path("api/feedback/", FeedbackView.as_view(), name="feedback_create"),
    path("api-auth/", include("rest_framework.urls")),
    # Свой вход стоит перед стандартными маршрутами: он тот же, но считает
    # неудачные попытки и блокирует перебор.
    path("accounts/login/", account_views.ThrottledLoginView.as_view(), name="login"),
    path(
        "accounts/password-reset/",
        account_views.ThrottledPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "accounts/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "accounts/password-reset/<uidb64>/<token>/",
        account_views.ClearingPasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "accounts/password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path(
        "accounts/two-factor/",
        account_views.two_factor_verify,
        name="two_factor_verify",
    ),
    path(
        "accounts/two-factor/setup/",
        account_views.two_factor_setup,
        name="two_factor_setup",
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path("account/", account_views.account_settings, name="account_settings"),
    path("account/data.json", legal_views.download_user_data, name="account_data_export"),
    path(
        "account/delete/", legal_views.create_deletion_request,
        name="account_delete_request",
    ),
    path("account/password/", account_views.account_password, name="account_password"),
    path(
        "account/parent-invites/create/",
        account_views.parent_invite_create,
        name="parent_invite_create",
    ),
    path(
        "account/parent-invites/<int:invite_id>/revoke/",
        account_views.parent_invite_revoke,
        name="parent_invite_revoke",
    ),
    path("pricing/", billing_pages.pricing, name="pricing"),
    path("invite/", account_views.register_by_invite, name="register"),
    path("invite/<str:code>/", account_views.register_by_invite, name="register_by_invite"),
    path("legal/privacy/", legal_views.privacy, name="legal_privacy"),
    path("legal/terms/", legal_views.terms, name="legal_terms"),
    path("legal/accept/", legal_views.accept_documents, name="legal_accept"),
    path("", web_views.dashboard, name="dashboard"),
    path("map/", web_views.knowledge_map, name="knowledge_map"),
    path("map/node/<int:node_id>/", web_views.knowledge_node, name="knowledge_node"),
    path("track/", web_views.track, name="track"),
    path("schedule/", web_views.schedule, name="schedule"),
    path("leagues/", web_views.leagues, name="leagues"),
    path("arena/", web_views.arena, name="arena"),
    path("arena/match/<int:match_id>/", web_views.arena_match, name="arena_match"),
    path("lesson/<int:node_id>/", web_views.lesson, name="lesson"),
    path(
        "lesson/<int:node_id>/summary.md",
        lesson_summary,
        name="lesson-summary",
    ),
    path("diagnostics/", web_views.diagnostics, name="diagnostics"),
    path(
        "diagnostics/run/<int:result_id>/",
        web_views.diagnostic_run,
        name="diagnostic_run",
    ),
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
