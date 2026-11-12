"""Structured tables of the Markdown corpus: find them, turn them into pipe rows, cut them at row ends."""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

MARKER = re.compile(r"^##[ \t]+Tables \(structured\)[ \t]*\r?$", re.MULTILINE)
LABEL = re.compile(r"^###[ \t]+Table[ \t]+(\d+)[ \t]*\r?$", re.MULTILINE)
_HTML_TABLE = re.compile(r"<table\b.*?(?:</table\s*>|\Z)", re.IGNORECASE | re.DOTALL)
_PIPE_BLOCK = re.compile(r"(?:^[ \t]*\|[^\n]*(?:\n|\Z))+", re.MULTILINE)
_PIPE_SPLIT = re.compile(r"(?<!\\)\|")
_RULE_CELL = re.compile(r":?-+:?")
MAX_COLSPAN = 50


@dataclass(frozen=True)
class Table:
    """One structured table; start and end are positions in the prepared text."""

    number: int
    caption: str
    rows: int
    cols: int
    start: int
    end: int


@dataclass(frozen=True)
class Segment:
    """A piece of the tables part of the prepared text: one table passage, or leftover text."""

    kind: str            # "table" | "text"
    number: int
    start: int
    end: int


@dataclass(frozen=True)
class Prepared:
    """Text as it is indexed: the paper's body, then every structured table as pipe rows."""

    text: str
    body_end: int
    segments: tuple[Segment, ...]
    tables: tuple[Table, ...]


class _Rows(HTMLParser):
    """Collect the rows of the first <table>: a list of (is_header_cell, text) lists."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[bool, str]]] = []
        self._row: list[tuple[bool, str]] | None = None
        self._cell: list[str] | None = None
        self._head = False
        self._span = 1

    def _end_cell(self) -> None:
        if self._cell is not None and self._row is not None:
            self._row.append((self._head, "".join(self._cell)))
            self._row.extend((self._head, "") for _ in range(self._span - 1))
        self._cell = None

    def _end_row(self) -> None:
        self._end_cell()
        if self._row is not None:
            self.rows.append(self._row)
        self._row = None

    def handle_starttag(self, tag, attrs) -> None:
        if tag == "tr":
            self._end_row()
            self._row = []
        elif tag in ("td", "th"):
            self._end_cell()
            if self._row is None:
                self._row = []
            self._cell = []
            self._head = tag == "th"
            span = dict(attrs).get("colspan") or "1"
            self._span = min(int(span), MAX_COLSPAN) if span.isdigit() and int(span) > 0 else 1
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag) -> None:
        if tag in ("td", "th"):
            self._end_cell()
        elif tag in ("tr", "table"):
            self._end_row()

    def handle_data(self, data) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _clean(cell: str) -> str:
    return " ".join(cell.split()).replace("|", "\\|")


def _line(cells: list[str]) -> str:
    """One pipe row; cells are cleaned, empty cells at the end are dropped; '' for an empty row."""
    cells = [_clean(c) for c in cells]
    while cells and not cells[-1]:
        cells.pop()
    return "| " + " | ".join(cells) + " |" if cells else ""


def _html_rows(html: str):
    parser = _Rows()
    parser.feed(html)
    parser.close()
    parser._end_row()
    header: list[list[str]] = []
    data: list[list[str]] = []
    for row in parser.rows:
        cells = [text for _, text in row]
        if not data and row and all(head for head, _ in row):
            header.append(cells)
        else:
            data.append(cells)
    return header, data


def _pipe_rows(block: str):
    rows: list[list[str]] = []
    rule_at = None
    for raw in block.splitlines():
        line = raw.strip()
        if line.endswith("|") and not line.endswith("\\|") and len(line) > 1:
            line = line[:-1]
        cells = [c.strip().replace("\\|", "|") for c in _PIPE_SPLIT.split(line[1:])]
        if cells and all(_RULE_CELL.fullmatch(c) for c in cells):
            if rule_at is None:
                rule_at = len(rows)
            continue
        rows.append(cells)
    return rows[:rule_at or 0], rows[rule_at or 0:]


def parse_table(body: str):
    """(caption, header lines, data lines, columns, note) of the first table in a section.

    None when the section holds no table; both line lists are empty when the table has no content.
    """
    m = _HTML_TABLE.search(body)
    if m:
        header, data = _html_rows(m.group(0))
    else:
        m = _PIPE_BLOCK.search(body)
        if not m:
            return None
        header, data = _pipe_rows(m.group(0))
    cols = max((len(r) for r in header + data), default=0)
    head_lines = [s for s in map(_line, header) if s]
    data_lines = [s for s in map(_line, data) if s]
    caption = " ".join(body[:m.start()].split())
    note = " ".join(body[m.end():].split())
    return caption, head_lines, data_lines, cols, note


def _chunks(number: int, caption: str, head: list[str], data: list[str], cols: int, note: str,
            window: int) -> list[str]:
    """The table as passages of about `window` characters; each repeats the label and header rows."""
    rule = ["| " + " | ".join(["---"] * max(cols, 1)) + " |"] if head else []
    top = head + rule
    first = [f"### Table {number}"] + ([caption] if caption else []) + top
    again = [f"### Table {number} (continued)"] + (top if sum(map(len, top)) <= window // 2 else [])
    out: list[str] = []
    lines, size, filled = first, sum(len(s) + 1 for s in first), False
    for row in data + ([note] if note else []):
        if filled and size + len(row) + 1 > window:
            out.append("\n".join(lines) + "\n")
            lines, size = list(again), sum(len(s) + 1 for s in again)
        lines = lines + [row]
        size += len(row) + 1
        filled = True
    out.append("\n".join(lines) + "\n")
    return out


def prepare(text: str, source: str, window: int = 2000) -> Prepared:
    """Rewrite the '## Tables (structured)' part of a Markdown paper as pipe-row passages.

    Everything before the marker is kept as it is. The marker line and the converter's note under
    it are left out. A '### Table N' section without a readable table is kept as plain text.
    """
    plain = Prepared(text, len(text), (), ())
    if source != "markdown":
        return plain
    marker = MARKER.search(text)
    if marker is None:
        return plain
    labels = list(LABEL.finditer(text, marker.end()))
    if not labels:
        return plain
    body = text[:marker.start()].rstrip()
    parts = [body + "\n\n"] if body else []
    pos = body_end = len(parts[0]) if parts else 0
    segments: list[Segment] = []
    tables: list[Table] = []
    for n, label in enumerate(labels):
        number = int(label.group(1))
        section = text[label.end():labels[n + 1].start() if n + 1 < len(labels) else len(text)]
        parsed = parse_table(section)
        if parsed is not None and not parsed[1] and not parsed[2]:
            continue                     # a table without content: nothing to index
        if parsed is None:
            if not section.strip():
                continue
            pieces, kind = [f"### Table {number}\n\n{section.strip()}\n"], "text"
        else:
            pieces, kind = _chunks(number, *parsed, window), "table"
        start = pos
        for piece in pieces:
            segments.append(Segment(kind, number, pos, pos + len(piece)))
            parts.append(piece + "\n")
            pos += len(piece) + 1
        if parsed is not None:
            caption, head, data, cols, _ = parsed
            tables.append(Table(number, caption, len(head) + len(data), cols, start, pos - 1))
    return Prepared("".join(parts), body_end, tuple(segments), tuple(tables))
