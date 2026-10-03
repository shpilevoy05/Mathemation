"""Навигация рельса: два уровня вместо плоского списка из одиннадцати ссылок.

Плоский список требовал читать все пункты, чтобы найти один. Группы дают
ориентир: сначала выбираешь «зачем я сюда пришёл» (учиться, проверить себя,
посмотреть прогресс), потом конкретную страницу.

Структура собирается здесь, а не в шаблоне: активный пункт и раскрытая группа
считаются по имени маршрута, и это нужно проверять тестами, а не глазами.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.urls import reverse

from .permissions import is_expert, is_methodist


@dataclass
class NavItem:
    label: str
    url: str
    icon: str
    routes: tuple[str, ...]
    short_label: str = ""

    def is_active(self, route: str) -> bool:
        return route in self.routes


@dataclass
class NavGroup:
    """Раздел рельса. Группа из одного пункта показывается ссылкой без раскрытия."""

    title: str
    icon: str
    items: list[NavItem] = field(default_factory=list)

    def is_open(self, route: str) -> bool:
        return any(item.is_active(route) for item in self.items)

    @property
    def is_single(self) -> bool:
        return len(self.items) == 1


def _student_groups() -> list[NavGroup]:
    return [
        NavGroup("Учёба", "i-cap", [
            NavItem("Кабинет", reverse("dashboard"), "i-home", ("dashboard",)),
            NavItem("Дорожка", reverse("track"), "i-track", ("track", "lesson")),
            NavItem(
                "Расписание", reverse("schedule"), "i-clock", ("schedule",),
            ),
            NavItem(
                "Карта навыков", reverse("knowledge_map"), "i-map",
                ("knowledge_map", "knowledge_node"), short_label="Карта",
            ),
            NavItem("Домашки", reverse("homework"), "i-doc", ("homework",)),
            NavItem("Отработка", reverse("practice_backlog"), "i-repeat", ("practice_backlog",)),
        ]),
        NavGroup("Проверить себя", "i-target", [
            NavItem(
                "Диагностика", reverse("diagnostics"), "i-checklist",
                ("diagnostics", "diagnostic_run"),
            ),
            NavItem(
                "Пробники", reverse("mocks"), "i-cup",
                ("mocks", "mock_run", "mock_result"),
            ),
            NavItem(
                "Задание дня", reverse("daily_challenge"), "i-star",
                ("daily_challenge",), short_label="Задание",
            ),
        ]),
        NavGroup("Результат", "i-chart", [
            NavItem("Прогноз", reverse("forecast"), "i-chart", ("forecast",)),
        ]),
        NavGroup("Игры", "i-gamepad", [
            NavItem("Арена", reverse("arena"), "i-cup", ("arena", "arena_match")),
            NavItem("Лига", reverse("leagues"), "i-medal", ("leagues",)),
        ]),
        # Магазин и тарифы — разные разговоры: один про сигмы, другой про
        # деньги родителя. В одной группе они путались, поэтому остаются
        # отдельными вкладками.
        NavGroup("Магазин", "i-sigma", [
            NavItem("Магазин", reverse("shop"), "i-sigma", ("shop",)),
        ]),
        NavGroup("Тарифы", "i-ruble", [
            NavItem("Тарифы", reverse("pricing"), "i-ruble", ("pricing",)),
        ]),
        _account_group(),
    ]


def _parent_groups() -> list[NavGroup]:
    return [
        NavGroup("Ребёнок", "i-doc", [
            NavItem("Отчёт", reverse("parent_dashboard"), "i-doc", ("parent_dashboard",)),
        ]),
        NavGroup("Оплата", "i-ruble", [
            NavItem("Тарифы и оплата", reverse("pricing"), "i-ruble", ("pricing",)),
        ]),
        _account_group(),
    ]


def _staff_groups(user) -> list[NavGroup]:
    groups: list[NavGroup] = []
    if is_expert(user):
        groups.append(NavGroup("Проверка", "i-doc", [
            NavItem(
                "Очередь работ", reverse("expert_queue"), "i-doc",
                ("expert_queue", "expert_review"),
            ),
        ]))
    if is_methodist(user):
        groups.append(NavGroup("Контент", "i-book", [
            NavItem("Обзор", reverse("methodist_dashboard"), "i-grid", ("methodist_dashboard",)),
            NavItem(
                "Уроки", reverse("studio_lessons"), "i-play",
                ("studio_lessons", "studio_lesson_new", "studio_lesson_edit"),
            ),
            NavItem(
                "Задачи", reverse("studio_tasks"), "i-pencil",
                ("studio_tasks", "studio_task_new", "studio_task_edit", "studio_task_picker"),
            ),
            NavItem(
                "Граф знаний", reverse("studio_graph"), "i-graph",
                ("studio_graph", "studio_node_new", "studio_node_edit"),
            ),
            NavItem(
                "Задания дня", reverse("studio_daily"), "i-star",
                ("studio_daily", "studio_daily_edit"),
            ),
            NavItem(
                "Диагностики и пробники", reverse("studio_tests"), "i-checklist",
                ("studio_tests", "studio_diagnostic_new", "studio_diagnostic_edit",
                 "studio_mock_new", "studio_mock_edit"),
            ),
            NavItem(
                "Цены и акции", reverse("studio_pricing"), "i-tag",
                ("studio_pricing", "studio_tariff_edit", "studio_tariff_price",
                 "studio_addon_edit", "studio_promotion_new", "studio_promotion_edit"),
            ),
            NavItem("Панель", reverse("admin-panel"), "i-sliders", ("admin-panel",)),
            NavItem("Django-админка", reverse("admin:index"), "i-database", ()),
        ]))
        groups.append(NavGroup("Деньги", "i-ruble", [
            NavItem("Тарифы", reverse("pricing"), "i-ruble", ("pricing",)),
        ]))
    if groups:
        groups.append(_account_group())
    return groups


def _account_group() -> NavGroup:
    return NavGroup("Аккаунт", "i-gear", [
        NavItem(
            "Настройки", reverse("account_settings"), "i-gear",
            ("account_settings", "account_password"),
        ),
    ])


def nav_groups(user) -> list[NavGroup]:
    """Разделы рельса для роли. Сотрудник видит своё, ученик — своё."""
    if not getattr(user, "is_authenticated", False):
        return []
    staff = _staff_groups(user)
    if staff:
        return staff
    if getattr(user, "student_profile", None):
        return _student_groups()
    if getattr(user, "parent_profile", None):
        return _parent_groups()
    return [_account_group()]
