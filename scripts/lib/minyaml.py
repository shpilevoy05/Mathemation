"""Парсер подмножества YAML без внешних зависимостей.

Поддерживается ровно то, что используется в этой подсистеме:

* вложенные отображения по отступам;
* списки скаляров и списки отображений (``- key: value``);
* строки в кавычках и без, int, float, bool, null;
* inline-списки ``[a, b]``;
* комментарии ``#`` вне кавычек;
* блочные скаляры ``|`` и ``>`` (без сохранения относительных отступов
  внутри блока; комментарии внутри блока удаляются);
* извлечение YAML-frontmatter из Markdown.

Не поддерживается: анкоры, multi-doc, inline-отображения ``{a: b}``.
При встрече неподдерживаемой конструкции поднимается :class:`YamlError` —
молчаливое искажение данных недопустимо.
"""

from __future__ import annotations

import re

__all__ = ["YamlError", "load", "loads", "frontmatter"]


class YamlError(ValueError):
    """Ошибка разбора YAML-подмножества."""


_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")
_KEY_RE = re.compile(r"^([^:#]+):(?:\s+(.*))?$")
_ITEM_KEY_RE = re.compile(r"^[^:\s#][^:]*:(\s|$)")


def _strip_comment(line: str) -> str:
    out: list[str] = []
    quote = None
    for index, char in enumerate(line):
        if quote:
            out.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            out.append(char)
            continue
        if char == "#" and (index == 0 or line[index - 1] in " \t"):
            break
        out.append(char)
    return "".join(out).rstrip()


def _scalar(token: str):
    token = token.strip()
    if token == "":
        return None
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    if token.startswith("[") and token.endswith("]"):
        inner = token[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part) for part in inner.split(",")]
    lowered = token.lower()
    if lowered in ("null", "~"):
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if _INT_RE.match(token):
        return int(token)
    if _FLOAT_RE.match(token):
        return float(token)
    return token


def _lines(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for raw in text.replace("\t", "    ").splitlines():
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        result.append((indent, stripped.strip()))
    return result


def _is_item(text: str) -> bool:
    return text == "-" or text.startswith("- ")


_BLOCK_RE = re.compile(r"^([|>])([+-]?)(\d*)$")


def _parse_block_scalar(lines, index, indent, header: str):
    """Собрать блочный скаляр, объявленный как ``|`` или ``>``."""
    match = _BLOCK_RE.match(header)
    if not match:
        raise YamlError("неподдерживаемый блочный скаляр: %r" % header)
    style, chomping = match.group(1), match.group(2)
    collected: list[str] = []
    while index < len(lines) and lines[index][0] > indent:
        collected.append(lines[index][1])
        index += 1
    if style == "|":
        text = "\n".join(collected)
    else:
        text = " ".join(collected)
    if chomping == "+":
        text += "\n"
    elif chomping != "-":
        text = text.rstrip() + "\n" if text else ""
    return text, index


def _parse_node(lines, index, indent):
    if _is_item(lines[index][1]):
        return _parse_list(lines, index, indent)
    return _parse_map(lines, index, indent)


def _parse_list(lines, index, indent):
    items: list = []
    while index < len(lines):
        line_indent, text = lines[index]
        if line_indent < indent or not _is_item(text):
            break
        if line_indent > indent:
            raise YamlError("неожиданный отступ в списке: %r" % text)
        rest = text[1:].strip()
        if rest == "":
            index += 1
            if index < len(lines) and lines[index][0] > indent:
                node, index = _parse_node(lines, index, lines[index][0])
                items.append(node)
            else:
                items.append(None)
        elif _ITEM_KEY_RE.match(rest):
            lines[index] = (line_indent + 2, rest)
            node, index = _parse_map(lines, index, line_indent + 2)
            items.append(node)
        else:
            items.append(_scalar(rest))
            index += 1
    return items, index


def _parse_map(lines, index, indent):
    mapping: dict = {}
    while index < len(lines):
        line_indent, text = lines[index]
        if line_indent < indent or _is_item(text):
            break
        if line_indent > indent:
            raise YamlError("неожиданный отступ в отображении: %r" % text)
        match = _KEY_RE.match(text)
        if not match:
            raise YamlError("ожидалась пара 'ключ: значение', получено %r" % text)
        key = str(_scalar(match.group(1)))
        value = (match.group(2) or "").strip()
        if value:
            if _BLOCK_RE.match(value):
                mapping[key], index = _parse_block_scalar(lines, index + 1, line_indent, value)
            else:
                mapping[key] = _scalar(value)
                index += 1
            continue
        nested = index + 1
        if nested < len(lines) and (
            lines[nested][0] > line_indent
            or (lines[nested][0] == line_indent and _is_item(lines[nested][1]))
        ):
            mapping[key], index = _parse_node(lines, nested, lines[nested][0])
        else:
            mapping[key] = None
            index = nested
    return mapping, index


def loads(text: str):
    """Разобрать YAML-текст. Возвращает dict, list или None."""
    lines = _lines(text)
    if not lines:
        return None
    node, index = _parse_node(lines, 0, lines[0][0])
    if index != len(lines):
        raise YamlError("не разобран остаток документа: %r" % (lines[index][1],))
    return node


def load(path):
    """Разобрать YAML-файл в UTF-8."""
    with open(path, "r", encoding="utf-8") as handle:
        return loads(handle.read())


def frontmatter(path):
    """Вернуть (метаданные, тело) для Markdown-файла с YAML-frontmatter.

    Если frontmatter отсутствует, метаданные равны ``None``.
    """
    with open(path, "r", encoding="utf-8") as handle:
        raw = handle.read()
    if not raw.startswith("---"):
        return None, raw
    parts = raw.split("\n")
    if parts[0].strip() != "---":
        return None, raw
    for number in range(1, len(parts)):
        if parts[number].strip() == "---":
            head = "\n".join(parts[1:number])
            body = "\n".join(parts[number + 1 :])
            return loads(head) or {}, body
    raise YamlError("frontmatter не закрыт: %s" % path)
