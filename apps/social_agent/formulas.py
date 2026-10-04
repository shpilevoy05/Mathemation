from __future__ import annotations

import re


class FormulaRenderError(ValueError):
    pass


_COMMANDS = {
    r"\cdot": "·",
    r"\times": "×",
    r"\leq": "≤",
    r"\le": "≤",
    r"\geq": "≥",
    r"\ge": "≥",
    r"\neq": "≠",
    r"\ne": "≠",
    r"\pi": "π",
    r"\circ": "°",
    r"\pm": "±",
    r"\sin": "sin",
    r"\cos": "cos",
    r"\tan": "tan",
    r"\log": "log",
    r"\ln": "ln",
}
_SUPERSCRIPT = str.maketrans("0123456789+-=()in", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁱⁿ")
_SUPERSCRIPT.update(
    str.maketrans(
        "abcdefghjklmoprstuvwxyz",
        "ᵃᵇᶜᵈᵉᶠᵍʰʲᵏˡᵐᵒᵖʳˢᵗᵘᵛʷˣʸᶻ",
    )
)
_SUBSCRIPT = str.maketrans("0123456789+-=()aeoxhklmnpst", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ")
_SIMPLE_ATOM = re.compile(r"^[\wπ.]+$", re.UNICODE)


def _parenthesize_if_needed(value: str) -> str:
    return value if _SIMPLE_ATOM.fullmatch(value) else f"({value})"


def _render_formula(formula: str) -> str:
    if r"\begin" in formula or r"\end" in formula or r"\int" in formula:
        raise FormulaRenderError("Unsupported complex LaTeX")
    if formula.count("{") != formula.count("}"):
        raise FormulaRenderError("Unbalanced braces")
    if re.search(r"\\frac\s*\{[^{}]*\\frac|\\frac\s*\{[^{}]*\}\s*\{[^{}]*\\frac", formula):
        raise FormulaRenderError("Nested fractions are unsupported")
    formula = re.sub(r"\^\s*\\circ\b", "°", formula)

    def fraction(match: re.Match) -> str:
        numerator = _render_formula(match.group(1).strip())
        denominator = _render_formula(match.group(2).strip())
        if not numerator or not denominator:
            raise FormulaRenderError("Empty fraction")
        return f"{_parenthesize_if_needed(numerator)}/{_parenthesize_if_needed(denominator)}"

    previous = None
    while previous != formula:
        previous = formula
        formula = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", fraction, formula)
    if r"\frac" in formula:
        raise FormulaRenderError("Unsupported fraction")

    def square_root(match: re.Match) -> str:
        radicand = _render_formula(match.group(1).strip())
        if not radicand:
            raise FormulaRenderError("Empty square root")
        return f"√{_parenthesize_if_needed(radicand)}"

    formula = re.sub(r"\\sqrt\s*\{([^{}]+)\}", square_root, formula)
    if r"\sqrt" in formula:
        raise FormulaRenderError("Unsupported square root")

    for command in sorted(_COMMANDS, key=len, reverse=True):
        formula = formula.replace(command, _COMMANDS[command])

    def index(match: re.Match, table: dict[int, str]) -> str:
        value = match.group(1) or match.group(2)
        if any(ord(character) not in table for character in value):
            raise FormulaRenderError("Unsupported index characters")
        try:
            rendered = value.translate(table)
        except (TypeError, ValueError) as error:
            raise FormulaRenderError("Unsupported index") from error
        return rendered

    formula = re.sub(r"\^(?:\{([^{}]+)\}|([+-]?\d+|[A-Za-z]))", lambda m: index(m, _SUPERSCRIPT), formula)
    formula = re.sub(r"_(?:\{([^{}]+)\}|([+-]?\d+|[A-Za-z]))", lambda m: index(m, _SUBSCRIPT), formula)
    formula = formula.replace("~", " ")
    if "\\" in formula or "{" in formula or "}" in formula or "$" in formula:
        raise FormulaRenderError("Unsupported LaTeX command")
    return formula.strip()


def to_telegram_text(text: str) -> str:
    parts = text.split("$")
    if len(parts) % 2 == 0:
        raise FormulaRenderError("Unclosed inline formula")
    for index in range(1, len(parts), 2):
        parts[index] = _render_formula(parts[index])
    return "".join(parts)
