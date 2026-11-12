"""Read-only search and reading over the local index (standard library only)."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from pathlib import Path

from .index import SCHEMA_VERSION
from .zdb import normalize_doi

STOPWORDS = frozenset(
    "a an the of on in and or to for with by at from as is are was were be been it its this that these those "
    "what which who how does do did vs versus about into than".split())
MAX_TERMS = 12
POOL = 200                 # top passages examined before grouping them by item
SNIPPET_TOKENS = 24
MAX_SEARCH_CHARS = 12000   # cap on the whole JSON answer of zotero_search
MAX_COLLECTIONS = 3        # collection paths shown per hit
MAX_TABLES_LISTED = 100    # tables listed by zotero_read mode=tables
MAX_CAPTION_CHARS = 160
BM25 = "bm25(passages, 2.0, 1.0, 1.0)"   # title counts double; columns are title, section, body

_JOIN = "FROM passages p JOIN passage_map m ON m.rowid = p.rowid"
_SCOPE_JOIN = " JOIN temp.scope s ON s.library = m.library AND s.item_key = m.item_key"
_TABLES_ONLY = " AND m.kind = 'table'"
OUTDATED_HINT = ("Call zotero_sync and repeat it until it reports done: true (a one-time rebuild), "
                 "or ask the user to run `hermes zotero sync` in a terminal.")


class SearchError(Exception):
    """A problem the tools report as a structured error."""

    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


def open_index(path) -> sqlite3.Connection:
    """Open the index read-only; never creates it."""
    p = Path(path)
    if not p.exists():
        raise SearchError("no_index", "The Zotero index has not been built yet.",
                          "Run `hermes zotero sync` in a terminal, then try again.")
    con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        version = _state(con, "schema")
    except sqlite3.Error:
        version = None
    if version != str(SCHEMA_VERSION):
        con.close()
        raise SearchError("index_outdated", "The Zotero index was built by an older version of the plugin.",
                          OUTDATED_HINT)
    return con


def query_terms(query) -> tuple[list[str], bool]:
    """Search terms from free text, and whether some were dropped for the MAX_TERMS limit."""
    tokens = [t.lower() for t in re.findall(r"[^\W_]+", query or "")]
    kept = [t for t in tokens if t not in STOPWORDS] or tokens
    unique = list(dict.fromkeys(kept))
    return unique[:MAX_TERMS], len(unique) > MAX_TERMS


def _all_expr(terms: list[str]) -> str:
    return " ".join(f'"{t}"' for t in terms)


def _any_expr(terms: list[str]) -> str:
    return " OR ".join(f'"{t}"' for t in terms)


def _state(con: sqlite3.Connection, key: str):
    row = con.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _collection_match(paths: list[str], wanted: str) -> bool:
    w = wanted.casefold()
    for path in paths:
        p = path.casefold()
        if p == w or p.startswith(w + " / ") or p.split(" / ")[-1] == w:
            return True
    return False


def _build_scope(con, library, collection, year_from, year_to, tag=None) -> bool:
    """Fill temp.scope from the filters; return True when the scope is empty."""
    sql = "SELECT library, item_key, collections, tags FROM items WHERE 1=1"
    params: list = []
    if library is not None:
        sql += " AND library = ?"
        params.append(library)
    if year_from is not None:
        sql += " AND year >= ?"
        params.append(year_from)
    if year_to is not None:
        sql += " AND year <= ?"
        params.append(year_to)
    con.execute("CREATE TEMP TABLE IF NOT EXISTS scope (library TEXT, item_key TEXT, PRIMARY KEY (library, item_key))")
    con.execute("DELETE FROM temp.scope")
    wanted_tag = None if tag is None else tag.casefold()
    rows = []
    for lib, key, cols, tags in con.execute(sql, params).fetchall():
        if collection is not None and not _collection_match(json.loads(cols or "[]"), collection):
            continue
        if wanted_tag is not None and wanted_tag not in (t.casefold() for t in json.loads(tags or "[]")):
            continue
        rows.append((lib, key))
    con.executemany("INSERT INTO temp.scope VALUES (?, ?)", rows)
    return not rows


def _item_rows(con, pairs) -> dict:
    out = {}
    for lib, key in pairs:
        row = con.execute("SELECT title, creators, year, doi, collections, text_source, flags FROM items "
                          "WHERE library = ? AND item_key = ?", (lib, key)).fetchone()
        if row:
            out[(lib, key)] = row
    return out


def _hit(lib: str, key: str, row, match: str, passages: list[dict]) -> dict:
    title, creators, year, doi, collections, text_source, flags = row
    creators = json.loads(creators or "[]")
    hit = {"key": key, "library": lib, "title": title,
           "first_author": creators[0] if creators else "", "n_authors": len(creators),
           "year": year, "doi": doi or None,
           "collections": json.loads(collections or "[]")[:MAX_COLLECTIONS],
           "text_source": text_source, "match": match, "passages": passages}
    flag_list = json.loads(flags or "[]")
    if flag_list:
        hit["flags"] = flag_list
    return hit


def _find_hits(con, terms, scoped, limit, in_tables=False) -> list[dict]:
    per_item = 2 if limit <= 10 else 1
    slots: dict = {}   # (lib, key) -> [pass, passages]
    sql = (f"SELECT m.library, m.item_key, p.start, CASE WHEN p.section = p.title THEN '' ELSE p.section END, "
           f"snippet(passages, 2, '«', '»', '…', {SNIPPET_TOKENS}), m.kind, m.table_no "
           f"{_JOIN}{_SCOPE_JOIN if scoped else ''} "
           f"WHERE passages MATCH ?{_TABLES_ONLY if in_tables else ''} ORDER BY {BM25} LIMIT ?")
    passes = [("all", _all_expr(terms))]
    if len(terms) > 1:
        passes.append(("any", _any_expr(terms)))
    for name, expr in passes:
        if len(slots) >= limit:
            break
        for lib, key, start, section, snippet, kind, table_no in con.execute(sql, (expr, max(POOL, limit * 20))):
            slot = slots.get((lib, key))
            if slot is None:
                if len(slots) >= limit:
                    continue
                slot = slots[(lib, key)] = [name, []]
            if slot[0] != name or len(slot[1]) >= per_item:
                continue
            passage = {"offset": start, "snippet": snippet}
            if section:
                passage["section"] = section
            if kind == "table":
                passage["kind"] = "table"
                passage["table"] = table_no
            slot[1].append(passage)
    rows = _item_rows(con, slots)
    return [_hit(lib, key, rows[(lib, key)], name, passages)
            for (lib, key), (name, passages) in slots.items() if (lib, key) in rows]


def _coverage(con, terms, scoped, settings, this_year, in_tables=False) -> dict:
    join = _JOIN + (_SCOPE_JOIN if scoped else "")
    only = _TABLES_ONLY if in_tables else ""
    any_n = con.execute(f"SELECT COUNT(*) FROM (SELECT DISTINCT m.library, m.item_key {join} "
                        f"WHERE passages MATCH ?{only})", (_any_expr(terms),)).fetchone()[0]
    all_n, recent, newest = con.execute(
        f"SELECT COUNT(*), SUM(i.year >= ?), MAX(i.year) FROM (SELECT DISTINCT m.library, m.item_key {join} "
        f"WHERE passages MATCH ?{only}) d JOIN items i ON i.library = d.library AND i.item_key = d.item_key",
        (this_year - settings.coverage_recent_years + 1, _all_expr(terms))).fetchone()
    recent = recent or 0
    if all_n == 0:
        verdict = "none"
    elif all_n >= settings.coverage_strong_min and recent >= settings.coverage_recent_min:
        verdict = "strong"
    else:
        verdict = "thin"
    cov = {"matches_all": all_n, "matches_any": any_n, "recent": recent,
           "recent_years": settings.coverage_recent_years, "newest_year": newest, "verdict": verdict}
    if in_tables:
        cov["in_tables"] = True
        cov["hint"] = ("Counts cover table cells only. Judge what the library holds on a topic from a search "
                       "without in_tables.")
    elif all_n == 0 and any_n > 0 and len(terms) > 1:
        cov["hint"] = "No passage contains every term; retry with fewer or broader terms before using the web."
    return cov


def best_offset(con, library: str, key: str, terms: list[str]) -> int | None:
    """Start offset of the item's passage that best matches the terms, or None."""
    if not terms:
        return None
    lo, hi = con.execute("SELECT MIN(rowid), MAX(rowid) FROM passage_map WHERE library = ? AND item_key = ?",
                         (library, key)).fetchone()
    if lo is None:
        return None
    sql = (f"SELECT p.start {_JOIN} WHERE passages MATCH ? AND p.rowid BETWEEN ? AND ? "
           f"AND m.library = ? AND m.item_key = ? ORDER BY {BM25} LIMIT 1")
    exprs = [_all_expr(terms)] + ([_any_expr(terms)] if len(terms) > 1 else [])
    for expr in exprs:
        row = con.execute(sql, (expr, lo, hi, library, key)).fetchone()
        if row:
            return row[0]
    return None


def read_window(con, library: str, key: str, offset: int, max_chars: int) -> tuple[str, int, int, str]:
    """Text from offset (at most max_chars), end position, total length and first section."""
    spans = con.execute('SELECT m.rowid, p.start, p."end" FROM passage_map m JOIN passages p ON p.rowid = m.rowid '
                        "WHERE m.library = ? AND m.item_key = ? ORDER BY m.rowid", (library, key)).fetchall()
    total = max((s[2] for s in spans), default=0)
    limit = offset + max_chars
    cursor = offset
    parts: list[str] = []
    section = ""
    first = True
    for rowid, start, end in spans:
        if end <= offset or start >= limit:
            continue
        if end <= cursor:
            continue
        sec, body = con.execute("SELECT section, body FROM passages WHERE rowid = ?", (rowid,)).fetchone()
        if first:
            section, first = sec or "", False
        if start > cursor:
            parts.append("\n")
            cursor = start
        stop = min(end, limit)
        parts.append(body[cursor - start:stop - start])
        cursor = stop
        if cursor >= limit:
            break
    return "".join(parts), cursor, total, section


def find_item(con, key, library=None) -> tuple[str, str]:
    """Resolve an item key (and optional library) to (library, key)."""
    k = (key or "").strip().upper()
    if not k:
        raise SearchError("invalid_argument", "key is required")
    libs = sorted(r[0] for r in con.execute("SELECT library FROM items WHERE item_key = ?", (k,)))
    if library is not None:
        libs = [lib for lib in libs if lib == library]
    if not libs:
        raise SearchError("not_found", f"no item with key {k} in the index",
                          "Use a key from zotero_search results; run `hermes zotero sync` if the paper is new.")
    if len(libs) > 1:
        raise SearchError("ambiguous", f"key {k} exists in libraries {', '.join(libs)}", "Pass library= as well.")
    return libs[0], k


def item_info(con, library: str, key: str) -> dict:
    """Metadata of one indexed item (the keys zotero_read returns before the text fields)."""
    title, creators, year, doi, publication, text_source, flags = con.execute(
        "SELECT title, creators, year, doi, publication, text_source, flags FROM items "
        "WHERE library = ? AND item_key = ?", (library, key)).fetchone()
    creators = json.loads(creators or "[]")
    return {"key": key, "library": library, "title": title, "creators": creators[:3], "n_authors": len(creators),
            "year": year, "doi": doi or None, "publication": publication or None, "text_source": text_source,
            "flags": json.loads(flags or "[]")}


def _table_rows(con, library: str, key: str) -> list[tuple]:
    return con.execute('SELECT number, caption, n_rows, n_cols, start, "end" FROM item_tables '
                       "WHERE library = ? AND item_key = ? ORDER BY start", (library, key)).fetchall()


def _table_entry(row) -> dict:
    number, caption, n_rows, n_cols, start, end = row
    caption = caption or ""
    if len(caption) > MAX_CAPTION_CHARS:
        caption = caption[:MAX_CAPTION_CHARS - 1].rstrip() + "…"
    return {"table": number, "caption": caption or None, "rows": n_rows, "cols": n_cols, "chars": end - start}


def list_tables(con, *, key, library=None) -> dict:
    """The structured tables of one item: number, caption, size."""
    lib, k = find_item(con, key, library)
    rows = _table_rows(con, lib, k)
    warnings: list[str] = []
    if not rows:
        warnings.append("this paper has no structured tables in the index; "
                        "read the text instead (mode=text with a query)")
    if len(rows) > MAX_TABLES_LISTED:
        warnings.append(f"only the first {MAX_TABLES_LISTED} tables are listed")
    return {**item_info(con, lib, k), "total_tables": len(rows),
            "tables": [_table_entry(r) for r in rows[:MAX_TABLES_LISTED]], "warnings": warnings}


def read_table(con, *, key, table: int, library=None, offset=None, max_chars: int) -> dict:
    """One structured table as pipe rows: whole pieces while they fit max_chars."""
    lib, k = find_item(con, key, library)
    rows = [r for r in _table_rows(con, lib, k) if r[0] == table]
    if not rows:
        raise SearchError("not_found", f"this paper has no table {table} in the index",
                          "Call zotero_read with mode=tables and no table to list the tables.")
    warnings: list[str] = []
    if len(rows) > 1:
        warnings.append(f"{len(rows)} tables are numbered {table}; this is the first")
    start, end = rows[0][4], rows[0][5]
    pos = start
    if offset is not None:
        if start <= offset < end:
            pos = offset
        else:
            warnings.append(f"offset {offset} is outside table {table} ({start}-{end}); showing its start")
    pieces = con.execute(
        'SELECT p.start, p."end", p.body FROM passage_map m JOIN passages p ON p.rowid = m.rowid '
        "WHERE m.library = ? AND m.item_key = ? AND m.kind = 'table' AND p.start >= ? AND p.\"end\" <= ? "
        "ORDER BY p.start", (lib, k, start, end)).fetchall()
    parts: list[str] = []
    used = 0
    cursor = pos
    for p_start, p_end, body in pieces:
        if p_end <= pos:
            continue
        piece = body[max(pos - p_start, 0):]
        if used + len(piece) > max_chars:
            if not parts:   # one piece is larger than the limit: cut it at a row end
                cut = piece.rfind("\n", 0, max_chars) + 1 or max_chars
                parts.append(piece[:cut])
                cursor = max(pos, p_start) + cut
                warnings.append("max_chars is smaller than one piece of this table, so the piece was cut; "
                                "the next page starts without the header rows")
            break
        parts.append(piece)
        used += len(piece) + 1
        cursor = p_end
    return {**item_info(con, lib, k), "table": _table_entry(rows[0]), "total_chars": end - start, "offset": pos,
            "next_offset": None if cursor >= end else (cursor if cursor > pos else None),
            "text": "\n".join(parts), "warnings": warnings}


def read_item(con, *, key, library=None, query=None, offset=None, max_chars: int) -> dict:
    """Return a bounded piece of one item's text."""
    lib, k = find_item(con, key, library)
    warnings: list[str] = []
    if offset is not None:
        pos = offset
        if query:
            warnings.append("offset given, so query was not used to position the passage")
    elif query:
        found = best_offset(con, lib, k, query_terms(query)[0])
        if found is None:
            warnings.append("query terms not found in this item; showing the start")
            found = 0
        pos = found
    else:
        pos = 0
    text, end, total, section = read_window(con, lib, k, pos, max_chars)
    if total > 0 and pos >= total:
        warnings.append(f"offset {pos} is past the end of the text ({total} characters)")
    return {**item_info(con, lib, k), "total_chars": total, "offset": pos,
            "next_offset": None if end >= total else end, "section": section or None,
            "text": text, "tables_count": len(_table_rows(con, lib, k)), "warnings": warnings}


def _doi_check(con, doi, terms) -> dict:
    value = normalize_doi(doi)
    if not value.startswith("10.") or "/" not in value:
        raise SearchError("invalid_argument", f"not a DOI: {doi}", "Pass a DOI such as 10.1038/nature12345.")
    rows = con.execute("SELECT library, item_key FROM items WHERE doi = ? ORDER BY library, item_key",
                       (value,)).fetchall()
    details = _item_rows(con, rows)
    items = []
    for lib, key in rows:
        offset = best_offset(con, lib, key, terms) or 0
        text = read_window(con, lib, key, offset, 300)[0].strip()
        items.append(_hit(lib, key, details[(lib, key)], "doi", [{"offset": offset, "snippet": text}]))
    return {"doi": value, "held": bool(items), "items": items}


def search(con, settings, *, query=None, doi=None, library=None, collection=None, year_from=None,
           year_to=None, limit=10, this_year=None, tag=None, in_tables=False) -> dict:
    """Search the index; see the task spec for the result layout."""
    terms, truncated = query_terms(query)
    if not terms and not doi:
        raise SearchError("invalid_argument", "query is empty", "Pass a few keywords, or doi= to check one paper.")
    warnings: list[str] = []
    if truncated:
        warnings.append(f"only the first {MAX_TERMS} query terms were used")
    result: dict = {"query": query, "terms": terms}
    if doi:
        result["doi_check"] = _doi_check(con, doi, terms)
    scoped = any(v is not None for v in (library, collection, year_from, year_to, tag))
    if scoped and _build_scope(con, library, collection, year_from, year_to, tag):
        warnings.append("no indexed items match the filters")
    if terms:
        result["hits"] = _find_hits(con, terms, scoped, limit, in_tables)
        result["coverage"] = _coverage(con, terms, scoped, settings, this_year or date.today().year, in_tables)
    else:
        result["hits"] = []
        result["coverage"] = None
    result["index_last_sync"] = _state(con, "last_sync")
    result["warnings"] = warnings
    return result
