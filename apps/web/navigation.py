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
        NavGroup("Учёба", "i-track", [
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
                "Диагностика", reverse("diagnostics"), "i-target",
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
        NavGroup("Игры", "i-cup", [
            NavItem("Арена", reverse("arena"), "i-cup", ("arena", "arena_match")),
        ]),
        NavGroup("Награды", "i-sigma", [
            NavItem("Магазин", reverse("shop"), "i-sigma", ("shop",)),
            NavItem("Тарифы", reverse("pricing"), "i-ruble", ("pricing",)),
        ]),
    ]


def _parent_groups() -> list[NavGroup]:
    return [
        NavGroup("Ребёнок", "i-doc", [
            NavItem("Отчёт", reverse("parent_dashboard"), "i-doc", ("parent_dashboard",)),
        ]),
        NavGroup("Оплата", "i-ruble", [
            NavItem("Тарифы и оплата", reverse("pricing"), "i-ruble", ("pricing",)),
        ]),
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
            NavItem("Обзор", reverse("methodist_dashboard"), "i-book", ("methodist_dashboard",)),
            NavItem("Панель", reverse("admin-panel"), "i-map", ("admin-panel",)),
            NavItem("Django-админка", reverse("admin:index"), "i-target", ()),
        ]))
        groups.append(NavGroup("Деньги", "i-ruble", [
            NavItem("Тарифы", reverse("pricing"), "i-ruble", ("pricing",)),
        ]))
    return groups


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
    return []
