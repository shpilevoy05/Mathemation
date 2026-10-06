"""Косметика ученика для каждого шаблона.

Тема, аватар и рамка меняют весь кабинет, поэтому они нужны в `base.html`, а не
в контексте отдельной страницы.
"""

from apps.billing.access import is_enforced, subscription_state
from apps.economy.services import cosmetic_codes


def cosmetics(request):
    student = getattr(getattr(request, "user", None), "student_profile", None)
    if student is None:
        return {"ui_theme": "", "ui_avatar": "", "ui_frame": ""}

    codes = cosmetic_codes(student)
    return {
        "ui_theme": codes["theme"],
        "ui_avatar": codes["avatar"],
        "ui_frame": codes["frame"],
    }


def access(request):
    """Состояние подписки в шапке кабинета.

    Пока гейт выключен, блока нет вовсе: показывать «доступ открыт» там, где он
    открыт всем и всегда, — шум.
    """
    student = getattr(getattr(request, "user", None), "student_profile", None)
    if student is None or not is_enforced():
        return {"access_state": None}
    return {"access_state": subscription_state(student)}


def navigation(request):
    """Разделы рельса и активный маршрут.

    Считается здесь, а не в шаблоне: активность пункта и раскрытие группы —
    это правила, а не разметка, и их проверяют тестами.
    """
    from .navigation import nav_groups

    match = getattr(request, "resolver_match", None)
    route = match.url_name if match else ""
    groups = nav_groups(getattr(request, "user", None))
    return {
        "nav_groups": [
            {
                "title": group.title,
                "icon": group.icon,
                "is_open": group.is_open(route),
                "is_single": group.is_single,
                "items": [
                    {
                        "label": item.label,
                        "short_label": item.short_label or item.label,
                        "url": item.url,
                        "icon": item.icon,
                        "is_active": item.is_active(route),
                    }
                    for item in group.items
                ],
            }
            for group in groups
        ],
    }
