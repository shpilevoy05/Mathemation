"""Каталог косметики — разметкой в коде.

Аватары, рамки и знаки лиг нарисованы дизайном (`design/svg/`), а витрина
должна знать про каждую вещь три вещи: как она называется, сколько стоит и к
какому уровню относится. Держать это в базе руками — способ получить предмет
с кодом, которому нет картинки, или картинку, которую никто не продаёт.

Четыре уровня аватаров, и это продуктовое решение, а не украшение:

* **базовые** выдаются сразу при регистрации. Кабинет не должен встречать
  ученика пустым кружком с буквой;
* **покупные** — обычная косметика за сигмы;
* **анимированные** дороже и намеренно редкие: чем реже движение встречается
  в списке, тем дороже оно читается.
* **наградные** выдаются за призовое место в лиге и никогда не продаются.

Коды совпадают с именами файлов в `design/svg/`: по ним собирается спрайт
`static/img/cosmetics.svg`, и разъехаться им негде — за этим следит тест.
"""

from __future__ import annotations


class Tier:
    BASE = "base"
    PAID = "paid"
    ANIMATED = "animated"
    REWARD = "reward"


LEAGUES = ["delta", "gamma", "omega", "beta", "alpha", "sigma"]
LEAGUE_TITLES = {
    "delta": "Дельты",
    "gamma": "Гаммы",
    "omega": "Омеги",
    "beta": "Бетты",
    "alpha": "Альфы",
    "sigma": "Сигмы",
}


# (код, название, уровень, цена)
AVATARS: list[tuple[str, str, str, int]] = [
    ("sigma", "Сигма", Tier.BASE, 0),
    ("integral", "Интеграл", Tier.BASE, 0),
    ("pi", "Пи", Tier.BASE, 0),
    ("infinity", "Лемниската", Tier.BASE, 0),
    ("owl", "Сова", Tier.PAID, 60),
    ("fox", "Лис", Tier.PAID, 60),
    ("cat", "Кот", Tier.PAID, 70),
    ("penguin", "Пингвин", Tier.PAID, 70),
    ("hedgehog", "Ёж", Tier.PAID, 80),
    ("bear", "Медведь", Tier.PAID, 90),
    ("whale", "Кит", Tier.PAID, 90),
    ("robot", "Робот", Tier.PAID, 100),
    ("astronaut", "Космонавт", Tier.PAID, 110),
    ("ninja", "Ниндзя", Tier.PAID, 110),
    ("wizard", "Волшебник", Tier.PAID, 120),
    ("dragon", "Дракон", Tier.PAID, 140),
    ("icosa", "Икосаэдр", Tier.PAID, 130),
    ("spiral", "Спираль", Tier.PAID, 130),
    ("tesseract", "Тессеракт", Tier.ANIMATED, 320),
    ("fractal", "Фрактал", Tier.ANIMATED, 320),
    ("crystal", "Кристалл", Tier.ANIMATED, 340),
    ("origami", "Оригами", Tier.ANIMATED, 340),
    ("mobius", "Лента Мёбиуса", Tier.ANIMATED, 380),
    ("comet", "Комета", Tier.ANIMATED, 400),
    ("blackhole", "Чёрная дыра", Tier.ANIMATED, 450),
] + [
    (f"champion-{league}", f"Чемпион {LEAGUE_TITLES[league]}", Tier.REWARD, 0)
    for league in LEAGUES
]

FRAMES: list[tuple[str, str, str, int]] = [
    ("integral", "Интеграл", Tier.PAID, 120),
    ("tessellation", "Тесселяция", Tier.PAID, 130),
    ("ivy", "Плющ", Tier.PAID, 140),
    ("pcb", "Плата", Tier.PAID, 150),
    ("vitrage", "Витраж", Tier.PAID, 160),
    # Покупные рамки статичны: движение — признак уровня «анимированный».
    ("bloom", "Цветущая", Tier.PAID, 170),
    ("coordinates", "Координаты", Tier.PAID, 180),
    ("flame", "Пламя", Tier.PAID, 190),
    ("bitflow", "Битовый ток", Tier.ANIMATED, 260),
    ("nebula", "Туманность", Tier.ANIMATED, 260),
    ("aurora", "Аврора", Tier.ANIMATED, 280),
    ("gears", "Механизм", Tier.ANIMATED, 280),
    ("saturn", "Сатурн", Tier.ANIMATED, 300),
    ("comet", "Комета", Tier.ANIMATED, 320),
] + [
    (
        f"rosette-{league}-{place}",
        f"Розетка {LEAGUE_TITLES[league]} · {place} место",
        Tier.REWARD,
        0,
    )
    for league in LEAGUES
    for place in (1, 2, 3)
]

# Темы оформления рисуются css-палитрой, а не svg: они живут отдельно.
THEMES: list[tuple[str, str, str, int]] = [
    ("dark", "Ночь", Tier.PAID, 120),
    ("sunrise", "Рассвет", Tier.PAID, 150),
    ("forest", "Лес", Tier.PAID, 150),
    ("graphite", "Графит", Tier.PAID, 180),
]

# Расходники: срабатывают в момент покупки и покупаются повторно.
#
# Ускорители те же, что выдаёт лига, — 12, 24 и 48 часов: набор наград и набор
# товаров не должны различаться, иначе «ускоритель на 48 часов» звучит как две
# разные вещи. Заморозки продаются поштучно и наборами; набор дешевле не ради
# скидки, а потому что покупает его тот, кто планирует пропуски заранее.
FREEZE_UNIT_PRICE = 100
BUNDLE_DISCOUNTS = {5: 10, 10: 20}  # штук: скидка в процентах
BOOST_HOUR_PRICES = {12: 90, 24: 150, 48: 260}
BOOST_PERCENT = 50


def _bundle_price(count: int) -> int:
    """Цена набора заморозок со скидкой, округлённая до десятка."""
    discount = BUNDLE_DISCOUNTS.get(count, 0)
    full = FREEZE_UNIT_PRICE * count
    return int(round(full * (100 - discount) / 100 / 10) * 10)


# (код, название, эффект, значение, часы, цена, описание)
CONSUMABLES: list[tuple[str, str, str, int, int, int, str]] = [
    ("freeze-1", "Заморозка серии", "streak_freeze", 1, 0, FREEZE_UNIT_PRICE,
     "Один пропущенный день не сбрасывает серию."),
    ("freeze-5", "Заморозка серии ×5", "streak_freeze", 5, 0, _bundle_price(5),
     f"Пять пропусков про запас — на {BUNDLE_DISCOUNTS[5]} % дешевле поштучных."),
    ("freeze-10", "Заморозка серии ×10", "streak_freeze", 10, 0, _bundle_price(10),
     f"Десять пропусков про запас — на {BUNDLE_DISCOUNTS[10]} % дешевле поштучных."),
    ("boost-12", f"Ускоритель опыта +{BOOST_PERCENT} % на 12 ч", "xp_boost",
     BOOST_PERCENT, 12, BOOST_HOUR_PRICES[12], "Полтора опыта на один вечер."),
    ("boost-24", f"Ускоритель опыта +{BOOST_PERCENT} % на 24 ч", "xp_boost",
     BOOST_PERCENT, 24, BOOST_HOUR_PRICES[24], "Полтора опыта на сутки занятий."),
    ("boost-48", f"Ускоритель опыта +{BOOST_PERCENT} % на 48 ч", "xp_boost",
     BOOST_PERCENT, 48, BOOST_HOUR_PRICES[48], "Полтора опыта на выходные."),
]

# Значки — не товар: их выдают за достижения. В магазине им делать нечего,
# поэтому слот попадает в уборку витрины вместе с косметикой.
RETIRED_SLOTS = ["badge"]

# Знаки лиг — не товар: их выдаёт место в таблице, а не покупка. В каталоге
# они нужны, чтобы спрайт знал, что рисовать. Порядок — от младшей лиги к
# старшей, тот же, что в `apps.gamification.models.LEAGUE_ORDER`.
LEAGUE_MARKS = LEAGUES
LEAGUE_PLACES = [1, 2, 3]
PENNANT_CODES = [
    f"pennant-{league}-{place}"
    for league in LEAGUES
    for place in LEAGUE_PLACES
]

AVATAR_CODES = [code for code, *_rest in AVATARS]
FRAME_CODES = [code for code, *_rest in FRAMES]
THEME_CODES = [code for code, *_rest in THEMES]
BASE_AVATARS = [code for code, _t, tier, _p in AVATARS if tier == Tier.BASE]
ANIMATED_AVATARS = [code for code, _t, tier, _p in AVATARS if tier == Tier.ANIMATED]
ANIMATED_FRAMES = [
    code for code, _t, tier, _p in FRAMES
    if tier == Tier.ANIMATED or code.startswith("rosette-")
]

TIER_LABELS = {
    Tier.BASE: "базовый",
    Tier.PAID: "покупной",
    Tier.ANIMATED: "анимированный",
    Tier.REWARD: "награда лиги",
}

_COSMETIC_GROUPS = (
    ("avatar", "Аватары", 0, AVATARS),
    ("frame", "Рамки", 1, FRAMES),
    ("theme", "Темы оформления", 2, THEMES),
)


def is_animated(slot: str, code: str) -> bool:
    if slot == "avatar":
        return code in ANIMATED_AVATARS
    if slot == "frame":
        return code in ANIMATED_FRAMES
    return False


def _update_cosmetic(category, slot: str, item_definition: tuple[str, str, str, int]):
    from .models import ShopItem

    code, title, tier, price = item_definition
    noun = {"avatar": "Аватар", "frame": "Рамка", "theme": "Тема"}[slot]
    return ShopItem.objects.update_or_create(
        slot=slot, code=code,
        defaults={
            "category": category,
            "title": f"{noun} «{title}»",
            "tier": tier,
            "price_coins": price,
            "is_active": True,
            "effect": ShopItem.Effect.NONE,
        },
    )


def ensure_cosmetic(slot: str, code: str):
    """Создать или обновить одну косметику из каталога; неизвестную пропустить."""
    from .models import ShopCategory

    for group_slot, category_title, order, items in _COSMETIC_GROUPS:
        if group_slot != slot:
            continue
        definition = next((item for item in items if item[0] == code), None)
        if definition is None:
            return None
        category, _ = ShopCategory.objects.update_or_create(
            title=category_title, defaults={"order": order}
        )
        item, _ = _update_cosmetic(category, slot, definition)
        return item
    return None


def load_cosmetics(*, dry_run: bool = False) -> dict:
    """Разложить каталог по витрине. Идемпотентно: ключ — слот и код.

    Цены и названия обновляются, купленные предметы у учеников не трогаются:
    инвентарь ссылается на ту же запись товара.
    """
    from .models import ShopCategory, ShopItem

    report = {"created": 0, "updated": 0, "dry_run": dry_run}
    if not dry_run:
        _load_consumables(report)
    for slot, category_title, order, items in _COSMETIC_GROUPS:
        if dry_run:
            report["updated"] += len(items)
            continue
        category, _ = ShopCategory.objects.update_or_create(
            title=category_title, defaults={"order": order}
        )
        for item_definition in items:
            _, created = _update_cosmetic(category, slot, item_definition)
            report["created" if created else "updated"] += 1
    if not dry_run:
        # Предметы, которых в каталоге больше нет, снимаются с витрины, но не
        # удаляются: они лежат в инвентарях учеников, и удалить их значило бы
        # отобрать купленное.
        from django.db.models import Q

        known = Q()
        for slot, _title, _order, items in _COSMETIC_GROUPS:
            known |= Q(slot=slot, code__in=[code for code, *_rest in items])
        stale = ShopItem.objects.filter(
            slot__in=[slot for slot, *_rest in _COSMETIC_GROUPS] + RETIRED_SLOTS,
            is_active=True,
        ).exclude(known)
        report["retired"] = stale.update(is_active=False)
    return report


def _load_consumables(report: dict) -> None:
    """Ускорители и заморозки: те же вещи, что выдаёт лига, но за сигмы."""
    from .models import ShopCategory, ShopItem

    category, _ = ShopCategory.objects.update_or_create(
        title="Ускорители", defaults={"order": 3}
    )
    codes = []
    for code, title, effect, value, hours, price, description in CONSUMABLES:
        codes.append(code)
        _, created = ShopItem.objects.update_or_create(
            slot="boost", code=code,
            defaults={
                "category": category,
                "title": title,
                "description": description,
                "price_coins": price,
                "effect": effect,
                "effect_value": value,
                "duration_hours": hours,
                "tier": ShopItem.Tier.PAID,
                "is_active": True,
            },
        )
        report["created" if created else "updated"] += 1
    # Расходники из старых наборов — с витрины: два «ускорителя на сутки» с
    # разными ценами выглядят ошибкой, а не выбором.
    report["retired"] = report.get("retired", 0) + ShopItem.objects.filter(
        slot="boost", is_active=True
    ).exclude(code__in=codes).update(is_active=False)


def grant_base_avatars(student) -> int:
    """Выдать базовые аватары. Кабинет не должен встречать пустым кружком."""
    from .models import InventoryItem, ShopItem

    granted = 0
    items = ShopItem.objects.filter(slot="avatar", code__in=BASE_AVATARS)
    for item in items:
        _, created = InventoryItem.objects.get_or_create(student=student, item=item)
        granted += int(created)
    # Первый базовый аватар сразу надевается: выбор из четырёх лучше пустоты,
    # а поменять его — одно нажатие в магазине.
    if granted and not InventoryItem.objects.filter(
        student=student, is_equipped=True, item__slot="avatar"
    ).exists():
        first = items.filter(code=BASE_AVATARS[0]).first()
        if first is not None:
            InventoryItem.objects.filter(student=student, item=first).update(
                is_equipped=True
            )
    return granted
