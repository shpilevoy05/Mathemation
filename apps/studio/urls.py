from django.urls import path

from . import views


urlpatterns = [
    path("risks/", views.risk_list, name="studio_risks"),
    path("lessons/", views.lesson_list, name="studio_lessons"),
    path("lessons/new/", views.lesson_edit, name="studio_lesson_new"),
    path("lessons/<int:lesson_id>/", views.lesson_edit, name="studio_lesson_edit"),
    path("tasks/", views.task_list, name="studio_tasks"),
    path("tasks/new/", views.task_edit, name="studio_task_new"),
    path("tasks/<int:assignment_id>/", views.task_edit, name="studio_task_edit"),
    path("tasks/pick/", views.task_picker, name="studio_task_picker"),
    path("graph/", views.graph_overview, name="studio_graph"),
    path("graph/new/", views.node_edit, name="studio_node_new"),
    path("graph/<int:node_id>/", views.node_edit, name="studio_node_edit"),
    path(
        "graph/<int:node_id>/dependencies/<int:dependency_id>/delete/",
        views.dependency_delete,
        name="studio_dependency_delete",
    ),
    path("daily/", views.daily_calendar, name="studio_daily"),
    path("daily/<str:day>/", views.daily_edit, name="studio_daily_edit"),
    path("pricing/", views.pricing_overview, name="studio_pricing"),
    path("pricing/tariffs/<int:tariff_id>/", views.tariff_edit, name="studio_tariff_edit"),
    path("pricing/tariffs/<int:tariff_id>/price/", views.tariff_price, name="studio_tariff_price"),
    path("pricing/addons/<int:addon_id>/", views.addon_edit, name="studio_addon_edit"),
    path("pricing/promotions/new/", views.promotion_edit, name="studio_promotion_new"),
    path("pricing/promotions/<int:promotion_id>/", views.promotion_edit, name="studio_promotion_edit"),
    path("tests/", views.test_list, name="studio_tests"),
    path("tests/diagnostics/new/", views.diagnostic_edit, name="studio_diagnostic_new"),
    path("tests/diagnostics/<int:test_id>/", views.diagnostic_edit, name="studio_diagnostic_edit"),
    path("tests/mocks/new/", views.mock_edit, name="studio_mock_new"),
    path("tests/mocks/<int:exam_id>/", views.mock_edit, name="studio_mock_edit"),
]
