"""Front matter of a corpus file (Markdown corpus spec v1), read without a YAML library.

A block of 'key: value' lines between two '---' lines at the very top of the file:

    ---
    spec: 1
    ocr: true
    ---
    # Title of the paper
"""
from __future__ import annotations

import re

MAX_LINES = 100     # a block that does not close within this many lines is not front matter
_PAIR = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)[ \t]*:(?:[ \t]+(.*))?$")
_TRUE = frozenset(("true", "yes", "on", "1"))
_BOM = chr(0xFEFF)   # byte-order mark; written this way so that this file holds no invisible character


def _value(raw: str | None) -> str:
    value = (raw or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value.split(" #", 1)[0].strip()


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """(values, body). A text without front matter comes back as ({}, text).

    The block must start at the first character (a byte-order mark may precede it) and its first
    line must be a 'key: value' pair in the first column; a '---' anywhere else is an ordinary
    Markdown rule. Keys are lower-cased. Indented lines, list items and comments are skipped.
    """
    start = 1 if text.startswith(_BOM) else 0
    lines = text[start:].split("\n", MAX_LINES + 2)
    if len(lines) < 3 or lines[0].rstrip() != "---" or not _PAIR.match(lines[1].rstrip()):
        return {}, text
    values: dict[str, str] = {}
    pos = start + len(lines[0]) + 1
    for line in lines[1:MAX_LINES + 2]:
        pos += len(line) + 1
        stripped = line.rstrip()
        if stripped == "---":
            return values, text[pos:]
        pair = _PAIR.match(stripped)
        if pair:
            values.setdefault(pair.group(1).lower(), _value(pair.group(2)))
    return {}, text


def is_true(value: str | None) -> bool:
    """True for the YAML-style words true / yes / on / 1, in any letter case."""
    return (value or "").strip().lower() in _TRUE
