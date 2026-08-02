"""Страница панели администратора внутри кабинета."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render

SECTIONS = [
    {"group": "Обучение", "items": [
        {"key": "lessons", "title": "Уроки",
         "columns": ["id", "title", "node", "status", "order",
                     "video_provider", "video_url"]},
        {"key": "theory-blocks", "title": "Теория",
         "columns": ["id", "lesson", "title", "order"]},
        {"key": "assignments", "title": "Задачи",
         "columns": ["id", "title", "exam_part", "difficulty", "max_score"]},
        {"key": "assignment-versions", "title": "Версии задач",
         "columns": ["id", "assignment", "number", "change_note", "created_at"]},
        {"key": "homeworks", "title": "Домашки",
         "columns": ["id", "title", "lesson", "status", "due_at"]},
        {"key": "homework-tasks", "title": "Задачи в домашке",
         "columns": ["id", "homework", "assignment", "order"]},
        {"key": "daily-challenges", "title": "Задания дня",
         "columns": ["id", "date", "assignment", "reward_xp", "is_active"]},
    ]},
    {"group": "Ученики", "items": [
        {"key": "students", "title": "Ученики",
         "columns": ["id", "username", "is_active", "target_score", "weekly_hours",
                     "primary_calibration", "calibration_samples", "balance"]},
        {"key": "groups", "title": "Группы",
         "columns": ["id", "title", "curator", "is_active"]},
        {"key": "invites", "title": "Приглашения",
         "columns": ["id", "code", "role", "group", "expires_at", "used_by"]},
        {"key": "forecast-observations", "title": "Прогноз против факта",
         "columns": ["id", "student", "predicted_primary", "actual_primary", "error",
                     "created_at"]},
    ]},
    {"group": "Граф и экзамен", "items": [
        {"key": "clusters", "title": "Темы",
         "columns": ["id", "title", "exam_weight", "color"]},
        {"key": "nodes", "title": "Узлы графа",
         "columns": ["id", "code", "title", "cluster", "exam_part", "hours_estimate"]},
        {"key": "dependencies", "title": "Зависимости",
         "columns": ["id", "node", "prerequisite", "min_mastery"]},
        {"key": "exam-profiles", "title": "Профили экзамена",
         "columns": ["id", "year", "title", "max_primary_score", "is_active"]},
        {"key": "exam-tasks", "title": "Задания экзамена",
         "columns": ["id", "profile", "number", "exam_part", "max_score", "difficulty"]},
    ]},
    {"group": "Планы", "items": [
        {"key": "plans", "title": "Планы", "columns": ["id", "student", "target_score", "status"]},
        {"key": "plan-items", "title": "Пункты планов",
         "columns": ["id", "plan", "node", "item_type", "week_index", "due_date", "status"]},
        {"key": "plan-changes", "title": "Изменения планов",
         "columns": ["id", "plan", "reason", "node", "is_major", "created_at"]},
    ]},
    {"group": "Магазин", "items": [
        {"key": "shop-categories", "title": "Категории", "columns": ["id", "title", "order"]},
        {"key": "shop-items", "title": "Товары",
         "columns": ["id", "title", "slot", "price_coins", "is_active"]},
        {"key": "wallets", "title": "Кошельки", "columns": ["id", "student", "balance"]},
        {"key": "ledger", "title": "Реестр начислений",
         "columns": ["id", "student", "amount", "reason", "balance_after", "created_at"]},
        {"key": "inventory", "title": "Инвентарь",
         "columns": ["id", "student", "item", "is_equipped"]},
    ]},
    {"group": "Деньги", "items": [
        {"key": "tariffs", "title": "Тарифы",
         "columns": ["id", "code", "version", "title", "price_rub", "period_days", "is_active"]},
        {"key": "addons", "title": "Докупки (апселлы)",
         "columns": ["id", "code", "kind", "title", "description", "price_rub",
                     "quantity", "unit_label", "is_active", "order"]},
        {"key": "payment-methods", "title": "Способы оплаты",
         "columns": ["id", "code", "title", "description", "instructions",
                     "provider_key", "is_active", "order"]},
        {"key": "promotions", "title": "Скидки и акции",
         "columns": ["id", "title", "code", "kind", "value", "tariff_codes",
                     "starts_at", "ends_at", "max_uses", "used_count", "is_active"]},
        {"key": "subscriptions", "title": "Подписки",
         "columns": ["id", "student", "tariff", "status", "ends_at"]},
        {"key": "payments", "title": "Платежи",
         "columns": ["id", "student", "payer", "amount_rub", "status", "created_at"]},
    ]},
]

# Действия сверх CRUD: то, что нельзя делать правкой поля.
ROW_ACTIONS = {
    "lessons": [{"name": "publish", "title": "Опубликовать"},
                {"name": "unpublish", "title": "В черновик"}],
    "assignments": [{"name": "new-version", "title": "Новая версия",
                     "prompt": "statement", "hint": "Новое условие задачи"}],
    "homeworks": [{"name": "assign", "title": "Выдать", "prompt": "group",
                   "hint": "ID группы"}],
    "students": [{"name": "deactivate", "title": "Отключить"},
                 {"name": "reactivate", "title": "Включить"},
                 {"name": "grant-coins", "title": "Начислить баллы",
                  "prompt": "amount", "hint": "Сколько баллов"}],
    "tariffs": [{"name": "new-version", "title": "Новая цена",
                 "prompt": "price_rub", "hint": "Новая цена в рублях"}],
    "payments": [{"name": "refund", "title": "Вернуть деньги", "confirm": True}],
}


@login_required
def panel_view(request):
    from apps.web.permissions import is_methodist

    if not is_methodist(request.user):
        return HttpResponseForbidden("Нужны права методиста платформы.")
    return render(
        request,
        "adminpanel/panel.html",
        {"sections": SECTIONS, "row_actions": ROW_ACTIONS},
    )
