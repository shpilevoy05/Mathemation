"""График динамики прогноза для родительского отчёта.

Родителю нужен не «плюс пятьдесят», а картина: когда замеряли, куда шло, где
цель. Поэтому геометрия считается здесь, на сервере, — как и раскладка графа
знаний: одинаковая в браузере, в тестах и в будущем PDF, и никакой зависимости
от того, выполнился ли скрипт.

Две вещи, которые делают график честным, а не красивым:

* шкала строится по данным, а не от нуля до сотни. Иначе рост с 54 до 61
  превращается в незаметную полку — родитель видит «ничего не происходит» там,
  где ребёнок отыграл семь баллов;
* цель рисуется линией, только если она попадает в этот диапазон. Когда до неё
  далеко, честнее подписать её словами, чем сплющивать всю историю в нижнюю
  четверть картинки.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Система координат SVG. Ширина условная: картинка масштабируется по месту,
# пропорции сохраняются — точки остаются круглыми.
WIDTH = 640
HEIGHT = 220
PADDING_LEFT = 38
PADDING_RIGHT = 16
PADDING_TOP = 18
PADDING_BOTTOM = 30
MIN_SPAN = 8  # минимальный размах шкалы в баллах, чтобы линия не была «пилой»


@dataclass
class ForecastChart:
    """Готовая к отрисовке геометрия. Все значения — числа и строки."""

    width: int = WIDTH
    height: int = HEIGHT
    has_data: bool = False
    single_point: bool = False
    line: str = ""
    area: str = ""
    points: list[dict] = field(default_factory=list)
    y_ticks: list[dict] = field(default_factory=list)
    x_labels: list[dict] = field(default_factory=list)
    target_line: dict | None = None
    target_note: str = ""
    plot_left: float = PADDING_LEFT
    plot_right: float = WIDTH - PADDING_RIGHT
    plot_top: float = PADDING_TOP
    plot_bottom: float = HEIGHT - PADDING_BOTTOM
    # Подписи оси значений стоят левее поля графика.
    tick_label_x: float = PADDING_LEFT - 8

    def as_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "has_data": self.has_data,
            "single_point": self.single_point,
            "line": self.line,
            "area": self.area,
            "points": self.points,
            "y_ticks": self.y_ticks,
            "x_labels": self.x_labels,
            "target_line": self.target_line,
            "target_note": self.target_note,
            "plot_left": self.plot_left,
            "plot_right": self.plot_right,
            "plot_top": self.plot_top,
            "plot_bottom": self.plot_bottom,
            "tick_label_x": self.tick_label_x,
        }


def _nice_bounds(low: float, high: float) -> tuple[float, float]:
    """Границы шкалы: с запасом сверху и снизу и не уже минимального размаха."""
    if high - low < MIN_SPAN:
        centre = (high + low) / 2
        low, high = centre - MIN_SPAN / 2, centre + MIN_SPAN / 2
    padding = (high - low) * 0.18
    return max(0.0, low - padding), min(100.0, high + padding)


def _ticks(low: float, high: float, count: int = 4) -> list[int]:
    """Подписи оси: круглые значения внутри диапазона."""
    span = high - low
    step = max(1, round(span / max(1, count - 1)))
    for candidate in (1, 2, 5, 10, 20):
        if step <= candidate:
            step = candidate
            break
    start = int(low // step) * step
    values = []
    value = start
    while value <= high:
        if value >= low:
            values.append(int(value))
        value += step
    return values or [int(round(low)), int(round(high))]


def forecast_chart(snapshots, *, target_score: int | None = None) -> dict:
    """Геометрия графика по замерам прогноза (от старых к новым)."""
    chart = ForecastChart()
    series = [
        (snapshot.created_at, int(snapshot.predicted_score)) for snapshot in snapshots
    ]
    if not series:
        return chart.as_dict()

    chart.has_data = True
    scores = [score for _, score in series]
    low, high = _nice_bounds(min(scores), max(scores))
    span = high - low or 1

    plot_width = chart.plot_right - chart.plot_left
    plot_height = chart.plot_bottom - chart.plot_top

    def y_for(score: float) -> float:
        return round(chart.plot_bottom - (score - low) / span * plot_height, 1)

    def x_for(index: int) -> float:
        if len(series) == 1:
            return round(chart.plot_left + plot_width / 2, 1)
        return round(chart.plot_left + index * plot_width / (len(series) - 1), 1)

    chart.single_point = len(series) == 1
    for index, (moment, score) in enumerate(series):
        x, y = x_for(index), y_for(score)
        chart.points.append({
            "x": x,
            "y": y,
            # Подпись значения считается здесь, а не в шаблоне: арифметика в
            # шаблоне приводит число к целому и путает разряды.
            "label_y": round(y - 14, 1),
            "radius": 5 if index == len(series) - 1 else 3.5,
            "score": score,
            "date": moment.strftime("%d.%m"),
            "is_last": index == len(series) - 1,
        })

    chart.line = " ".join(f"{point['x']},{point['y']}" for point in chart.points)
    if not chart.single_point:
        first, last = chart.points[0], chart.points[-1]
        chart.area = (
            f"M{first['x']},{chart.plot_bottom} "
            + " ".join(f"L{point['x']},{point['y']}" for point in chart.points)
            + f" L{last['x']},{chart.plot_bottom} Z"
        )

    chart.y_ticks = [
        {
            "y": y_for(value),
            # Базовая линия текста ниже линии сетки: подпись стоит на делении.
            "label_y": round(y_for(value) + 4, 1),
            "label": str(value),
        }
        for value in _ticks(low, high)
    ]
    # Подписи дат: все точки при коротком ряде, иначе первая, середина и последняя.
    if len(chart.points) <= 5:
        marks = list(range(len(chart.points)))
    else:
        marks = [0, len(chart.points) // 2, len(chart.points) - 1]
    chart.x_labels = [
        {
            "x": chart.points[index]["x"],
            "y": round(chart.plot_bottom + 20, 1),
            "label": chart.points[index]["date"],
        }
        for index in marks
    ]

    if target_score is not None:
        if low <= target_score <= high:
            chart.target_line = {
                "y": y_for(target_score),
                "label_y": round(y_for(target_score) - 6, 1),
                "label": f"цель {target_score}",
            }
        else:
            # Цель за пределами картинки: подписываем словами, а не растягиваем
            # шкалу — иначе вся история сплющится в полоску.
            chart.target_note = f"цель {target_score} — выше графика"
    return chart.as_dict()
