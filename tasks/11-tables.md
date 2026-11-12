# Task 11 — Table-aware passages, `in_tables` search and `mode=tables`

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code |
| Reasoning | **medium** (the code is given below; the work is applying it exactly and running the tests). Set it in the app's model picker before pasting the prompt. |
| Budget | ≤ 30 tool calls |
| Depends on | task 10 committed (145 tests pass), release 0.1.0 at f25a01e |
| Done when | `.venv/bin/python -m pytest` shows **184 passed** (145 old + 39 new), the checksums match, report committed |

## Goal

First task of release 0.2.0 (plan v4). Papers in the Markdown corpus can carry a `## Tables (structured)` section: one `### Table N` heading per table, each with one HTML `<table>` (or a pipe table). Today that section is indexed as raw HTML and cut every 2,000 characters, in the middle of rows. After this task:

1. **Tables are indexed and returned as pipe rows** (`| a | b |`): entities decoded, markup gone, one table per passage, long tables cut at row ends with the header rows repeated.
2. **`zotero_search` has `in_tables=true`** (table cells only), and a hit inside a table says `kind: table` and its `table` number.
3. **`zotero_read` has `mode=tables`**: a list of the paper's tables, or one table with `table=N`.
4. **The index layout gets a version.** An index built by 0.1.0 is rebuilt by the next sync, resumably; until then the tools say what to do.

## Facts (measured on Gábor's corpus and index, 12 Nov 2026)

- 3,115 of 18,331 corpus files have the section: 10,290 tables, all as HTML with only `<table>`, `<tr>`, `<th>`, `<td>` and no attributes. 10,226 have one header row of `<th>` cells and then `<td>` rows; 64 have only the header row; 3 are empty.
- The reference implementation of this task was run over all 3,115 files: 10,287 tables converted (the 3 empty ones are skipped), and for every table the non-empty cell strings are identical to the HTML's, in number and content. The tables part shrinks to 70% of its characters and from 18,233 passages to 13,740. Converting all of them takes under 5 s.
- 136 table passages are longer than the 2,000-character window, because one row is: a row is never cut.
- Under the marker every file has the same converter's note of about 200 characters ("Extracted from the PDF layout. These are the cell strings…"). It is not paper text, it repeats words such as "cell" in 3,115 short passages, and it is left out of the index from now on, together with the marker line.
- **Pipe tables in a paper's body stay ordinary text.** 76% of the files have pipe-table blocks in the body, and by eye most are not tables: the text converter lays out multi-column prose and figures that way. Only the structured section is trusted. (Plan v4 said "recognise `<table>` blocks and pipe tables"; the measurement decided against the body ones. Inside the structured section both forms are read, as corpus spec v1 allows.)
- A mini-index of 300 real papers built with the reference: 848 tables, every table pages back whole through `mode=tables`; searches take under 0.01 s there.

## Design in short

- **The indexed text is a prepared text.** `zotcore/tables.py` rewrites the tables part of a Markdown paper: everything before the marker stays as it is, then each table follows as pipe rows. All positions in the index (`start`, `end`, `offset`, `next_offset`, `total_chars`) refer to this prepared text. For a paper without the section the prepared text is the file itself, so nothing changes for it.
- **One table, one or more passages.** A table that fits the window is one passage. A longer one is cut at row ends; the first piece starts with `### Table N`, the caption if there is one, the header rows and a rule row (`| --- | --- |`); every further piece starts with `### Table N (continued)`, the header rows and the rule row. Pieces are one blank line apart. A header taking more than half the window is not repeated.
- **Cells:** whitespace collapsed, `|` written as `\|`, inner tags dropped and their text kept, `<br>` is a space, `colspan=n` adds n-1 empty cells, empty cells at the end of a row are dropped, empty rows are dropped. Header rows are the leading rows made only of `<th>` cells (for a pipe table: the rows above the rule row).
- **Leftovers:** a `### Table N` section with text but no table is kept as plain text; an empty table is skipped; broken markup never raises.
- **Index (layout version 2):** `passage_map` gains `kind` (`text` / `table`) and `table_no`; a new table `item_tables` lists each paper's tables (number, caption, rows, columns, span). `state` holds `schema = 2`.
- **Old index:** opening it changes nothing. `zotero_search` and `zotero_read` answer with error `index_outdated`; `zotero_status` says `ready: false` with a hint. The next sync (CLI, tool or the nightly job) empties the index and fills it again; with a time budget it stops and resumes as before, and until it is done the status hint says the index is still being built.

## Files

```
create  zotcore/tables.py                         (verbatim, below)
create  tests/test_11_tables.py                   (verbatim, below)
replace skills/zotero-library/SKILL.md            (verbatim, below)
modify  zotcore/textsource.py, zotcore/index.py, zotcore/search.py, zotcore/tools.py, zotcore/cli.py   (the patch below)
modify  tests/test_08_annotations_citation_sync.py   (one line, in the patch; see the note)
create  tasks/11-report.md
commit  tasks/11-tables.md, tasks/README.md        (added or updated by the reviewer; commit them as they are)
```

Do not touch `plugin.yaml`, `pyproject.toml`, `README.md`, `__init__.py`, `tests/conftest.py`, or any other test.

**Note on `tests/test_08_annotations_citation_sync.py`.** AGENTS.md rule 4 says acceptance tests are read-only. This is the reviewer's own change and the only exception: one line asserted that `mode` has exactly two values, and it now lists the third. Change nothing else in that file.

## Steps

1. Run `.venv/bin/python -m pytest` first: 145 passed.
2. From the repo root, run this. It writes the three verbatim files and puts the patch into the system's temporary folder, and prints a SHA-256 for each:

```python
import hashlib, pathlib, re, tempfile
md = pathlib.Path("tasks/11-tables.md").read_text(encoding="utf-8")
for name, body in re.findall(r"<!-- file: (\S+) -->\n```\w*\n(.*?)\n```\n<!-- /file -->", md, re.S):
    out = pathlib.Path(tempfile.gettempdir()) / "task11.patch" if name == "PATCH" else pathlib.Path(name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body + "\n", encoding="utf-8", newline="\n")
    print(hashlib.sha256(out.read_bytes()).hexdigest(), out)
```

3. Compare the printed checksums with the table below. A mismatch means the copy went wrong: stop and fix it, do not edit the files.
4. Apply the patch from the repo root: `git apply --check <path printed for the patch>`, then `git apply <the same path>`. If a hunk does not apply, make the same change by hand; the tests decide.
5. Run `.venv/bin/python -m pytest`: 184 passed. Then `shasum -a 256` on the six patched files and compare with the second table.
6. Fill in the report `tasks/11-report.md` (the template is in the project rules file) and make one commit: `task 11: table-aware passages, in_tables, mode=tables`.

### Checksums

Verbatim files and the patch (must match):

| File | SHA-256 |
| --- | --- |
| `zotcore/tables.py` | `4e177e6dcdead3da2f1f0f2f15887e7f5f65e615d499fb0968c4fea4bff05d8a` |
| `tests/test_11_tables.py` | `19502931b876655228a88723a39207f73af1af9f1461dc1f759bf3d94b888f63` |
| `skills/zotero-library/SKILL.md` | `7290b3f0f93a7f1ce28c891be15ace7d067b21af4afd5a6e514463fdae67acee` |
| the patch file | `9e1f5e61b124c27d54278d7458f44a5cdfc4295d971f97ab4131b5d44ad6332b` |

Patched files after step 4 (they match when the patch applied cleanly; if you had to edit by hand and one differs, say so in the report):

| File | SHA-256 |
| --- | --- |
| `zotcore/textsource.py` | `1d769c24068e27a3cc8245b6a34a9f56019f1be1ad06b8fdd69e240a548bc6a7` |
| `zotcore/index.py` | `0581fa82d218ccdc586afd9fc25049a5949c3022b6567698f79f33d7ef5fa7db` |
| `zotcore/search.py` | `9e417f9e0f37a3bf27e842b2018ca6be9ce20402bb50116084bb7c86f5e6111f` |
| `zotcore/tools.py` | `23a824b70ce14811ec3bdf067748d807bf95a19a4f4d4337ffe28323a27e65d5` |
| `zotcore/cli.py` | `208088636fbb8bfb2bf54eca13596dc214651cb96bdf906cae07826d8c3950c1` |
| `tests/test_08_annotations_citation_sync.py` | `a91b03671118870e642f8dd130727a903a1893ec75bf90f53e6800c79800d8b8` |

## Spec — `zotcore/tables.py`

<!-- file: zotcore/tables.py -->
```python
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
```
<!-- /file -->

## Spec — the patch

What it does, file by file:

- `zotcore/textsource.py`: `Passage` gains `kind` and `table`; new `build_passages(text, source)` returns the prepared text, its passages and its tables. `split_passages` is unchanged.
- `zotcore/index.py`: `SCHEMA_VERSION = 2`, the two new columns and `item_tables`; `Index.schema_version()`, `Index.reset()`; `upsert` stores kinds and the table list; `counts()` adds `schema` and `tables`; `sync` resets an index of another layout and warns once.
- `zotcore/search.py`: `open_index` refuses an old layout (`index_outdated`); hits carry `kind`/`table`; `in_tables` narrows hits and coverage (and the coverage block says so); `list_tables`, `read_table`; text reads add `tables_count`.
- `zotcore/tools.py`: `in_tables` and `table` arguments, `mode=tables`, descriptions, the status hints for an old or half-built index.
- `zotcore/cli.py`: the sync summary prints the table count.

<!-- file: PATCH -->
```diff
diff --git a/tests/test_08_annotations_citation_sync.py b/tests/test_08_annotations_citation_sync.py
index 45eafbe..a1484d9 100644
--- a/tests/test_08_annotations_citation_sync.py
+++ b/tests/test_08_annotations_citation_sync.py
@@ -173,7 +173,7 @@ def test_sync_tool_is_registered_and_read_has_mode(plugin_module, fake_ctx):
     plugin_module.register(fake_ctx)
     assert {"zotero_status", "zotero_search", "zotero_read", "zotero_sync"} == set(fake_ctx.tools)
     mode = fake_ctx.tools["zotero_read"]["schema"]["parameters"]["properties"]["mode"]
-    assert mode["enum"] == ["text", "annotations"]
+    assert mode["enum"] == ["text", "annotations", "tables"]
     props = fake_ctx.tools["zotero_sync"]["schema"]["parameters"]["properties"]
     assert set(props) == {"budget_seconds"}
     assert "Zotero" in fake_ctx.tools["zotero_sync"]["schema"]["description"][:60]
diff --git a/zotcore/cli.py b/zotcore/cli.py
index d4b76f1..3806261 100644
--- a/zotcore/cli.py
+++ b/zotcore/cli.py
@@ -82,7 +82,7 @@ def _sync_locked(settings: Settings, root: Path, data_dir) -> int:
         print(f"Sync: indexed {report.indexed}, deleted {report.deleted}, "
               f"examined {report.examined} in {report.seconds:.1f}s")
         c = index.counts()
-        print(f"Index: {c['items']} items, {c['passages']} passages; "
+        print(f"Index: {c['items']} items, {c['passages']} passages, {c['tables']} tables; "
               f"text sources {c['by_source']}; flags {c['flags']}")
     finally:
         index.close()
diff --git a/zotcore/index.py b/zotcore/index.py
index ed01ba3..c2aac6d 100644
--- a/zotcore/index.py
+++ b/zotcore/index.py
@@ -10,10 +10,11 @@ from datetime import datetime, timezone
 from pathlib import Path
 from typing import Callable, Iterable, Sequence
 
-from .textsource import TextResult, choose_text, split_passages, text_signature
+from .textsource import TextResult, build_passages, choose_text, text_signature
 from .zdb import list_items, libraries as zotero_libraries, load_items, open_snapshot
 
 CHUNK = 500
+SCHEMA_VERSION = 2   # 2: passages know their kind, structured tables are listed (0.2.0)
 MAX_ITEM_WARNINGS = 20
 
 SCHEMA = (
@@ -21,11 +22,15 @@ SCHEMA = (
   creators TEXT, year INTEGER, date TEXT, doi TEXT, publication TEXT, abstract TEXT, collections TEXT, tags TEXT, date_added TEXT,
   modified TEXT, text_source TEXT, text_path TEXT, flags TEXT, signature TEXT, n_passages INTEGER, PRIMARY KEY (library, item_key))""",
     "CREATE INDEX IF NOT EXISTS items_doi ON items(doi)",
-    "CREATE TABLE IF NOT EXISTS passage_map (rowid INTEGER PRIMARY KEY, library TEXT NOT NULL, item_key TEXT NOT NULL)",
+    """CREATE TABLE IF NOT EXISTS passage_map (rowid INTEGER PRIMARY KEY, library TEXT NOT NULL, item_key TEXT NOT NULL,
+  kind TEXT NOT NULL DEFAULT 'text', table_no INTEGER)""",
     "CREATE INDEX IF NOT EXISTS passage_map_item ON passage_map(library, item_key)",
     """CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(title, section, body, library UNINDEXED, item_key UNINDEXED,
   start UNINDEXED, end UNINDEXED, tokenize='porter unicode61 remove_diacritics 2')""",
     "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)",
+    """CREATE TABLE IF NOT EXISTS item_tables (library TEXT NOT NULL, item_key TEXT NOT NULL, number INTEGER NOT NULL,
+  caption TEXT, n_rows INTEGER, n_cols INTEGER, start INTEGER NOT NULL, "end" INTEGER NOT NULL,
+  PRIMARY KEY (library, item_key, start))""",
 )
 
 
@@ -59,8 +64,26 @@ class Index:
         self.con: sqlite3.Connection = sqlite3.connect(str(path), isolation_level=None)
         self.con.execute("PRAGMA journal_mode=WAL")
         self.con.execute("PRAGMA synchronous=NORMAL")
+        fresh = self.con.execute("SELECT 1 FROM sqlite_master WHERE name = 'items'").fetchone() is None
         for statement in SCHEMA:
             self.con.execute(statement)
+        if fresh:
+            self.set_state("schema", str(SCHEMA_VERSION))
+
+    def schema_version(self) -> int:
+        """Layout version of this index file; 1 for an index built by 0.1.0."""
+        value = self.get_state("schema")
+        return int(value) if value and value.isdigit() else 1
+
+    def reset(self) -> None:
+        """Empty an index built with another layout; the next sync fills it again from scratch."""
+        with self.transaction():
+            for table in ("passages", "passage_map", "item_tables", "items"):
+                self.con.execute(f"DROP TABLE IF EXISTS {table}")
+            for statement in SCHEMA:
+                self.con.execute(statement)
+            self.con.execute("DELETE FROM state")
+            self.set_state("schema", str(SCHEMA_VERSION))
 
     def close(self) -> None:
         """Close the database connection."""
@@ -94,9 +117,10 @@ class Index:
             chunk = rowids[start:start + CHUNK]
             self.con.execute(f"DELETE FROM passages WHERE rowid IN ({','.join('?' * len(chunk))})", chunk)
         self.con.execute("DELETE FROM passage_map WHERE library = ? AND item_key = ?", (library, key))
+        self.con.execute("DELETE FROM item_tables WHERE library = ? AND item_key = ?", (library, key))
 
-    def upsert(self, item, text, passages: Sequence) -> None:
-        """Replace the item row and all of its passages."""
+    def upsert(self, item, text, passages: Sequence, tables: Sequence = ()) -> None:
+        """Replace the item row, all of its passages and its table list."""
         self._drop_passages(item.library, item.key)
         self.con.execute(
             "INSERT OR REPLACE INTO items (library, item_key, item_id, item_type, title, creators, year, date, doi, "
@@ -107,12 +131,15 @@ class Index:
              json.dumps(list(item.tags)), item.date_added, item.modified, text.source, text.path,
              json.dumps(list(text.flags)), text.signature, len(passages)))
         for p in passages:
-            rowid = self.con.execute("INSERT INTO passage_map (library, item_key) VALUES (?, ?)",
-                                     (item.library, item.key)).lastrowid
+            rowid = self.con.execute("INSERT INTO passage_map (library, item_key, kind, table_no) VALUES (?, ?, ?, ?)",
+                                     (item.library, item.key, p.kind, p.table)).lastrowid
             self.con.execute(
                 'INSERT INTO passages (rowid, title, section, body, library, item_key, start, "end") '
                 "VALUES (?,?,?,?,?,?,?,?)",
                 (rowid, item.title, p.section, p.text, item.library, item.key, p.start, p.end))
+        for t in tables:
+            self.con.execute("INSERT OR REPLACE INTO item_tables VALUES (?,?,?,?,?,?,?,?)",
+                             (item.library, item.key, t.number, t.caption, t.rows, t.cols, t.start, t.end))
 
     def delete(self, library: str, keys: Iterable[str]) -> int:
         """Remove items and their passages; returns the number of item rows removed."""
@@ -139,9 +166,12 @@ class Index:
         for (raw,) in con.execute("SELECT flags FROM items WHERE flags IS NOT NULL AND flags != '[]'"):
             for flag in json.loads(raw):
                 flags[flag] = flags.get(flag, 0) + 1
+        current = self.schema_version() == SCHEMA_VERSION
         return {
+            "schema": self.schema_version(),
             "items": con.execute("SELECT COUNT(*) FROM items").fetchone()[0],
             "passages": con.execute("SELECT COUNT(*) FROM passage_map").fetchone()[0],
+            "tables": con.execute("SELECT COUNT(*) FROM item_tables").fetchone()[0] if current else 0,
             "libraries": dict(con.execute("SELECT library, COUNT(*) FROM items GROUP BY library ORDER BY library")),
             "by_source": dict(con.execute("SELECT text_source, COUNT(*) FROM items GROUP BY text_source")),
             "flags": flags,
@@ -155,6 +185,9 @@ def sync(index: Index, snapshot_path, data_dir, *, libraries: Sequence[str] = ("
     """Bring the index in line with a snapshot. Safe to interrupt; the next run resumes."""
     t0 = clock()
     warnings: list[str] = []
+    if index.schema_version() != SCHEMA_VERSION:
+        index.reset()
+        warnings.append("the index was built by another plugin version and is being rebuilt from scratch")
     con = open_snapshot(snapshot_path)
     try:
         known = zotero_libraries(con)
@@ -200,7 +233,8 @@ def sync(index: Index, snapshot_path, data_dir, *, libraries: Sequence[str] = ("
                                             "indexed title and abstract only")
                         text = TextResult("metadata", "\n\n".join(p for p in (item.title, item.abstract) if p),
                                           None, ("body_not_read", "read_error"), signature)
-                    index.upsert(item, text, split_passages(text.text, text.source))
+                    _, passages, tables = build_passages(text.text, text.source)
+                    index.upsert(item, text, passages, tables)
                     indexed += 1
             examined += len(batch)
             if progress is not None:
diff --git a/zotcore/search.py b/zotcore/search.py
index 77c8753..1a83a2a 100644
--- a/zotcore/search.py
+++ b/zotcore/search.py
@@ -7,6 +7,7 @@ import sqlite3
 from datetime import date
 from pathlib import Path
 
+from .index import SCHEMA_VERSION
 from .zdb import normalize_doi
 
 STOPWORDS = frozenset(
@@ -17,10 +18,15 @@ POOL = 200                 # top passages examined before grouping them by item
 SNIPPET_TOKENS = 24
 MAX_SEARCH_CHARS = 12000   # cap on the whole JSON answer of zotero_search
 MAX_COLLECTIONS = 3        # collection paths shown per hit
+MAX_TABLES_LISTED = 100    # tables listed by zotero_read mode=tables
+MAX_CAPTION_CHARS = 160
 BM25 = "bm25(passages, 2.0, 1.0, 1.0)"   # title counts double; columns are title, section, body
 
 _JOIN = "FROM passages p JOIN passage_map m ON m.rowid = p.rowid"
 _SCOPE_JOIN = " JOIN temp.scope s ON s.library = m.library AND s.item_key = m.item_key"
+_TABLES_ONLY = " AND m.kind = 'table'"
+OUTDATED_HINT = ("Call zotero_sync and repeat it until it reports done: true (a one-time rebuild), "
+                 "or ask the user to run `hermes zotero sync` in a terminal.")
 
 
 class SearchError(Exception):
@@ -39,7 +45,16 @@ def open_index(path) -> sqlite3.Connection:
     if not p.exists():
         raise SearchError("no_index", "The Zotero index has not been built yet.",
                           "Run `hermes zotero sync` in a terminal, then try again.")
-    return sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
+    con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
+    try:
+        version = _state(con, "schema")
+    except sqlite3.Error:
+        version = None
+    if version != str(SCHEMA_VERSION):
+        con.close()
+        raise SearchError("index_outdated", "The Zotero index was built by an older version of the plugin.",
+                          OUTDATED_HINT)
+    return con
 
 
 def query_terms(query) -> tuple[list[str], bool]:
@@ -123,19 +138,20 @@ def _hit(lib: str, key: str, row, match: str, passages: list[dict]) -> dict:
     return hit
 
 
-def _find_hits(con, terms, scoped, limit) -> list[dict]:
+def _find_hits(con, terms, scoped, limit, in_tables=False) -> list[dict]:
     per_item = 2 if limit <= 10 else 1
     slots: dict = {}   # (lib, key) -> [pass, passages]
     sql = (f"SELECT m.library, m.item_key, p.start, CASE WHEN p.section = p.title THEN '' ELSE p.section END, "
-           f"snippet(passages, 2, '«', '»', '…', {SNIPPET_TOKENS}) {_JOIN}{_SCOPE_JOIN if scoped else ''} "
-           f"WHERE passages MATCH ? ORDER BY {BM25} LIMIT ?")
+           f"snippet(passages, 2, '«', '»', '…', {SNIPPET_TOKENS}), m.kind, m.table_no "
+           f"{_JOIN}{_SCOPE_JOIN if scoped else ''} "
+           f"WHERE passages MATCH ?{_TABLES_ONLY if in_tables else ''} ORDER BY {BM25} LIMIT ?")
     passes = [("all", _all_expr(terms))]
     if len(terms) > 1:
         passes.append(("any", _any_expr(terms)))
     for name, expr in passes:
         if len(slots) >= limit:
             break
-        for lib, key, start, section, snippet in con.execute(sql, (expr, max(POOL, limit * 20))):
+        for lib, key, start, section, snippet, kind, table_no in con.execute(sql, (expr, max(POOL, limit * 20))):
             slot = slots.get((lib, key))
             if slot is None:
                 if len(slots) >= limit:
@@ -146,19 +162,23 @@ def _find_hits(con, terms, scoped, limit) -> list[dict]:
             passage = {"offset": start, "snippet": snippet}
             if section:
                 passage["section"] = section
+            if kind == "table":
+                passage["kind"] = "table"
+                passage["table"] = table_no
             slot[1].append(passage)
     rows = _item_rows(con, slots)
     return [_hit(lib, key, rows[(lib, key)], name, passages)
             for (lib, key), (name, passages) in slots.items() if (lib, key) in rows]
 
 
-def _coverage(con, terms, scoped, settings, this_year) -> dict:
+def _coverage(con, terms, scoped, settings, this_year, in_tables=False) -> dict:
     join = _JOIN + (_SCOPE_JOIN if scoped else "")
+    only = _TABLES_ONLY if in_tables else ""
     any_n = con.execute(f"SELECT COUNT(*) FROM (SELECT DISTINCT m.library, m.item_key {join} "
-                        "WHERE passages MATCH ?)", (_any_expr(terms),)).fetchone()[0]
+                        f"WHERE passages MATCH ?{only})", (_any_expr(terms),)).fetchone()[0]
     all_n, recent, newest = con.execute(
         f"SELECT COUNT(*), SUM(i.year >= ?), MAX(i.year) FROM (SELECT DISTINCT m.library, m.item_key {join} "
-        "WHERE passages MATCH ?) d JOIN items i ON i.library = d.library AND i.item_key = d.item_key",
+        f"WHERE passages MATCH ?{only}) d JOIN items i ON i.library = d.library AND i.item_key = d.item_key",
         (this_year - settings.coverage_recent_years + 1, _all_expr(terms))).fetchone()
     recent = recent or 0
     if all_n == 0:
@@ -169,7 +189,11 @@ def _coverage(con, terms, scoped, settings, this_year) -> dict:
         verdict = "thin"
     cov = {"matches_all": all_n, "matches_any": any_n, "recent": recent,
            "recent_years": settings.coverage_recent_years, "newest_year": newest, "verdict": verdict}
-    if all_n == 0 and any_n > 0 and len(terms) > 1:
+    if in_tables:
+        cov["in_tables"] = True
+        cov["hint"] = ("Counts cover table cells only. Judge what the library holds on a topic from a search "
+                       "without in_tables.")
+    elif all_n == 0 and any_n > 0 and len(terms) > 1:
         cov["hint"] = "No passage contains every term; retry with fewer or broader terms before using the web."
     return cov
 
@@ -248,6 +272,77 @@ def item_info(con, library: str, key: str) -> dict:
             "flags": json.loads(flags or "[]")}
 
 
+def _table_rows(con, library: str, key: str) -> list[tuple]:
+    return con.execute('SELECT number, caption, n_rows, n_cols, start, "end" FROM item_tables '
+                       "WHERE library = ? AND item_key = ? ORDER BY start", (library, key)).fetchall()
+
+
+def _table_entry(row) -> dict:
+    number, caption, n_rows, n_cols, start, end = row
+    caption = caption or ""
+    if len(caption) > MAX_CAPTION_CHARS:
+        caption = caption[:MAX_CAPTION_CHARS - 1].rstrip() + "…"
+    return {"table": number, "caption": caption or None, "rows": n_rows, "cols": n_cols, "chars": end - start}
+
+
+def list_tables(con, *, key, library=None) -> dict:
+    """The structured tables of one item: number, caption, size."""
+    lib, k = find_item(con, key, library)
+    rows = _table_rows(con, lib, k)
+    warnings: list[str] = []
+    if not rows:
+        warnings.append("this paper has no structured tables in the index; "
+                        "read the text instead (mode=text with a query)")
+    if len(rows) > MAX_TABLES_LISTED:
+        warnings.append(f"only the first {MAX_TABLES_LISTED} tables are listed")
+    return {**item_info(con, lib, k), "total_tables": len(rows),
+            "tables": [_table_entry(r) for r in rows[:MAX_TABLES_LISTED]], "warnings": warnings}
+
+
+def read_table(con, *, key, table: int, library=None, offset=None, max_chars: int) -> dict:
+    """One structured table as pipe rows: whole pieces while they fit max_chars."""
+    lib, k = find_item(con, key, library)
+    rows = [r for r in _table_rows(con, lib, k) if r[0] == table]
+    if not rows:
+        raise SearchError("not_found", f"this paper has no table {table} in the index",
+                          "Call zotero_read with mode=tables and no table to list the tables.")
+    warnings: list[str] = []
+    if len(rows) > 1:
+        warnings.append(f"{len(rows)} tables are numbered {table}; this is the first")
+    start, end = rows[0][4], rows[0][5]
+    pos = start
+    if offset is not None:
+        if start <= offset < end:
+            pos = offset
+        else:
+            warnings.append(f"offset {offset} is outside table {table} ({start}-{end}); showing its start")
+    pieces = con.execute(
+        'SELECT p.start, p."end", p.body FROM passage_map m JOIN passages p ON p.rowid = m.rowid '
+        "WHERE m.library = ? AND m.item_key = ? AND m.kind = 'table' AND p.start >= ? AND p.\"end\" <= ? "
+        "ORDER BY p.start", (lib, k, start, end)).fetchall()
+    parts: list[str] = []
+    used = 0
+    cursor = pos
+    for p_start, p_end, body in pieces:
+        if p_end <= pos:
+            continue
+        piece = body[max(pos - p_start, 0):]
+        if used + len(piece) > max_chars:
+            if not parts:   # one piece is larger than the limit: cut it at a row end
+                cut = piece.rfind("\n", 0, max_chars) + 1 or max_chars
+                parts.append(piece[:cut])
+                cursor = max(pos, p_start) + cut
+                warnings.append("max_chars is smaller than one piece of this table, so the piece was cut; "
+                                "the next page starts without the header rows")
+            break
+        parts.append(piece)
+        used += len(piece) + 1
+        cursor = p_end
+    return {**item_info(con, lib, k), "table": _table_entry(rows[0]), "total_chars": end - start, "offset": pos,
+            "next_offset": None if cursor >= end else (cursor if cursor > pos else None),
+            "text": "\n".join(parts), "warnings": warnings}
+
+
 def read_item(con, *, key, library=None, query=None, offset=None, max_chars: int) -> dict:
     """Return a bounded piece of one item's text."""
     lib, k = find_item(con, key, library)
@@ -269,7 +364,7 @@ def read_item(con, *, key, library=None, query=None, offset=None, max_chars: int
         warnings.append(f"offset {pos} is past the end of the text ({total} characters)")
     return {**item_info(con, lib, k), "total_chars": total, "offset": pos,
             "next_offset": None if end >= total else end, "section": section or None,
-            "text": text, "warnings": warnings}
+            "text": text, "tables_count": len(_table_rows(con, lib, k)), "warnings": warnings}
 
 
 def _doi_check(con, doi, terms) -> dict:
@@ -288,7 +383,7 @@ def _doi_check(con, doi, terms) -> dict:
 
 
 def search(con, settings, *, query=None, doi=None, library=None, collection=None, year_from=None,
-           year_to=None, limit=10, this_year=None, tag=None) -> dict:
+           year_to=None, limit=10, this_year=None, tag=None, in_tables=False) -> dict:
     """Search the index; see the task spec for the result layout."""
     terms, truncated = query_terms(query)
     if not terms and not doi:
@@ -303,8 +398,8 @@ def search(con, settings, *, query=None, doi=None, library=None, collection=None
     if scoped and _build_scope(con, library, collection, year_from, year_to, tag):
         warnings.append("no indexed items match the filters")
     if terms:
-        result["hits"] = _find_hits(con, terms, scoped, limit)
-        result["coverage"] = _coverage(con, terms, scoped, settings, this_year or date.today().year)
+        result["hits"] = _find_hits(con, terms, scoped, limit, in_tables)
+        result["coverage"] = _coverage(con, terms, scoped, settings, this_year or date.today().year, in_tables)
     else:
         result["hits"] = []
         result["coverage"] = None
diff --git a/zotcore/textsource.py b/zotcore/textsource.py
index d8ca0ce..b243b0b 100644
--- a/zotcore/textsource.py
+++ b/zotcore/textsource.py
@@ -6,6 +6,7 @@ import re
 from dataclasses import dataclass
 from pathlib import Path
 
+from .tables import Table, prepare
 from .zdb import normalize_doi
 
 MIN_BYTES = 200
@@ -30,6 +31,8 @@ class Passage:
     start: int
     end: int
     text: str
+    kind: str = "text"            # "text" | "table"
+    table: int | None = None      # the N of '### Table N' for a table passage
 
 
 def doi_slug(doi: str) -> str:
@@ -207,3 +210,23 @@ def split_passages(text: str, source: str, *, window: int = 2000, overlap: int =
             if piece.strip():
                 passages.append(Passage(name, a, b, piece))
     return passages
+
+
+def build_passages(text: str, source: str, *, window: int = 2000,
+                   overlap: int = 200) -> tuple[str, list[Passage], tuple[Table, ...]]:
+    """The text as it is indexed, its passages and its structured tables.
+
+    Positions (Passage.start/end, Table.start/end) refer to the returned text, in which each
+    structured table stands as pipe rows; for a paper without such tables it is `text` itself.
+    """
+    prep = prepare(text, source, window)
+    passages = split_passages(prep.text[:prep.body_end], source, window=window, overlap=overlap)
+    for seg in prep.segments:
+        name = f"Table {seg.number}"
+        if seg.kind == "table":
+            passages.append(Passage(name, seg.start, seg.end, prep.text[seg.start:seg.end], "table", seg.number))
+        else:
+            for a, b in _window(prep.text, seg.start, seg.end, window, overlap):
+                if prep.text[a:b].strip():
+                    passages.append(Passage(name, a, b, prep.text[a:b]))
+    return prep.text, passages, prep.tables
diff --git a/zotcore/tools.py b/zotcore/tools.py
index 21ce9b0..db15d1c 100644
--- a/zotcore/tools.py
+++ b/zotcore/tools.py
@@ -10,9 +10,10 @@ from . import __version__
 from .annotations import load_annotations, open_current_snapshot, page_entries
 from .citation import citation
 from .datadir import resolve_data_dir
-from .index import Index
+from .index import SCHEMA_VERSION, Index
 from .jsonout import err, ok, safe
-from .search import MAX_SEARCH_CHARS, SearchError, find_item, item_info, open_index, read_item, search
+from .search import (MAX_SEARCH_CHARS, OUTDATED_HINT, SearchError, find_item, item_info, list_tables, open_index,
+                     read_item, read_table, search)
 from .settings import Settings
 from .snapshot import is_stale, load_info
 from .synctool import sync_step
@@ -22,11 +23,12 @@ STATUS_DESC = ("Zotero index status: whether the local library index is ready an
 SEARCH_DESC = ("Zotero library search: find papers the user already owns, before using the web. "
                "Full text, offline, ranked by passage. Returns short snippets and a coverage verdict "
                "(strong / thin / none) for the topic. Filters: collection, tag, year, library; "
-               "doi= checks whether one paper is held.")
-READ_DESC = ("Zotero paper reader: read part of one paper, or the user's highlights on it. "
+               "in_tables=true searches table cells only; doi= checks whether one paper is held.")
+READ_DESC = ("Zotero paper reader: read part of a paper, its tables or the user's highlights. "
              "Give a key from zotero_search and a query (starts at the best match) or an offset "
              "(next_offset pages on); every result carries a citation line. "
-             "mode=annotations returns the user's own highlights, comments and notes instead of the text.")
+             "mode=tables lists the paper's tables, and with table=N returns one; "
+             "mode=annotations returns the user's highlights, comments and notes.")
 SYNC_DESC = ("Zotero index update: add new and changed papers from Zotero to the local index. "
              "Each call stops after budget_seconds and the next call resumes; it reports progress and "
              "how many items remain. Use it when the user has added papers or zotero_status says Zotero changed.")
@@ -38,6 +40,7 @@ SEARCH_SCHEMA = {"type": "object", "properties": {
     "library": {"type": "string", "description": "'user' or a group ID. Default: all indexed libraries."},
     "year_from": {"type": "integer"},
     "year_to": {"type": "integer"},
+    "in_tables": {"type": "boolean", "description": "true: search only inside the papers' tables (numbers, baseline values)."},
     "limit": {"type": "integer", "minimum": 1, "maximum": 25, "description": "Papers to return (default 10)."}}}
 READ_SCHEMA = {"type": "object", "properties": {
     "key": {"type": "string", "description": "Item key from zotero_search, e.g. 'ABCD2345'."},
@@ -45,8 +48,10 @@ READ_SCHEMA = {"type": "object", "properties": {
     "query": {"type": "string", "description": "Start at the passage that best matches these words."},
     "offset": {"type": "integer", "minimum": 0, "description": "Start at this character (next_offset of a previous read)."},
     "max_chars": {"type": "integer", "description": "Characters to return (default and cap set by the user)."},
-    "mode": {"type": "string", "enum": ["text", "annotations"],
-             "description": "'text' (default): the paper's text. 'annotations': the user's highlights, comments and notes."}},
+    "mode": {"type": "string", "enum": ["text", "annotations", "tables"],
+             "description": "'text' (default): the paper's text. 'annotations': the user's highlights, comments and notes. "
+                            "'tables': the paper's tables (a list, or one table with table=N)."},
+    "table": {"type": "integer", "minimum": 1, "description": "With mode=tables: the number of the table to return."}},
     "required": ["key"]}
 SYNC_SCHEMA = {"type": "object", "properties": {
     "budget_seconds": {"type": "integer", "minimum": 5, "maximum": 60,
@@ -75,12 +80,30 @@ def _str_arg(args: dict, name: str):
     return str(v).strip() or None
 
 
-def _status_hint(ready: bool, data_dir, snapshot) -> str | None:
+def _bool_arg(args: dict, name: str) -> bool:
+    """Boolean argument; accepts booleans, 0/1 and the words true/false/yes/no."""
+    v = args.get(name)
+    if v is None or v == "":
+        return False
+    if isinstance(v, bool):
+        return v
+    if isinstance(v, int) and v in (0, 1):
+        return bool(v)
+    if isinstance(v, str) and v.strip().lower() in ("true", "false", "yes", "no", "1", "0"):
+        return v.strip().lower() in ("true", "yes", "1")
+    raise SearchError("invalid_argument", f"{name} must be true or false")
+
+
+def _status_hint(ready: bool, data_dir, snapshot, index=None) -> str | None:
     """What the agent should do next, as one sentence, or None."""
+    if index is not None and index["schema"] != SCHEMA_VERSION:
+        return "The index was built by an older version of the plugin. " + OUTDATED_HINT
     if not ready and data_dir is None:
         return "Zotero's data directory was not found: ask the user to run `hermes zotero doctor` in a terminal."
     if not ready:
         return "The index is empty: ask the user to run `hermes zotero sync` in a terminal once."
+    if index is not None and index["last_sync"] is None:
+        return "The index is still being built, so results are incomplete: call zotero_sync until it reports done: true."
     if snapshot is not None and snapshot["stale"]:
         return "Zotero has changed since the last sync: call zotero_sync to add the changes."
     return None
@@ -129,8 +152,8 @@ def tool_specs(settings_provider: Callable[[], Settings],
                 if info is not None:
                     snapshot = {"taken_at": info.taken_at,
                                 "stale": is_stale(info, found.path) if found.path else None}
-        ready = bool(index and index["items"] > 0)
-        return ok(plugin_version=__version__, ready=ready, hint=_status_hint(ready, found.path, snapshot),
+        ready = bool(index and index["items"] > 0 and index["schema"] == SCHEMA_VERSION)
+        return ok(plugin_version=__version__, ready=ready, hint=_status_hint(ready, found.path, snapshot, index),
                   settings=s.as_dict(), warnings=warnings,
                   data_dir=found.as_dict(), snapshot=snapshot, index=index)
 
@@ -155,7 +178,7 @@ def tool_specs(settings_provider: Callable[[], Settings],
             limit = min(max(_int_arg(args, "limit", 10), 1), 25)
             payload = search(con, s, query=_str_arg(args, "query"), doi=_str_arg(args, "doi"),
                              library=_str_arg(args, "library"), collection=_str_arg(args, "collection"),
-                             tag=_str_arg(args, "tag"),
+                             tag=_str_arg(args, "tag"), in_tables=_bool_arg(args, "in_tables"),
                              year_from=_int_arg(args, "year_from"), year_to=_int_arg(args, "year_to"), limit=limit)
             out = ok(**payload)
             dropped = 0
@@ -174,22 +197,34 @@ def tool_specs(settings_provider: Callable[[], Settings],
 
         def run(con) -> str:
             mode = (_str_arg(args, "mode") or "text").lower()
-            if mode not in ("text", "annotations"):
-                return err("invalid_argument", "mode must be 'text' or 'annotations'")
+            if mode not in ("text", "annotations", "tables"):
+                return err("invalid_argument", "mode must be 'text', 'annotations' or 'tables'")
             max_chars = min(max(_int_arg(args, "max_chars", s.read_max_chars_default), 200), s.read_max_chars_cap)
             offset = _int_arg(args, "offset")
             offset = None if offset is None else max(offset, 0)
             query = _str_arg(args, "query")
+            table = _int_arg(args, "table")
             if mode == "text":
                 payload = read_item(con, key=_str_arg(args, "key"), library=_str_arg(args, "library"),
                                     query=query, offset=offset, max_chars=max_chars)
+                if table is not None:
+                    payload["warnings"].append("table is only used with mode=tables")
+            elif mode == "tables":
+                if table is None:
+                    payload = list_tables(con, key=_str_arg(args, "key"), library=_str_arg(args, "library"))
+                else:
+                    payload = read_table(con, key=_str_arg(args, "key"), table=table,
+                                         library=_str_arg(args, "library"), offset=offset, max_chars=max_chars)
+                if query:
+                    payload["warnings"].append("query is not used in tables mode; "
+                                               "use zotero_search with in_tables=true to find a table")
             else:
                 lib, k = find_item(con, _str_arg(args, "key"), _str_arg(args, "library"))
                 payload = item_info(con, lib, k)
             lib, k = payload["library"], payload["key"]
             root = Path(data_root())
             loaded = None
-            snap = open_current_snapshot(root)
+            snap = None if mode == "tables" else open_current_snapshot(root)
             if snap is not None:
                 try:
                     loaded = load_annotations(snap, lib, k)
@@ -198,7 +233,7 @@ def tool_specs(settings_provider: Callable[[], Settings],
             payload["mode"] = mode
             if mode == "text":
                 payload["annotations_count"] = None if loaded is None else len(loaded[0])
-            else:
+            elif mode == "annotations":
                 entries, empty = loaded if loaded is not None else ([], 0)
                 start = offset or 0
                 page, next_offset = page_entries(entries, start, max_chars)
```
<!-- /file -->

## Spec — `skills/zotero-library/SKILL.md`

Reviewer-written; replace the file with this, byte for byte. If something in it looks wrong, say so in the report.

<!-- file: skills/zotero-library/SKILL.md -->
```markdown
---
name: zotero-library
description: "Research questions: check the user's Zotero library first"
version: 0.2.0
metadata:
  hermes:
    tags: [zotero, literature, research, citations, local-first]
---

# Zotero library first

The hermes-zotero plugin keeps a local, read-only index of the user's Zotero library. For any question about scientific or scholarly literature, a specific paper, or the user's own highlights and notes, search the library before the web. The tools never change Zotero.

## Search

1. Call `zotero_search` with 2-4 distinctive keywords, not a sentence: `SCD1 ferroptosis`, not "what does SCD1 do in ferroptosis". Use scientific names, not brand names (`tirzepatide`, not Mounjaro). A hit with `match: all` has one passage holding every word; `match: any` hits hold only some of them and are weaker evidence.
2. Check `terms` in the result: stop words and words like the "a" in Lp(a) are dropped. If the distinctive word is missing, rephrase.
3. When the user names a collection, tag, year range or group, pass `collection`, `tag`, `year_from`, `year_to` or `library`. Filters also narrow the coverage counts, so judge gaps from a search without them. To check one paper, pass `doi` and read `doi_check.held`.
4. Let `coverage.verdict` decide where to look:
   - `strong`: answer from the library.
   - `thin`: answer from the library, then use the web only for what is missing, and say which sources came from where.
   - `none` with a `hint`: no passage holds every word. Retry with fewer or broader words before treating it as a gap.
   - `none` without a hint: the library has nothing on this. Say so, then use the web.

## Read before citing

A snippet is a search hit, not evidence. For the 3-5 best papers, call `zotero_read` with `key` and `query`: it starts at the best-matching passage. Page on with `offset` set to `next_offset` when the methods or results come later. Ask for what the question needs (`max_chars` 1500-4000), never a whole paper.

- Cite with the `citation` field. `approximate: true` means it was built from the index, not by Zotero: check the details before giving a formatted reference.
- Flags `body_not_read` or `scanned_or_empty` mean the paper's body text is not in the index (metadata only); `truncated` means Zotero extracted only the first pages. Do not report results you have not read.
- `mode` = `annotations` returns the user's highlights, comments and notes on the paper. `author: user` marks the user's own words; quote them as theirs. Any other author is a group member or the PDF's creator.

## Numbers and tables

For numbers (baseline values, effect sizes, doses), use the papers' tables, which are kept as pipe rows:

- `zotero_search` with `in_tables` = true searches table cells only. Its coverage then counts tables only: never judge a gap from it.
- A passage with `kind: table` names its `table`. `zotero_read` with `mode` = `tables` and that `table` returns the whole table; without `table` it lists the paper's tables.
- Cells are the PDF's own strings, and a long table comes in pieces that repeat the header. Check the header and the units before quoting a number.

## Keep the index fresh

- Error `no_index`: ask the user to run `hermes zotero sync` once in a terminal. A large library takes a few minutes.
- Error `index_outdated` (after a plugin update): call `zotero_sync` until it returns `done: true`.
- `zotero_status` says whether the index is `ready` and gives a `hint` when Zotero has changed since the last sync.
- When the user has added papers, or the hint says so, call `zotero_sync`. While it returns `done: false`, call it again.

## Limits

- Use these tools, not other ways of opening Zotero's database or the plugin's index.
- Quote short passages with their citation; do not paste whole papers into the answer.
```
<!-- /file -->

## Acceptance tests — `tests/test_11_tables.py`

<!-- file: tests/test_11_tables.py -->
```python
import json
import re
import sqlite3
from pathlib import Path

import pytest

from tests.zfixture import ZoteroFixture
from zotcore import tools
from zotcore.index import SCHEMA_VERSION, Index, sync
from zotcore.settings import Settings
from zotcore.tables import prepare
from zotcore.textsource import MarkdownCorpus, build_passages, split_passages

ROOT = Path(__file__).resolve().parents[1]
NOTE = "Extracted from the PDF layout. These are the cell strings, not a paraphrase of the prose.\n\n"
HEAD = "# Paper\n\n- **Year:** 2020\n\n---\n\n## Results\n\nBody text about adiponectin in plasma.\n\n"
T1 = ("### Table 1\n\n<table>\n<tr><th></th><th>Women (n = 12)</th><th>Men</th></tr>\n"
      "<tr><td>Age (yr)</td><td>59 &plusmn; 11</td><td>58 &#177; 11</td></tr>\n"
      "<tr><td>P value</td><td>p &lt; 0.05</td><td></td></tr>\n"
      "<tr><td></td><td></td><td></td></tr>\n"
      "<tr><td>Ratio a|b</td><td>  1.5\n  (0.9) </td><td>n/a</td></tr>\n</table>\n\n")
T1_PIPES = ("### Table 1\n|  | Women (n = 12) | Men |\n| --- | --- | --- |\n| Age (yr) | 59 ± 11 | 58 ± 11 |\n"
            "| P value | p < 0.05 |\n| Ratio a\\|b | 1.5 (0.9) | n/a |\n")


def doc(*sections, head=HEAD, note=NOTE):
    return head + "## Tables (structured)\n\n" + note + "".join(sections)


def long_table(number=2, rows=60):
    body = "".join(f"<tr><td>Subject {n:03d}</td><td>glucose {n * 1.5:.1f} mmol/L</td><td>insulin {n} pmol/L</td></tr>\n"
                   for n in range(rows))
    return (f"### Table {number}\n\n<table>\n<tr><th>Subject</th><th>Fasting glucose</th><th>Fasting insulin</th></tr>\n"
            f"{body}</table>\n\n")


def data_rows(text):
    return [line for line in text.splitlines() if re.match(r"\| Subject \d", line)]


# ---------- prepare: HTML and pipe tables become pipe rows ---------------------------------------------

def test_html_table_becomes_pipe_rows():
    prep = prepare(doc(T1), "markdown")
    assert prep.text == HEAD + T1_PIPES + "\n"
    assert prep.body_end == len(HEAD) and prep.text[:prep.body_end] == HEAD
    assert "Tables (structured)" not in prep.text and "Extracted from the PDF" not in prep.text
    (table,) = prep.tables
    assert (table.number, table.caption, table.rows, table.cols) == (1, "", 4, 3)
    assert prep.text[table.start:table.end] == T1_PIPES
    (seg,) = prep.segments
    assert (seg.kind, seg.number, seg.start, seg.end) == ("table", 1, table.start, table.end)


def test_merged_cells_header_rows_and_inner_tags():
    html = ("### Table 3\nTable 3. Lipids by <b>sex</b>\n<TABLE class=\"x\">\n"
            "<tr><th rowspan=\"2\">Variable</th><th colspan=\"2\">Women</th><th colspan='2'>Men</th></tr>\n"
            "<tr><th></th><th>VAT</th><th>SAT</th><th>VAT</th><th>SAT</th></tr>\n"
            "<tr><td>BMI<sup>a</sup></td><td>0.61<br>0.70</td><td><i>0.83</i></td><td>0.5</td><td>0.6</td>\n"
            "<tr><td>LDL&nbsp;C<td>1<td>2</tr>\n</TABLE>\nValues are r.\n")
    prep = prepare(doc(html), "markdown")
    assert prep.text[prep.body_end:] == (
        "### Table 3\nTable 3. Lipids by <b>sex</b>\n"
        "| Variable | Women |  | Men |\n|  | VAT | SAT | VAT | SAT |\n| --- | --- | --- | --- | --- |\n"
        "| BMIa | 0.61 0.70 | 0.83 | 0.5 | 0.6 |\n| LDL C | 1 | 2 |\nValues are r.\n\n")
    (table,) = prep.tables
    assert (table.number, table.caption, table.rows, table.cols) == (3, "Table 3. Lipids by <b>sex</b>", 4, 5)


def test_pipe_table_in_the_tables_section():
    src = ("### Table 1\nBaseline values\n\n| Group | n | Note |\n|:---|---:|---|\n| Keto \\| low | 12 | |\n"
           "|Control|11|x|\n\n### Table 2\n| only | data |\n| 1 | 2 |\n")
    prep = prepare(doc(src), "markdown")
    assert prep.text[prep.body_end:] == (
        "### Table 1\nBaseline values\n| Group | n | Note |\n| --- | --- | --- |\n| Keto \\| low | 12 |\n"
        "| Control | 11 | x |\n\n### Table 2\n| only | data |\n| 1 | 2 |\n\n")
    assert [(t.number, t.caption, t.rows, t.cols) for t in prep.tables] == [(1, "Baseline values", 3, 3), (2, "", 2, 2)]


def test_long_table_is_cut_at_row_ends_and_repeats_the_header():
    prep = prepare(doc(T1, long_table()), "markdown", window=700)
    pieces = [prep.text[s.start:s.end] for s in prep.segments if s.number == 2]
    assert len(pieces) >= 5 and all(len(p) <= 700 for p in pieces)
    top = "| Subject | Fasting glucose | Fasting insulin |\n| --- | --- | --- |\n"
    assert pieces[0].startswith("### Table 2\n" + top)
    assert all(p.startswith("### Table 2 (continued)\n" + top) for p in pieces[1:])
    assert all(p.endswith("|\n") and "<t" not in p for p in pieces)
    rows = [row for p in pieces for row in data_rows(p)]
    assert rows == [f"| Subject {n:03d} | glucose {n * 1.5:.1f} mmol/L | insulin {n} pmol/L |" for n in range(60)]
    table = prep.tables[1]
    assert (table.number, table.rows, table.cols) == (2, 61, 3)
    assert table.start == prep.segments[1].start and table.end == prep.segments[-1].end
    assert [s.start for s in prep.segments[2:]] == [s.end + 1 for s in prep.segments[1:-1]]  # one blank line apart


def test_a_row_longer_than_the_window_stays_whole():
    wide = "x" * 900
    src = f"### Table 1\n<table><tr><th>A</th></tr><tr><td>one</td></tr><tr><td>{wide}</td></tr><tr><td>two</td></tr></table>\n"
    prep = prepare(doc(src), "markdown", window=300)
    pieces = [prep.text[s.start:s.end] for s in prep.segments]
    assert len(pieces) == 3 and f"| {wide} |\n" in pieces[1] and len(pieces[1]) > 300
    assert all("| A |\n| --- |\n" in p for p in pieces)


def test_a_huge_header_is_not_repeated():
    wide = "h" * 400
    rows = "".join(f"<tr><td>row {n} {'y' * 80}</td></tr>" for n in range(8))
    prep = prepare(doc(f"### Table 1\n<table><tr><th>{wide}</th></tr>{rows}</table>\n"), "markdown", window=500)
    pieces = [prep.text[s.start:s.end] for s in prep.segments]
    assert len(pieces) >= 2 and wide in pieces[0]
    assert all(wide not in p and p.startswith("### Table 1 (continued)\n| row ") for p in pieces[1:])


@pytest.mark.parametrize("text, source", [
    (HEAD + "| a | b |\n|---|---|\n| 1 | 2 |\n", "markdown"),                       # a pipe table in the body is text
    (HEAD + "## Tables (structured)\n\n" + NOTE, "markdown"),                       # marker without tables
    (doc(T1), "ft-cache"),                                                           # only Markdown has the section
    (HEAD.replace("## Results", "### Table 1") + "<table><tr><td>x</td></tr></table>\n", "markdown"),  # no marker
    ("", "markdown"),
])
def test_text_without_a_tables_section_is_left_alone(text, source):
    prep = prepare(text, source)
    assert prep.text == text and prep.body_end == len(text) and prep.segments == () and prep.tables == ()
    out, passages, tables = build_passages(text, source)
    assert out == text and tables == () and all(p.kind == "text" and p.table is None for p in passages)
    assert [(p.section, p.start, p.end, p.text) for p in passages] == \
        [(p.section, p.start, p.end, p.text) for p in split_passages(text, source)]


def test_sections_without_a_table_and_empty_tables():
    src = ("### Table 1\n\nSee the supplement for this table.\n\n"
           "### Table 2\n\n<table>\n<tr><th></th></tr>\n</table>\n\n"
           "### Table 3\n\n" + "### Table 4\n<table><tr><td>kept</td></tr></table>\n")
    prep = prepare(doc(src), "markdown")
    assert prep.text[prep.body_end:] == "### Table 1\n\nSee the supplement for this table.\n\n### Table 4\n| kept |\n\n"
    assert [(s.kind, s.number) for s in prep.segments] == [("text", 1), ("table", 4)]
    assert [(t.number, t.rows, t.cols) for t in prep.tables] == [(4, 1, 1)]


@pytest.mark.parametrize("junk", [
    "<table>", "<table><tr><td>open cell", "<table></table>", "<table><tr></tr></table>", "<td>stray</td>",
    "<table><tr><td colspan='x'>a</td><td colspan='0'>b</td><td colspan='999999'>c</td></tr></table>",
    "<table><tr><td><table><tr><td>inner</td></tr></table></td></tr></table>", "|", "|||", "| --- |", "\x00<table",
    "<table><tr><td>&bogus; &#xZZ; &amp;</td></tr>", "<table" + "<tr>" * 500,
])
def test_broken_markup_never_raises(junk):
    text = doc(f"### Table 1\n{junk}\n### Table 2\n<table><tr><td>fine</td></tr></table>\n")
    out, passages, tables = build_passages(text, "markdown")
    assert tables[-1].number == 2 and out.endswith("### Table 2\n| fine |\n\n")
    assert all(p.text == out[p.start:p.end] and p.text.strip() for p in passages)


def test_build_passages_marks_table_passages():
    text = doc(T1, long_table(), "### Table 3\n\nNot a table.\n")
    out, passages, tables = build_passages(text, "markdown", window=700, overlap=50)
    assert all(p.text == out[p.start:p.end] for p in passages)
    kinds = [(p.kind, p.table, p.section) for p in passages]
    assert kinds[:3] == [("text", None, "Paper"), ("text", None, "Results"), ("table", 1, "Table 1")]
    assert kinds[-1] == ("text", None, "Table 3") and set(kinds[3:-1]) == {("table", 2, "Table 2")}
    assert [t.number for t in tables] == [1, 2]
    assert not any("<td" in p.text or "Tables (structured)" in p.text for p in passages)
    assert out.count("| Subject 0") == 60


# ---------- index ---------------------------------------------------------------------------------------

V1_SCHEMA = (
    """CREATE TABLE items (library TEXT NOT NULL, item_key TEXT NOT NULL, item_id INTEGER, item_type TEXT, title TEXT,
  creators TEXT, year INTEGER, date TEXT, doi TEXT, publication TEXT, abstract TEXT, collections TEXT, tags TEXT,
  date_added TEXT, modified TEXT, text_source TEXT, text_path TEXT, flags TEXT, signature TEXT, n_passages INTEGER,
  PRIMARY KEY (library, item_key))""",
    "CREATE TABLE passage_map (rowid INTEGER PRIMARY KEY, library TEXT NOT NULL, item_key TEXT NOT NULL)",
    """CREATE VIRTUAL TABLE passages USING fts5(title, section, body, library UNINDEXED, item_key UNINDEXED,
  start UNINDEXED, end UNINDEXED, tokenize='porter unicode61 remove_diacritics 2')""",
    "CREATE TABLE state (key TEXT PRIMARY KEY, value TEXT)",
    "INSERT INTO state VALUES ('last_sync', '2026-11-06T12:00:00Z')",
    "INSERT INTO items (library, item_key, title, modified, signature, n_passages) VALUES ('user', 'OLDITEM1', 'Old', 'm', 's', 1)",
    "INSERT INTO passage_map (rowid, library, item_key) VALUES (1, 'user', 'OLDITEM1')",
    "INSERT INTO passages (rowid, title, section, body, library, item_key, start, \"end\") "
    "VALUES (1, 'Old', '', 'stale words from version one', 'user', 'OLDITEM1', 0, 28)",
)


def make_library(tmp):
    z = ZoteroFixture(tmp / "Zotero")
    md = tmp / "md"
    md.mkdir()
    i = z.add_item("TABLES01", fields={"title": "Adiponectin and visceral fat", "DOI": "10.1000/tab.1", "date": "2020-00-00 2020"},
                   creators=[("Ada", "Lovelace", "author")])
    z.add_attachment(i, "PDFTAB01", ft_text="cache text that loses to markdown " * 10)
    (md / "doi_10.1000_tab.1.md").write_text(doc(T1, long_table(), "### Table 3\n| Marker | Level |\n|---|---|\n| leptin | high |\n"),
                                             encoding="utf-8")
    i = z.add_item("PLAIN001", fields={"title": "Glucose without tables", "DOI": "10.1000/plain.1", "date": "2021-00-00 2021"})
    z.add_attachment(i, "PDFPLN01", ft_text="Fasting glucose and insulin were measured in plasma. td tr th.\n\n" * 6)
    for n in range(12):
        i = z.add_item(f"FILL00{n:02d}", fields={"title": f"Filler {n}", "date": "2019-00-00 2019"})
        z.add_attachment(i, f"PDFFL0{n:02d}", ft_text=f"Unrelated filler text number {n} about myokines.\n\n" * 4)
    return z, md


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lib11")
    z, md = make_library(tmp)
    root = tmp / "pd"
    index = Index(root / "index.sqlite")
    rep = sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md))
    assert rep.done and rep.indexed == 14
    index.close()
    z.close()
    return root


def handlers(root):
    settings = Settings()
    specs = {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root)}
    return specs["zotero_search"].handler, specs["zotero_read"].handler, specs["zotero_status"].handler


def call(handler, **args):
    out = handler(args)
    assert isinstance(out, str)
    return json.loads(out)


def test_index_stores_kinds_and_the_table_list(lib):
    con = sqlite3.connect(lib / "index.sqlite")
    try:
        assert con.execute("SELECT value FROM state WHERE key = 'schema'").fetchone() == (str(SCHEMA_VERSION),)
        kinds = con.execute("SELECT kind, table_no, COUNT(*) FROM passage_map WHERE item_key = 'TABLES01' "
                            "GROUP BY kind, table_no ORDER BY table_no").fetchall()
        assert kinds[0][:2] == ("text", None) and [k[:2] for k in kinds[1:]] == [("table", 1), ("table", 2), ("table", 3)]
        assert dict((k[1], k[2]) for k in kinds[1:])[2] >= 2  # the long table needs several passages
        assert con.execute("SELECT COUNT(*) FROM passage_map WHERE kind != 'text' AND item_key != 'TABLES01'").fetchone() == (0,)
        rows = con.execute('SELECT number, caption, n_rows, n_cols, "end" - start FROM item_tables ORDER BY start').fetchall()
        assert [r[:4] for r in rows] == [(1, "", 4, 3), (2, "", 61, 3), (3, "", 2, 2)] and all(r[4] > 0 for r in rows)
        bodies = [r[0] for r in con.execute("SELECT body FROM passages WHERE item_key = 'TABLES01'")]
        assert not any("<td" in b or "<tr" in b for b in bodies)
    finally:
        con.close()
    index = Index(lib / "index.sqlite")
    try:
        counts = index.counts()
        assert counts["schema"] == SCHEMA_VERSION >= 2 and counts["tables"] == 3 and counts["items"] == 14
    finally:
        index.close()


def test_resync_replaces_and_removes_table_rows(tmp_path):
    z, md = make_library(tmp_path)
    index = Index(tmp_path / "pd" / "index.sqlite")
    try:
        corpus = MarkdownCorpus(md)
        assert sync(index, z.db_path, z.data_dir, corpus=corpus).indexed == 14
        (md / "doi_10.1000_tab.1.md").write_text(doc(T1) + "\nA new line, so the file size changes.\n", encoding="utf-8")
        assert sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md)).indexed == 1
        assert index.con.execute("SELECT number FROM item_tables").fetchall() == [(1,)]
        assert index.con.execute("SELECT COUNT(*) FROM passage_map WHERE kind = 'table'").fetchone() == (1,)
        z.trash(z.con.execute("SELECT itemID FROM items WHERE key = 'TABLES01'").fetchone()[0])
        assert sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md)).deleted == 1
        assert index.counts()["tables"] == 0
    finally:
        index.close()
        z.close()


def test_an_index_from_version_1_is_rebuilt_by_sync(tmp_path):
    z, md = make_library(tmp_path)
    root = tmp_path / "pd"
    root.mkdir()
    con = sqlite3.connect(root / "index.sqlite")
    for statement in V1_SCHEMA:
        con.execute(statement)
    con.commit()
    con.close()
    search, read, status = handlers(root)

    data = call(status)
    assert data["ready"] is False and data["index"]["schema"] == 1 and data["index"]["items"] == 1
    assert "zotero_sync" in data["hint"] and "older version" in data["hint"]
    for data in (call(search, query="stale words"), call(read, key="OLDITEM1")):
        assert data["ok"] is False and data["error"]["code"] == "index_outdated" and "zotero_sync" in data["error"]["hint"]
    con = sqlite3.connect(root / "index.sqlite")  # looking at an old index never changes its contents
    assert con.execute("SELECT COUNT(*) FROM passage_map").fetchone() == (1,)
    assert con.execute("SELECT value FROM state WHERE key = 'schema'").fetchone() is None
    con.close()

    ticks = iter(range(0, 10_000, 10))
    index = Index(root / "index.sqlite")
    try:
        assert index.schema_version() == 1
        rep = sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md), batch_items=5, budget_seconds=5,
                   clock=lambda: next(ticks))
        assert rep.done is False and rep.indexed == 5 and rep.remaining == 9
        assert any("rebuilt" in w for w in rep.warnings)
        assert index.schema_version() == SCHEMA_VERSION and index.get_state("last_sync") is None
        assert index.con.execute("SELECT COUNT(*) FROM items WHERE item_key = 'OLDITEM1'").fetchone() == (0,)
    finally:
        index.close()
    data = call(status)
    assert data["ready"] is True and "still being built" in data["hint"] and "zotero_sync" in data["hint"]
    assert call(search, query="stale words")["hits"] == []

    index = Index(root / "index.sqlite")
    try:
        rep = sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md))
        assert rep.done and rep.indexed == 9 and not any("rebuilt" in w for w in rep.warnings)
    finally:
        index.close()
        z.close()
    data = call(status)
    assert data["ready"] is True and data["index"]["items"] == 14 and data["index"]["tables"] == 3
    assert "still being built" not in (data["hint"] or "")
    assert call(search, query="leptin", in_tables=True)["hits"][0]["key"] == "TABLES01"


# ---------- zotero_search -------------------------------------------------------------------------------

def test_table_hits_say_kind_and_table_number(lib):
    search, _, _ = handlers(lib)
    data = call(search, query="leptin")
    (hit,) = data["hits"]
    assert hit["key"] == "TABLES01" and hit["match"] == "all"
    passage = hit["passages"][0]
    assert passage["kind"] == "table" and passage["table"] == 3 and passage["section"] == "Table 3"
    assert "«leptin»" in passage["snippet"] and "<td" not in passage["snippet"]
    data = call(search, query="adiponectin plasma")
    passage = next(h for h in data["hits"] if h["key"] == "TABLES01")["passages"][0]
    assert "kind" not in passage and "table" not in passage and passage["section"] == "Results"


def test_in_tables_limits_hits_and_coverage(lib):
    search, _, _ = handlers(lib)
    everywhere = call(search, query="fasting glucose insulin")
    assert {h["key"] for h in everywhere["hits"]} == {"TABLES01", "PLAIN001"}
    assert everywhere["coverage"]["matches_all"] == 2 and "in_tables" not in everywhere["coverage"]
    for flag in (True, "true", "TRUE", 1, "yes"):
        data = call(search, query="fasting glucose insulin", in_tables=flag)
        assert [h["key"] for h in data["hits"]] == ["TABLES01"]
        assert all(p["kind"] == "table" and p["table"] == 2 for p in data["hits"][0]["passages"])
        cov = data["coverage"]
        assert cov["matches_all"] == 1 and cov["matches_any"] == 1 and cov["in_tables"] is True
        assert "without in_tables" in cov["hint"]
    for flag in (False, "false", 0, "", None, "no"):
        assert len(call(search, query="fasting glucose insulin", in_tables=flag)["hits"]) == 2
    data = call(search, query="myokines", in_tables=True)
    assert data["hits"] == [] and data["coverage"]["verdict"] == "none" and data["coverage"]["in_tables"] is True
    data = call(search, query="glucose", in_tables="maybe")
    assert data["ok"] is False and data["error"]["code"] == "invalid_argument" and "in_tables" in data["error"]["message"]


def test_markup_words_are_not_indexed_for_tables(lib):
    search, _, _ = handlers(lib)
    assert [h["key"] for h in call(search, query="td tr th")["hits"]] == ["PLAIN001"]  # words in prose still count
    assert call(search, query="structured")["hits"] == [] and call(search, query="paraphrase")["hits"] == []


# ---------- zotero_read ---------------------------------------------------------------------------------

def test_mode_tables_lists_the_tables(lib):
    _, read, _ = handlers(lib)
    data = call(read, key="TABLES01", mode="tables")
    assert data["ok"] is True and data["mode"] == "tables" and data["total_tables"] == 3 and data["warnings"] == []
    assert [(t["table"], t["caption"], t["rows"], t["cols"]) for t in data["tables"]] == \
        [(1, None, 4, 3), (2, None, 61, 3), (3, None, 2, 2)]
    assert data["tables"][0]["chars"] == len(T1_PIPES) and data["tables"][1]["chars"] > 2000
    assert data["title"] == "Adiponectin and visceral fat" and data["citation"]["text"] and "text" not in data
    data = call(read, key="PLAIN001", mode="tables", query="glucose")
    assert data["ok"] is True and data["total_tables"] == 0 and data["tables"] == []
    assert any("no structured tables" in w for w in data["warnings"]) and any("query" in w for w in data["warnings"])


def test_mode_tables_returns_one_table(lib):
    _, read, _ = handlers(lib)
    data = call(read, key="TABLES01", mode="tables", table=1)
    assert data["text"] == T1_PIPES and data["next_offset"] is None and data["warnings"] == []
    assert data["table"] == {"table": 1, "caption": None, "rows": 4, "cols": 3, "chars": len(T1_PIPES)}
    assert data["total_chars"] == len(T1_PIPES) and data["mode"] == "tables" and data["citation"]["text"]
    assert call(read, key="TABLES01", mode="tables", table="3")["text"] == "### Table 3\n| Marker | Level |\n| --- | --- |\n| leptin | high |\n"
    data = call(read, key="TABLES01", mode="tables", table=9)
    assert data["ok"] is False and data["error"]["code"] == "not_found" and "mode=tables" in data["error"]["hint"]
    assert call(read, key="NOSUCH01", mode="tables")["error"]["code"] == "not_found"
    assert call(read, key="TABLES01", mode="table")["error"]["code"] == "invalid_argument"


def test_a_long_table_is_paged_in_whole_pieces(lib):
    _, read, _ = handlers(lib)
    pages = []
    offset = None
    for _ in range(10):
        args = {"key": "TABLES01", "mode": "tables", "table": 2, "max_chars": 2500}
        if offset is not None:
            args["offset"] = offset
        data = call(read, **args)
        assert data["ok"] is True and data["warnings"] == [] and len(data["text"]) <= 2500
        pages.append(data["text"])
        offset = data["next_offset"]
        if offset is None:
            break
    assert len(pages) >= 2 and pages[0].startswith("### Table 2\n| Subject | Fasting glucose | Fasting insulin |\n| --- |")
    assert all(p.startswith("### Table 2 (continued)\n| Subject | Fasting glucose |") for p in pages[1:])
    assert [row[:13] for p in pages for row in data_rows(p)] == [f"| Subject {n:03d}" for n in range(60)]
    whole = call(read, key="TABLES01", mode="tables", table=2, max_chars=12000)
    assert whole["next_offset"] is None and len(data_rows(whole["text"])) == 60 and "\n\n### Table 2 (continued)\n" in whole["text"]
    stray = call(read, key="TABLES01", mode="tables", table=2, offset=3)
    assert stray["offset"] == whole["offset"] and any("outside table 2" in w for w in stray["warnings"])


def test_a_small_max_chars_cuts_at_a_row_end(lib):
    _, read, _ = handlers(lib)
    rows, offset, warned = [], None, False
    for _ in range(40):
        args = {"key": "TABLES01", "mode": "tables", "table": 2, "max_chars": 600}
        if offset is not None:
            args["offset"] = offset
        data = call(read, **args)
        assert 0 < len(data["text"]) <= 2000 and data["text"].endswith("|\n")
        warned = warned or any("max_chars is smaller" in w for w in data["warnings"])
        rows += data_rows(data["text"])
        offset = data["next_offset"]
        if offset is None:
            break
    assert offset is None and warned
    assert [row[:13] for row in rows] == [f"| Subject {n:03d}" for n in range(60)]


def test_text_mode_reads_tables_as_pipe_rows(lib):
    _, read, _ = handlers(lib)
    data = call(read, key="TABLES01", max_chars=12000, table=2)
    assert data["mode"] == "text" and data["tables_count"] == 3 and data["next_offset"] is None
    assert any("table is only used" in w for w in data["warnings"])
    text = data["text"]
    assert text.startswith(HEAD) and T1_PIPES in text and "<t" not in text and "Tables (structured)" not in text
    assert len(data_rows(text)) == 60 and text.rstrip().endswith("| leptin | high |")
    assert data["total_chars"] == len(text)
    data = call(read, key="TABLES01", query="leptin", max_chars=300)
    assert data["section"] == "Table 3" and data["text"].startswith("### Table 3\n| Marker | Level |")
    assert call(read, key="PLAIN001")["tables_count"] == 0


# ---------- registration and skill ----------------------------------------------------------------------

def test_schemas_and_descriptions(plugin_module, fake_ctx):
    plugin_module.register(fake_ctx)
    read = fake_ctx.tools["zotero_read"]["schema"]
    props = read["parameters"]["properties"]
    assert props["mode"]["enum"] == ["text", "annotations", "tables"] and "tables" in props["mode"]["description"]
    assert props["table"]["type"] == "integer" and read["parameters"]["required"] == ["key"]
    assert "tables" in read["description"][:80] and "mode=tables" in read["description"] and len(read["description"]) <= 400
    search = fake_ctx.tools["zotero_search"]["schema"]
    assert search["parameters"]["properties"]["in_tables"]["type"] == "boolean"
    assert "in_tables" in search["description"] and len(search["description"]) <= 400


def test_skill_explains_the_table_route():
    text = (ROOT / "skills" / "zotero-library" / "SKILL.md").read_text(encoding="utf-8")
    assert re.search(r"^version: 0\.2\.0$", text, re.M) and len(text) <= 4000
    for word in ("`in_tables`", "`table`", "`tables`", "`kind: table`", "`index_outdated`"):
        assert word in text
```
<!-- /file -->

## Live check (Gábor, on the Mac; not for the executor)

After the commit. Paste the outputs into `tasks/11-report.md` under `## Live check`.

**1. Rebuild and direct checks.** In a terminal:

```bash
cd ~/Developer/hermes-zotero
time hermes zotero sync
hermes gateway restart
```

The sync prints one warning ("…is being rebuilt from scratch") and re-indexes everything once. Expected: about the same time as the first full sync on 6 Nov (70 s) plus the time to empty the old index; the last line names about 19,290 items and about 10,300 tables. If it takes longer than 10 minutes, stop and tell the reviewer.

Then:

```bash
cd ~/Developer/hermes-zotero && .venv/bin/python - <<'EOF'
import json, time
from pathlib import Path
from zotcore import tools
from zotcore.settings import Settings

root = Path.home() / ".hermes" / "plugin-data" / "hermes-zotero"
settings = Settings(libraries=("user", "4805701"))
h = {t.name: t.handler for t in tools.tool_specs(lambda: settings, data_root=lambda: root)}
st = json.loads(h["zotero_status"]({}))
ix = st["index"]
print("status:", st["ready"], "| hint:", st["hint"], "| schema", ix["schema"], "| items", ix["items"],
      "| passages", ix["passages"], "| tables", ix["tables"])
for q in ["LDL cholesterol baseline", "HbA1c", "visceral adipose tissue women men", "hazard ratio", "td tr"]:
    for flag in (False, True):
        t0 = time.time()
        d = json.loads(h["zotero_search"]({"query": q, "in_tables": flag, "limit": 5}))
        c = d["coverage"]
        kinds = [p.get("kind", "text") for hit in d["hits"] for p in hit["passages"]]
        print(f"{q} | in_tables={flag} | all {c['matches_all']} | any {c['matches_any']} | {c['verdict']} | "
              f"table passages {kinds.count('table')}/{len(kinds)} | {time.time() - t0:.2f} s")
d = json.loads(h["zotero_search"]({"query": "LDL cholesterol baseline", "in_tables": True, "limit": 3}))
hit = d["hits"][0]
p = hit["passages"][0]
print("first hit:", hit["key"], "|", hit["title"][:70], "| table", p["table"])
lst = json.loads(h["zotero_read"]({"key": hit["key"], "mode": "tables"}))
print("tables in it:", lst["total_tables"], lst["tables"][:5])
one = json.loads(h["zotero_read"]({"key": hit["key"], "mode": "tables", "table": p["table"], "max_chars": 3000}))
print("next_offset:", one["next_offset"], "| warnings:", one["warnings"], "| citation:", one["citation"]["text"][:80])
print(one["text"][:1200])
EOF
```

| Line | Expected |
| --- | --- |
| status | `True`, hint `None` (or "Zotero has changed…"), schema 2, items about 19,290, passages about 1,062,000 (was 1,067,137), tables about 10,300 |
| each query with `in_tables=False` | counts as before this task or slightly lower; a mix of text and table passages |
| each query with `in_tables=True` | lower counts; every passage is a table passage |
| `td tr` | far fewer matches than before (the tags are no longer indexed); `in_tables=True`: 0 or a handful |
| timings | each under about 1.5 s |
| the table | starts with `### Table N`, then pipe rows; no `<td>`; a citation line |

**2. Through Hermes.**

```bash
hermes -z "In my Zotero library, find a paper with a table of baseline LDL cholesterol values and quote two rows of that table with the citation."
```

Expected: `zotero_search` (ideally with `in_tables`), then `zotero_read` with `mode` = `tables`; rows quoted as they stand in the table. Paste the tool calls with their arguments (from `~/.hermes/state.db`, as in task 07) and the total time.

## Out of scope

The `ocr` flag and front matter (task 12), the damaged-text flag (task 13), README, the corpus guide and the version number (task 14). Tables in a paper's body, and tables in Zotero's own text cache, stay plain text.
