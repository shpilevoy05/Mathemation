"""Символьные гардрейлы для ответов ИИ-наставника."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sympy import (
    E,
    Float,
    Integer,
    Rational,
    Symbol,
    cos,
    log,
    pi,
    simplify,
    sin,
    sqrt,
    tan,
)
from sympy.assumptions import Q, ask
from sympy.core.expr import Expr
from sympy.parsing.sympy_parser import (
    auto_number,
    convert_xor,
    function_exponentiation,
    implicit_application,
    implicit_multiplication,
    lambda_notation,
    parse_expr,
    repeated_decimals,
)


@dataclass(frozen=True, slots=True)
class GuardrailResult:
    """Результат проверки всех математических утверждений в подсказке."""

    passed: bool
    failed_claims: list[str]
    unverified_claims: list[str]


_COMPARISON_RE = re.compile(r"\\(?:neq|ne|leq|le|geq|ge)|!=|==|≠|≤|≥|=|<|>")
_MATH_RUN_LEFT_RE = re.compile(
    r"[A-Za-z0-9πΠ\\{}()[\].,+\-−–—*/÷·×^²³√\s]+$"
)
_MATH_RUN_RIGHT_RE = re.compile(
    r"^[A-Za-z0-9πΠ\\{}()[\].,+\-−–—*/÷·×^²³√\s]+"
)
_TRANSFORMATIONS = (
    lambda_notation,
    repeated_decimals,
    auto_number,
    convert_xor,
    implicit_multiplication,
    implicit_application,
    function_exponentiation,
)
_SAFE_GLOBALS: dict[str, object] = {
    "Integer": Integer,
    "Float": Float,
    "Rational": Rational,
    "__builtins__": {},
}
_SAFE_LOCALS: dict[str, object] = {
    "sin": sin,
    "cos": cos,
    "tan": tan,
    "log": log,
    "ln": log,
    "sqrt": sqrt,
    "pi": pi,
    "e": E,
    "E": E,
}
_ALLOWED_FUNCTIONS = frozenset(_SAFE_LOCALS) | {
    "log2",
    "log10",
}
_IDENTIFIER_RE = re.compile(r"[A-Za-z]+\d*")
_NUMERIC_TOKEN_RE = re.compile(
    r"(?<![\w])[-+]?(?:sqrt\s*\([^()]+\)|√\s*(?:\([^()]+\)|\d+(?:[.,]\d+)?)|"
    r"\d+(?:[.,]\d+)?(?:\s*\^\s*[-+]?\d+)?(?:\s*/\s*[-+]?\d+(?:[.,]\d+)?)?)(?![\w])",
    re.IGNORECASE,
)


def extract_math_claims(text: str) -> list[str]:
    """Извлекает равенства и неравенства из обычной и LaTeX-подобной записи.

    Простое присваивание нового одиночного символа слева считается
    определением и не включается в результат.
    """

    claims: list[str] = []
    for line_match in re.finditer(r"[^\r\n]+", text):
        line = line_match.group(0)
        for comparison in _COMPARISON_RE.finditer(line):
            left_match = _MATH_RUN_LEFT_RE.search(line[: comparison.start()])
            right_match = _MATH_RUN_RIGHT_RE.match(line[comparison.end() :])
            if left_match is None or right_match is None:
                continue
            left = _clean_claim_side(left_match.group(0), left=True)
            right = _clean_claim_side(right_match.group(0), left=False)
            if not left or not right:
                continue
            absolute_left_start = line_match.start() + left_match.start()
            operator = comparison.group(0)
            if operator in {"=", "=="} and _is_new_symbol_definition(
                text, left, absolute_left_start
            ):
                continue
            claims.append(f"{left} {operator} {right}")
    return claims


def verify_claim(claim: str) -> bool | None:
    """Проверяет одно равенство или неравенство средствами SymPy.

    Возвращает ``None``, когда выражение нельзя безопасно разобрать либо
    истинность зависит от неизвестных ограничений на переменные.
    """

    comparison = _COMPARISON_RE.search(claim)
    if comparison is None:
        return None
    lhs = _try_parse_math_expression(claim[: comparison.start()])
    rhs = _try_parse_math_expression(claim[comparison.end() :])
    if lhs is None or rhs is None:
        return None

    try:
        operator = comparison.group(0)
        difference = simplify(lhs - rhs)
        if operator in {"=", "=="}:
            result = difference.equals(0)
            return bool(result) if result is not None else None
        if operator in {"!=", "≠", r"\ne", r"\neq"}:
            result = difference.equals(0)
            return not bool(result) if result is not None else None

        predicate = {
            "<": Q.negative,
            ">": Q.positive,
            "≤": Q.nonpositive,
            r"\le": Q.nonpositive,
            r"\leq": Q.nonpositive,
            "≥": Q.nonnegative,
            r"\ge": Q.nonnegative,
            r"\geq": Q.nonnegative,
        }.get(operator)
        if predicate is None:
            return None
        result = ask(predicate(difference))
        return bool(result) if result is not None else None
    except Exception:
        # SymPy может выбрасывать разные исключения и после успешного разбора.
        # Содержимое подсказки не должно нарушать доступность API.
        return None


def check_hint(text: str) -> GuardrailResult:
    """Проверяет подсказку; неверные утверждения блокируют её показ."""

    failed: list[str] = []
    unverified: list[str] = []
    for claim in extract_math_claims(text):
        try:
            verdict = verify_claim(claim)
        except Exception:
            # Последний защитный контур для непредвиденного поведения SymPy.
            verdict = None
        if verdict is False:
            failed.append(claim)
        elif verdict is None:
            unverified.append(claim)
    return GuardrailResult(
        passed=not failed,
        failed_claims=failed,
        unverified_claims=unverified,
    )


def contains_final_answer(text: str, answer: str, statement: str) -> bool:
    """Ищет числовой финальный ответ, не считая числа из условия задачи."""

    expected = _try_parse_math_expression(answer)
    if expected is None:
        return False
    if expected.free_symbols:
        return False

    statement_values = _numeric_values(statement, include_coefficients=True)
    try:
        for value in _numeric_values(text):
            if simplify(value - expected) != 0:
                continue
            if any(simplify(value - stated) == 0 for stated in statement_values):
                continue
            return True
    except Exception:
        # Ошибка SymPy в выходном фильтре означает безопасную деградацию,
        # но не падение запроса наставника.
        return False
    return False


def _clean_claim_side(value: str, *, left: bool) -> str:
    value = value.strip(" \t:;,.!?—–")
    if left:
        # После русского текста регулярное выражение уже оставляет только
        # математический суффикс; двоеточие дополнительно отделяет пояснение.
        value = value.rsplit(":", 1)[-1].strip()
    else:
        value = re.split(r"(?<!\d)[.!?;](?!\d)", value, maxsplit=1)[0].strip()
    return value


def _is_new_symbol_definition(text: str, lhs: str, lhs_start: int) -> bool:
    normalized = lhs.strip().strip("${}() ")
    if re.fullmatch(r"[A-Za-z]", normalized) is None:
        return False
    prefix = text[:lhs_start]
    nearby = prefix[-24:].lower()
    if "пусть" in nearby or "обознач" in nearby or "let" in nearby:
        return True
    return re.search(rf"\b{re.escape(normalized)}\b", prefix) is None


def _normalize_expression(value: str) -> str:
    value = value.strip().strip("$")
    value = value.replace(r"\left", "").replace(r"\right", "")
    value = value.replace(r"\cdot", "*").replace(r"\times", "*").replace("×", "*")
    value = value.replace("·", "*").replace("÷", "/")
    value = value.replace("−", "-").replace("–", "-").replace("—", "-")
    value = value.replace("π", "pi").replace("Π", "pi")
    value = value.replace(r"\pi", "pi")
    value = re.sub(r"\\(sin|cos|tan|log|ln|sqrt)", r"\1", value)
    value = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1)/(\2)", value)
    value = re.sub(r"sqrt\s*\{([^{}]+)\}", r"sqrt(\1)", value)
    value = value.replace("{", "(").replace("}", ")")
    value = re.sub(r"√\s*(\([^()]+\)|[A-Za-z0-9.]+)", r"sqrt(\1)", value)
    value = value.replace("²", "**2").replace("³", "**3").replace("^", "**")
    value = re.sub(r"(?<=\d),(?=\d)", ".", value)
    return value


def _parse_math_expression(value: str) -> Expr:
    normalized = _normalize_expression(value)
    identifiers = set(_IDENTIFIER_RE.findall(normalized))
    locals_dict = dict(_SAFE_LOCALS)
    locals_dict["log2"] = _log2
    locals_dict["log10"] = _log10
    for identifier in identifiers:
        if identifier in _ALLOWED_FUNCTIONS:
            continue
        if len(identifier) != 1:
            raise ValueError("Недопустимый идентификатор в выражении")
        locals_dict[identifier] = Symbol(identifier, real=True)
    if re.search(r"[^A-Za-z0-9.()+\-*/\s]", normalized):
        raise ValueError("Недопустимый символ в выражении")
    parsed = parse_expr(
        normalized,
        local_dict=locals_dict,
        global_dict=_SAFE_GLOBALS,
        transformations=_TRANSFORMATIONS,
        evaluate=True,
    )
    if not isinstance(parsed, Expr):
        raise ValueError("Ожидалось математическое выражение")
    return parsed


def _try_parse_math_expression(value: str) -> Expr | None:
    """Безопасно разбирает внешнее выражение, не выпуская исключения SymPy."""

    try:
        return _parse_math_expression(value)
    except Exception:
        return None


def _log2(argument: Expr) -> Expr:
    """Возвращает логарифм по основанию 2 для безопасного locals-словаря."""

    return log(argument, 2)


def _log10(argument: Expr) -> Expr:
    """Возвращает логарифм по основанию 10 для безопасного locals-словаря."""

    return log(argument, 10)


def _numeric_values(text: str, *, include_coefficients: bool = False) -> list[Expr]:
    values: list[Expr] = []
    scan_text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    tokens = _NUMERIC_TOKEN_RE.findall(scan_text)
    if include_coefficients:
        tokens.extend(
            re.findall(r"(?<![\w])[-+]?\d+(?:[.,]\d+)?(?=[A-Za-z])", scan_text)
        )
    for token in tokens:
        value = _try_parse_math_expression(token)
        if value is None:
            continue
        if not value.free_symbols:
            values.append(value)
    return values
