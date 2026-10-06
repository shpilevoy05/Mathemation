"""Проверка ответа по смыслу, а не по строке.

Ответ задания 13 — это не число: пункт а) даёт семейства корней вида
`π/6 + 2πk`, пункт б) — конечное множество. Строковое сравнение здесь врёт в
обе стороны: `π/6+2πn` и `π/6+2πk` — один и тот же ответ, порядок серий не
важен, а `π/4+πk/2` и пара `π/4+πk`, `3π/4+πk` описывают одно множество,
записанное двумя способами.

Устройство модуля:

* разбор — единственное место, куда попадает текст ученика. Он проходит через
  белый список символов и имён: `sympify` исполняет выражение, и пускать в него
  произвольную строку из интернета нельзя;
* сравнение семейств идёт по множествам точек, а не по записи. Периоды
  приводятся к общему, каждая серия раскрывается в остатки по этому периоду —
  так две разные записи одного множества совпадают;
* проверка ошибки ученика (лишняя буква, пропущенная скобка) — это `None`, а не
  «неверно»: интерфейс должен сказать «не разобрал ответ», а не засчитать
  ошибку в освоение навыка.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import sympy as sp
from sympy.parsing.sympy_parser import (
    implicit_application,
    implicit_multiplication,
    parse_expr,
    standard_transformations,
)

# Буквы, которыми обозначают целый параметр серии. Разметка использует k, n, m;
# остальные добавлены, потому что ученик пишет то, что видел в учебнике.
PARAMETER_LETTERS = ("k", "n", "m", "l", "t", "p", "s")

# Что вообще может стоять в ответе. Всё, чего здесь нет, до `sympify` не
# доходит: разбор выражения — это исполнение кода.
ALLOWED_NAMES = {
    "pi": sp.pi,
    "sqrt": sp.sqrt,
    "arcsin": sp.asin,
    "arccos": sp.acos,
    "arctan": sp.atan,
    "arcctg": sp.acot,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "tg": sp.tan,
    "ctg": sp.cot,
    "cot": sp.cot,
    "log": sp.log,
    "ln": sp.log,
}
ALLOWED_NAMES.update({letter: sp.Symbol(letter, integer=True) for letter in PARAMETER_LETTERS})

MAX_ANSWER_LENGTH = 400
_ALLOWED_CHARS = re.compile(r"^[0-9a-z+\-*/(). ]*$")
# Умножение и применение функции без знака («2pi», «sqrt 3») разрешаем, а
# дробление многобуквенных имён — нет: с ним «pin» тихо превращается в p·i·n,
# а нам нужно, чтобы непонятная запись падала, а не считалась чем-то другим.
_TRANSFORMATIONS = standard_transformations + (implicit_multiplication, implicit_application)

# Имена, которые подставляет сам разбор (`auto_number` строит Integer/Float).
# Пустой словарь не годится: eval всё равно добавит туда builtins, а разбор без
# этих имён падает.
_GLOBALS = {
    "__builtins__": {},
    "Integer": sp.Integer,
    "Float": sp.Float,
    "Rational": sp.Rational,
    "Symbol": sp.Symbol,
}

# Замены записи: ученик пишет как на бумаге, а разбор ждёт машинную форму.
_REPLACEMENTS = (
    ("π", "*pi*"), ("Π", "*pi*"),
    ("−", "-"), ("–", "-"), ("—", "-"),
    ("·", "*"), ("×", "*"), ("∙", "*"),
    ("÷", "/"), (":", "/"),
    ("√", "sqrt"),
    ("∈", " "), ("∪", ";"),
    ("{", "("), ("}", ")"), ("[", "("), ("]", ")"),
    ("arcsn", "arcsin"),
)


class AnswerType:
    TEXT = "text"
    NUMBER = "number"
    EXPRESSION = "expression"
    ROOT_SET = "root_set"
    ROOT_FAMILIES = "root_families"


@dataclass(frozen=True)
class Family:
    """Серия корней: `base + period·k`. Период всегда положительный."""

    base: sp.Expr
    period: sp.Expr


class AnswerParseError(ValueError):
    """Ответ не разобран: не «неверно», а «непонятно»."""


def _clean(text: str) -> str:
    value = (text or "").strip().lower()
    if len(value) > MAX_ANSWER_LENGTH:
        raise AnswerParseError("Ответ слишком длинный.")
    # Степень проверяем до замен: подстановка π вносит свои звёздочки, и после
    # неё «**» уже не отличить от них. А `9**9**9` — это ещё и способ подвесить
    # разбор одним коротким ответом.
    if "**" in value or "^" in value:
        raise AnswerParseError("Степени в ответе не поддерживаются.")
    for source, target in _REPLACEMENTS:
        value = value.replace(source, target)
    # Запятая между цифрами без пробела — десятичная («7,5»); в остальных
    # случаях это разделитель серий («π/6, 5π/6»).
    value = re.sub(r"(?<=\d),(?=\d)", ".", value)
    # «x = …», «x_1 = …» — подпись переменной, к ответу она не относится.
    value = re.sub(r"^[a-z](_?\d+)?\s*=\s*", "", value)
    return _tidy_stars(value).strip()


def _tidy_stars(value: str) -> str:
    """Убрать звёздочки, появившиеся от подстановки π как множителя.

    `π` подставляется как `*pi*`, иначе «2πn» разбирается не в ту сторону:
    без явного умножения многобуквенный кусок «pin» становится одним именем.
    Рядом с оператором и скобкой такая звёздочка лишняя — убираем.
    """
    value = re.sub(r"\*\s*([+\-*/)])", r"\g<1>", value)
    value = re.sub(r"([+\-*/(;])\s*\*", r"\g<1>", value)
    return value.strip().lstrip("*")


def _to_expression(text: str) -> sp.Expr:
    """Разобрать один терм. Единственная дверь к `sympify`."""
    if not _ALLOWED_CHARS.match(text):
        raise AnswerParseError("В ответе есть символы, которых здесь быть не может.")
    try:
        expression = parse_expr(
            text,
            local_dict=dict(ALLOWED_NAMES),
            global_dict=dict(_GLOBALS),
            transformations=_TRANSFORMATIONS,
            evaluate=True,
        )
    except Exception as error:  # sympy бросает что угодно
        raise AnswerParseError("Не разобрал ответ.") from error
    if not isinstance(expression, sp.Expr):
        raise AnswerParseError("Ответ должен быть выражением.")
    unknown = {
        symbol.name for symbol in expression.free_symbols
    } - set(PARAMETER_LETTERS)
    if unknown:
        raise AnswerParseError(f"Неизвестное обозначение: {', '.join(sorted(unknown))}.")
    return expression


def _split_terms(text: str) -> list[str]:
    """Разделить ответ на серии. Разделитель — «;», перевод строки или «,»."""
    value = _clean(text)
    if not value:
        return []
    parts = re.split(r"[;\n]+", value)
    if len(parts) == 1:
        # Запятая как разделитель: десятичная точка уже нормализована выше.
        parts = re.split(r",", value)
    return [part.strip() for part in parts if part.strip()]


def _expand_plus_minus(term: str) -> list[str]:
    """`±π/4 + πk` — это две серии, записанные одной строкой."""
    if "±" not in term and "+-" not in term:
        return [term]
    normalized = term.replace("+-", "±")
    # Прибираем звёздочки ещё раз: знак ± раскрывается уже после первой уборки.
    return [
        _tidy_stars(normalized.replace("±", "+")),
        _tidy_stars(normalized.replace("±", "-")),
    ]


def parse_family(term: str) -> Family | sp.Expr:
    """Серия или отдельный корень. Параметр определяется по букве в записи."""
    expression = _to_expression(term)
    parameters = [
        symbol for symbol in expression.free_symbols if symbol.name in PARAMETER_LETTERS
    ]
    if not parameters:
        return expression
    if len(parameters) > 1:
        raise AnswerParseError("В одной серии может быть только один параметр.")
    parameter = parameters[0]
    polynomial = sp.Poly(expression, parameter)
    if polynomial.degree() != 1:
        raise AnswerParseError("Серия должна быть вида «база + период·k».")
    period = sp.simplify(polynomial.coeff_monomial(parameter))
    base = sp.simplify(polynomial.coeff_monomial(1))
    if period == 0:
        raise AnswerParseError("Период серии не может быть нулевым.")
    if period.is_negative:
        # Знак параметра не меняет множество: k пробегает все целые.
        period = -period
    return Family(base=sp.simplify(base), period=period)


def parse_answer(text: str) -> tuple[list[Family], list[sp.Expr]]:
    """Разобрать ответ целиком: серии и отдельные корни."""
    families: list[Family] = []
    roots: list[sp.Expr] = []
    for term in _split_terms(text):
        for piece in _expand_plus_minus(term):
            parsed = parse_family(piece)
            if isinstance(parsed, Family):
                families.append(parsed)
            else:
                roots.append(parsed)
    if not families and not roots:
        raise AnswerParseError("Пустой ответ.")
    return families, roots


# --- Сравнение ---

def _same_point(first: sp.Expr, second: sp.Expr) -> bool:
    difference = sp.simplify(first - second)
    return difference == 0


def _same_set(first: list[sp.Expr], second: list[sp.Expr]) -> bool:
    """Множества корней: порядок и повторы не важны."""
    remaining = list(second)
    for point in first:
        match = next((other for other in remaining if _same_point(point, other)), None)
        if match is None:
            return False
        remaining.remove(match)
    return not remaining


def _common_period(families: list[Family]) -> sp.Expr | None:
    """Общий период всех серий, если он существует.

    Периоды в тригонометрии кратны π, поэтому берём наименьшее общее кратное
    рациональных коэффициентов. Если периоды несоизмеримы, общего нет — тогда
    сравниваем серии попарно.
    """
    coefficients = []
    unit = None
    for family in families:
        ratio = family.period
        if unit is None:
            unit = ratio
        quotient = sp.nsimplify(sp.simplify(ratio / unit))
        if not quotient.is_rational:
            return None
        coefficients.append(sp.Rational(quotient))
    lcm = coefficients[0]
    for coefficient in coefficients[1:]:
        lcm = sp.lcm(sp.Rational(lcm), sp.Rational(coefficient))
    return sp.simplify(lcm * unit)


def _residues(families: list[Family], period: sp.Expr) -> list[sp.Expr] | None:
    """Раскрыть серии в точки внутри общего периода.

    Так `π/4+πk/2` и пара `π/4+πk`, `3π/4+πk` превращаются в одно множество:
    ученик вправе записать ответ любой из этих форм.
    """
    points: list[sp.Expr] = []
    for family in families:
        steps = sp.simplify(period / family.period)
        if not steps.is_Integer or steps <= 0 or steps > 64:
            return None
        for index in range(int(steps)):
            points.append(sp.simplify(family.base + index * family.period))
    return points


def same_families(first: list[Family], second: list[Family]) -> bool:
    """Описывают ли два набора серий одно и то же множество точек."""
    if not first or not second:
        return not first and not second
    period = _common_period(first + second)
    if period is not None:
        left = _residues(first, period)
        right = _residues(second, period)
        if left is not None and right is not None:
            return _same_modulo(left, right, period)
    # Несоизмеримые периоды: сравниваем серию с серией.
    return _same_family_list(first, second)


def _same_modulo(first: list[sp.Expr], second: list[sp.Expr], period: sp.Expr) -> bool:
    def normalize(point: sp.Expr) -> sp.Expr:
        shift = sp.floor(sp.simplify(point / period))
        return sp.simplify(point - shift * period)

    return _same_set([normalize(point) for point in first], [normalize(point) for point in second])


def _same_family_list(first: list[Family], second: list[Family]) -> bool:
    remaining = list(second)
    for family in first:
        match = next(
            (
                other
                for other in remaining
                if _same_point(family.period, other.period)
                and sp.simplify((family.base - other.base) / family.period).is_Integer
            ),
            None,
        )
        if match is None:
            return False
        remaining.remove(match)
    return not remaining


# --- Точка входа для задачи ---

def _spec_terms(spec: dict, key: str) -> str:
    values = spec.get(key) or []
    if isinstance(values, str):
        return values
    return "; ".join(str(value) for value in values)


def canonical_answer(spec: dict) -> tuple[list[Family], list[sp.Expr]]:
    """Эталон из разметки. Ошибка здесь — ошибка данных, а не ученика."""
    text = _spec_terms(spec, "families") or _spec_terms(spec, "roots")
    if not text:
        raise AnswerParseError("В разметке нет эталонного ответа.")
    return parse_answer(text)


def check(answer_type: str, spec: dict, correct_answer: str, given: str) -> bool | None:
    """Сравнить ответ ученика с эталоном.

    `None` означает «не разобрал»: ошибка записи не должна списываться в
    незнание темы.
    """
    if answer_type in (AnswerType.ROOT_SET, AnswerType.ROOT_FAMILIES):
        try:
            expected_families, expected_roots = canonical_answer(spec)
            given_families, given_roots = parse_answer(given)
        except AnswerParseError:
            return None
        return same_families(expected_families, given_families) and _same_set(
            expected_roots, given_roots
        )
    if answer_type in (AnswerType.NUMBER, AnswerType.EXPRESSION):
        try:
            expected = _to_expression(_clean(correct_answer))
            actual = _to_expression(_clean(given))
        except AnswerParseError:
            return None
        return _same_point(expected, actual)
    norm = lambda value: (value or "").strip().lower().replace(",", ".").replace(" ", "")
    return norm(given) == norm(correct_answer)
