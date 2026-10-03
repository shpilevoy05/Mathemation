"""Идемпотентная загрузка справочников, общих для production и demo."""

from dataclasses import dataclass, field

from django.utils import timezone

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
    """Load the canonical cosmetics catalog instead of a demo-only subset."""
    from apps.economy.catalog import load_cosmetics

    catalog_report = load_cosmetics()
    report.created.extend(
        ["товар каталога косметики"] * catalog_report.get("created", 0)
    )


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
    from apps.exams.blueprint import load_blueprint
    from apps.exams.models import ExamProfile

    blueprint_report = load_blueprint()
    report.add(blueprint_report["created"], f"профиль экзамена {blueprint_report['year']}")
    return ExamProfile.active()
