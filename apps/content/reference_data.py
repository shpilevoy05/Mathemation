"""Идемпотентная загрузка справочников, общих для production и demo."""

from dataclasses import dataclass, field

from django.conf import settings
from django.utils import timezone


EXAM_YEAR = 2027
EXAM_TASKS = [
    (1, 1, 1, 2), (2, 1, 1, 2), (3, 1, 1, 2), (4, 1, 1, 2),
    (5, 1, 1, 3), (6, 1, 1, 3), (7, 1, 1, 2), (8, 1, 1, 3),
    (9, 1, 1, 3), (10, 1, 1, 3), (11, 1, 1, 4), (12, 1, 1, 4),
    (13, 2, 2, 4), (14, 2, 3, 4), (15, 2, 2, 4),
    (16, 2, 2, 4), (17, 2, 3, 5), (18, 2, 4, 5), (19, 2, 4, 5),
]

TRAJECTORIES = [
    ("score78", "78+", 78, 83, 6),
    ("score84", "84+", 84, 89, 8),
    ("score90", "90+", 90, 100, 10),
]


@dataclass
class ReferenceSeedReport:
    created: list[str] = field(default_factory=list)

    def add(self, was_created: bool, label: str) -> None:
        if was_created:
            self.created.append(label)


def seed_reference_data(*, nodes=None) -> tuple[object, ReferenceSeedReport]:
    """Создать/актуализировать только серверные справочники.

    ``nodes`` можно передать из ``seed_demo``; production-команда передаёт
    узлы, загруженные книгой разметки. Пользователей и учебную активность этот
    сервис принципиально не создаёт.
    """
    from apps.knowledge.models import KnowledgeNode
    from apps.planning.models import Trajectory

    report = ReferenceSeedReport()
    for slug, title, target_min, target_max, weekly_load in TRAJECTORIES:
        _, created = Trajectory.objects.update_or_create(
            slug=slug,
            defaults={
                "title": title,
                "target_min": target_min,
                "target_max": target_max,
                "weekly_load_hours": weekly_load,
                "config": {},
            },
        )
        report.add(created, f"траектория {slug}")

    node_list = list(nodes.values()) if isinstance(nodes, dict) else list(
        nodes if nodes is not None else KnowledgeNode.objects.all()
    )
    profile = _seed_exam_profile(node_list, report)
    _seed_shop(report)
    _seed_pricing(report)
    return profile, report


def seed_demo_promotion() -> None:
    """Демо-акция не входит в production bootstrap."""
    from datetime import timedelta

    from apps.billing.models import Promotion

    Promotion.objects.update_or_create(
        code="START10",
        defaults={
            "title": "Первый месяц −10%",
            "description": "Для тех, кто начинает подготовку.",
            "kind": Promotion.Kind.PERCENT,
            "value": 10,
            "tariff_codes": [],
            "max_uses": 0,
            "is_active": True,
            "ends_at": timezone.now() + timedelta(days=60),
        },
    )


def _seed_shop(report: ReferenceSeedReport) -> None:
    from apps.economy.models import ShopCategory, ShopItem

    cosmetics, created = ShopCategory.objects.update_or_create(
        title="Косметика", defaults={"order": 0}
    )
    report.add(created, "категория магазина «Косметика»")
    boosters, created = ShopCategory.objects.update_or_create(
        title="Ускорители", defaults={"order": 1}
    )
    report.add(created, "категория магазина «Ускорители»")

    cosmetics_items = [
        ("Аватар «Сова»", ShopItem.Slot.AVATAR, "owl", 40, ""),
        ("Аватар «Лис»", ShopItem.Slot.AVATAR, "fox", 60, ""),
        ("Аватар «Ракета»", ShopItem.Slot.AVATAR, "rocket", 90, ""),
        ("Аватар «Сигма»", ShopItem.Slot.AVATAR, "sigma", 70, ""),
        ("Рамка «Координаты»", ShopItem.Slot.FRAME, "coordinates", 80, ""),
        ("Рамка «Пламя»", ShopItem.Slot.FRAME, "flame", 110,
         "Открывается стриком от 7 дней."),
        ("Рамка «Интеграл»", ShopItem.Slot.FRAME, "integral", 140, ""),
        ("Тема «Ночь»", ShopItem.Slot.THEME, "dark", 120, "Тёмная тема кабинета."),
        ("Тема «Рассвет»", ShopItem.Slot.THEME, "sunrise", 150,
         "Тёплая охра вместо индиго."),
        ("Тема «Лес»", ShopItem.Slot.THEME, "forest", 150,
         "Зелёная палитра, спокойный фон."),
        ("Тема «Графит»", ShopItem.Slot.THEME, "graphite", 180,
         "Тёмно-серая, без синевы."),
        ("Значок «Стрик 7»", ShopItem.Slot.BADGE, "streak7", 30, ""),
    ]
    for title, slot, code, price, description in cosmetics_items:
        _, created = ShopItem.objects.update_or_create(
            title=title,
            defaults={
                "category": cosmetics,
                "slot": slot,
                "code": code,
                "description": description,
                "price_coins": price,
                "is_active": True,
                "effect": ShopItem.Effect.NONE,
            },
        )
        report.add(created, f"товар «{title}»")

    boost_items = [
        ("Заморозка стрика", ShopItem.Effect.STREAK_FREEZE, 1, 0, 100,
         "Один пропущенный день не сбрасывает серию."),
        ("Заморозка стрика ×3", ShopItem.Effect.STREAK_FREEZE, 3, 0, 260,
         "Три пропуска про запас: болезнь, поездка, форс-мажор."),
        ("Ускоритель опыта +50 % на сутки", ShopItem.Effect.XP_BOOST, 50, 24, 150,
         "XP за занятия начисляется в полтора раза быстрее."),
        ("Ускоритель опыта +100 % на 3 часа", ShopItem.Effect.XP_BOOST, 100, 3, 120,
         "Двойной опыт на один плотный подход."),
    ]
    for title, effect, value, hours, price, description in boost_items:
        _, created = ShopItem.objects.update_or_create(
            title=title,
            defaults={
                "category": boosters,
                "slot": ShopItem.Slot.BOOST,
                "description": description,
                "price_coins": price,
                "is_active": True,
                "effect": effect,
                "effect_value": value,
                "duration_hours": hours,
            },
        )
        report.add(created, f"товар «{title}»")


def _seed_pricing(report: ReferenceSeedReport) -> None:
    from apps.billing.models import AddOn, PaymentMethod, Tariff

    tariffs = [
        ("solo", "Самостоятельно", 2900, 30,
         "Полный доступ к платформе без экспертной проверки второй части.",
         {"Занятия и план": "без ограничений", "Наставник": "до 30 подсказок в месяц"}),
        ("expert", "С проверкой эксперта", 5900, 30,
         "Всё из «Самостоятельно» плюс проверка второй части живым экспертом.",
         {"Проверка второй части": "до 20 работ в месяц", "Срок проверки": "24 часа"}),
        ("intensive", "Интенсив перед экзаменом", 9900, 30,
         "Плотный режим: пробники каждую неделю и разбор с куратором.",
         {"Пробники": "еженедельно", "Разбор с куратором": "2 раза в месяц"}),
    ]
    for code, title, price, days, description, features in tariffs:
        _, created = Tariff.objects.get_or_create(
            code=code,
            version=1,
            defaults={
                "title": title,
                "description": description,
                "price_rub": price,
                "period_days": days,
                "features": features,
                "is_active": True,
            },
        )
        report.add(created, f"тариф {code}")

    methods = [
        ("card", "Банковская карта", "Оплата картой российского банка.",
         "Эквайринг подключается: пока куратор выставляет счёт вручную."),
        ("sbp", "СБП по QR-коду", "Перевод по системе быстрых платежей.",
         "Куратор пришлёт QR-код и подтвердит зачисление в течение дня."),
        ("invoice", "Счёт для организации", "Оплата от юридического лица.",
         "Напишите куратору реквизиты — счёт придёт на почту."),
    ]
    for order, (code, title, description, instructions) in enumerate(methods):
        _, created = PaymentMethod.objects.update_or_create(
            code=code,
            defaults={
                "title": title,
                "description": description,
                "instructions": instructions,
                "provider_key": "",
                "is_active": True,
                "order": order,
            },
        )
        report.add(created, f"способ оплаты {code}")

    addons = [
        ("extra-expert-check", AddOn.Kind.EXPERT_REVIEW,
         "Дополнительная проверка пробника экспертом", 1200, 1, "работа",
         "Разбор второй части живым экспертом сверх лимита тарифа, срок — 24 часа."),
        ("extra-hints", AddOn.Kind.MENTOR_HINTS, "Пакет подсказок наставника",
         490, 50, "подсказок",
         "50 наводящих подсказок сверх месячного лимита. Готовых решений наставник не выдаёт."),
    ]
    for order, (code, kind, title, price, quantity, unit, description) in enumerate(addons):
        _, created = AddOn.objects.update_or_create(
            code=code,
            defaults={
                "kind": kind,
                "title": title,
                "price_rub": price,
                "quantity": quantity,
                "unit_label": unit,
                "description": description,
                "is_active": True,
                "order": order,
            },
        )
        report.add(created, f"докупка {code}")


def _seed_exam_profile(nodes, report: ReferenceSeedReport):
    from apps.exams.models import ExamProfile, ExamTask, ExamTaskSkill

    max_primary = sum(max_score for _n, _p, max_score, _d in EXAM_TASKS)
    profile, created = ExamProfile.objects.update_or_create(
        year=EXAM_YEAR,
        defaults={
            "title": "ЕГЭ, профильная математика",
            "max_primary_score": max_primary,
            "primary_to_scaled": settings.PRIMARY_TO_SCALED[: max_primary + 1],
            "is_active": True,
        },
    )
    report.add(created, f"профиль экзамена {EXAM_YEAR}")
    ExamProfile.objects.exclude(pk=profile.pk).update(is_active=False)
    for number, part, max_score, difficulty in EXAM_TASKS:
        task, created = ExamTask.objects.update_or_create(
            profile=profile,
            number=number,
            defaults={
                "exam_part": part,
                "max_score": max_score,
                "difficulty": difficulty,
            },
        )
        report.add(created, f"задание профиля №{number}")
        for node in nodes:
            if number in (node.ege_task_numbers or []):
                _, link_created = ExamTaskSkill.objects.get_or_create(task=task, node=node)
                report.add(link_created, f"связь задания №{number} с темой {node.code}")
    return profile
