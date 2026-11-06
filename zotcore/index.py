"""The plugin's own full-text index (SQLite FTS5) and the incremental sync that fills it."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .textsource import TextResult, choose_text, split_passages, text_signature
from .zdb import list_items, libraries as zotero_libraries, load_items, open_snapshot

CHUNK = 500
MAX_ITEM_WARNINGS = 20

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS items (library TEXT NOT NULL, item_key TEXT NOT NULL, item_id INTEGER, item_type TEXT, title TEXT,
  creators TEXT, year INTEGER, date TEXT, doi TEXT, publication TEXT, abstract TEXT, collections TEXT, tags TEXT, date_added TEXT,
  modified TEXT, text_source TEXT, text_path TEXT, flags TEXT, signature TEXT, n_passages INTEGER, PRIMARY KEY (library, item_key))""",
    "CREATE INDEX IF NOT EXISTS items_doi ON items(doi)",
    "CREATE TABLE IF NOT EXISTS passage_map (rowid INTEGER PRIMARY KEY, library TEXT NOT NULL, item_key TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS passage_map_item ON passage_map(library, item_key)",
    """CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(title, section, body, library UNINDEXED, item_key UNINDEXED,
  start UNINDEXED, end UNINDEXED, tokenize='porter unicode61 remove_diacritics 2')""",
    "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)",
)


@dataclass(frozen=True)
class SyncReport:
    """Outcome of one sync run."""

    examined: int
    indexed: int
    deleted: int
    remaining: int
    done: bool
    seconds: float
    warnings: tuple[str, ...]
    read_errors: int = 0


def _read_error_summary(read_errors: int) -> list[str]:
    if read_errors <= 1:
        return []
    more = "; only the first 20 are listed" if read_errors > MAX_ITEM_WARNINGS else ""
    return [f"{read_errors} items could not be read{more}"]


class Index:
    """SQLite database holding item metadata and FTS5 passages."""

    def __init__(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con: sqlite3.Connection = sqlite3.connect(str(path), isolation_level=None)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=NORMAL")
        for statement in SCHEMA:
            self.con.execute(statement)

    def close(self) -> None:
        """Close the database connection."""
        self.con.close()

    @contextmanager
    def transaction(self):
        """BEGIN ... COMMIT; ROLLBACK on any exception."""
        self.con.execute("BEGIN")
        try:
            yield self
        except BaseException:
            self.con.execute("ROLLBACK")
            raise
        else:
            self.con.execute("COMMIT")

    def indexed(self, library: str) -> dict[str, tuple[str, str]]:
        """item_key -> (modified, signature) for every indexed item of a library."""
        rows = self.con.execute("SELECT item_key, modified, signature FROM items WHERE library = ?", (library,))
        return {key: (modified, signature) for key, modified, signature in rows}

    def libraries(self) -> list[str]:
        """Libraries present in the index."""
        return [r[0] for r in self.con.execute("SELECT DISTINCT library FROM items ORDER BY library")]

    def _drop_passages(self, library: str, key: str) -> None:
        rowids = [r[0] for r in self.con.execute(
            "SELECT rowid FROM passage_map WHERE library = ? AND item_key = ?", (library, key))]
        for start in range(0, len(rowids), CHUNK):
            chunk = rowids[start:start + CHUNK]
            self.con.execute(f"DELETE FROM passages WHERE rowid IN ({','.join('?' * len(chunk))})", chunk)
        self.con.execute("DELETE FROM passage_map WHERE library = ? AND item_key = ?", (library, key))

    def upsert(self, item, text, passages: Sequence) -> None:
        """Replace the item row and all of its passages."""
        self._drop_passages(item.library, item.key)
        self.con.execute(
            "INSERT OR REPLACE INTO items (library, item_key, item_id, item_type, title, creators, year, date, doi, "
            "publication, abstract, collections, tags, date_added, modified, text_source, text_path, flags, "
            "signature, n_passages) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (item.library, item.key, item.item_id, item.item_type, item.title, json.dumps(list(item.creators)),
             item.year, item.date, item.doi, item.publication, item.abstract, json.dumps(list(item.collections)),
             json.dumps(list(item.tags)), item.date_added, item.modified, text.source, text.path,
             json.dumps(list(text.flags)), text.signature, len(passages)))
        for p in passages:
            rowid = self.con.execute("INSERT INTO passage_map (library, item_key) VALUES (?, ?)",
                                     (item.library, item.key)).lastrowid
            self.con.execute(
                'INSERT INTO passages (rowid, title, section, body, library, item_key, start, "end") '
                "VALUES (?,?,?,?,?,?,?,?)",
                (rowid, item.title, p.section, p.text, item.library, item.key, p.start, p.end))

    def delete(self, library: str, keys: Iterable[str]) -> int:
        """Remove items and their passages; returns the number of item rows removed."""
        removed = 0
        for key in keys:
            self._drop_passages(library, key)
            removed += self.con.execute("DELETE FROM items WHERE library = ? AND item_key = ?",
                                        (library, key)).rowcount
        return removed

    def get_state(self, key: str, default=None):
        """Read a state value."""
        row = self.con.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return default if row is None else row[0]

    def set_state(self, key: str, value) -> None:
        """Write a state value."""
        self.con.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)", (key, value))

    def counts(self) -> dict:
        """Summary of what the index holds."""
        con = self.con
        flags: dict[str, int] = {}
        for (raw,) in con.execute("SELECT flags FROM items WHERE flags IS NOT NULL AND flags != '[]'"):
            for flag in json.loads(raw):
                flags[flag] = flags.get(flag, 0) + 1
        return {
            "items": con.execute("SELECT COUNT(*) FROM items").fetchone()[0],
            "passages": con.execute("SELECT COUNT(*) FROM passage_map").fetchone()[0],
            "libraries": dict(con.execute("SELECT library, COUNT(*) FROM items GROUP BY library ORDER BY library")),
            "by_source": dict(con.execute("SELECT text_source, COUNT(*) FROM items GROUP BY text_source")),
            "flags": flags,
            "last_sync": self.get_state("last_sync"),
        }


def sync(index: Index, snapshot_path, data_dir, *, libraries: Sequence[str] = ("user",), corpus=None,
         batch_items: int = 200, budget_seconds: float | None = None, clock: Callable[[], float] = time.monotonic,
         progress: Callable[[int, int], None] | None = None) -> SyncReport:
    """Bring the index in line with a snapshot. Safe to interrupt; the next run resumes."""
    t0 = clock()
    warnings: list[str] = []
    con = open_snapshot(snapshot_path)
    try:
        known = zotero_libraries(con)
        wanted: list[str] = []
        for name in libraries:
            if name in wanted:
                continue
            if name not in known:
                warnings.append(f"library {name} not found in Zotero; skipped")
                continue
            wanted.append(name)
        refs = list_items(con, wanted)
        total = len(refs)
        have = {name: index.indexed(name) for name in wanted}

        deleted = 0
        live = {(r.library, r.key) for r in refs}
        with index.transaction():
            for name in index.libraries():
                if name not in wanted:
                    deleted += index.delete(name, list(index.indexed(name)))
            for name in wanted:
                gone = [key for key in have[name] if (name, key) not in live]
                deleted += index.delete(name, gone)
                for key in gone:
                    del have[name][key]

        examined = indexed = read_errors = 0
        for start in range(0, total, batch_items):
            batch = refs[start:start + batch_items]
            items = load_items(con, [r.item_id for r in batch])
            with index.transaction():
                for item in items:
                    signature = text_signature(item, data_dir, corpus)
                    if have[item.library].get(item.key) == (item.modified, signature):
                        continue
                    try:
                        text = choose_text(item, data_dir, corpus)
                    except OSError as e:
                        read_errors += 1
                        if read_errors <= MAX_ITEM_WARNINGS:
                            warnings.append(f"item {item.key}: could not read text ({e}); "
                                            "indexed title and abstract only")
                        text = TextResult("metadata", "\n\n".join(p for p in (item.title, item.abstract) if p),
                                          None, ("body_not_read", "read_error"), signature)
                    index.upsert(item, text, split_passages(text.text, text.source))
                    indexed += 1
            examined += len(batch)
            if progress is not None:
                progress(examined, total)
            if budget_seconds is not None and examined < total:
                now = clock()
                if now - t0 >= budget_seconds:
                    return SyncReport(examined, indexed, deleted, total - examined, False, now - t0,
                                      tuple(warnings + _read_error_summary(read_errors)), read_errors)

        index.set_state("last_sync", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        return SyncReport(examined, indexed, deleted, 0, True, clock() - t0,
                          tuple(warnings + _read_error_summary(read_errors)), read_errors)
    finally:
        con.close()
