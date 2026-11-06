"""The user's annotations and child notes, read from the current snapshot (standard library only; read-only)."""
from __future__ import annotations

import html as html_lib
import re
import sqlite3
from pathlib import Path

from .zdb import libraries as zotero_libraries, open_snapshot

TYPE_NAMES = {1: "highlight", 2: "note", 3: "image", 4: "ink", 5: "underline", 6: "text"}

_BREAKS = re.compile(r"<br\s*/?>|</(?:p|div|li|h[1-6]|tr|blockquote|pre)>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")


def snapshot_db(data_root) -> Path:
    """Path of the current snapshot's database."""
    return Path(data_root) / "snapshot" / "current" / "zotero.sqlite"


def open_current_snapshot(data_root) -> sqlite3.Connection | None:
    """Open the current snapshot read-only, or None when there is none."""
    path = snapshot_db(data_root)
    if not path.exists():
        return None
    return open_snapshot(path)


def note_text(html: str | None) -> str:
    """Plain text of a Zotero note's HTML; paragraphs become lines."""
    text = _BREAKS.sub("\n", html or "")
    text = html_lib.unescape(_TAGS.sub("", text))
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _has_table(con: sqlite3.Connection, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def _local_user_id(con: sqlite3.Connection) -> int | None:
    if not _has_table(con, "settings"):
        return None
    row = con.execute("SELECT value FROM settings WHERE setting = 'account' AND key = 'userID'").fetchone()
    try:
        return None if row is None else int(row[0])
    except (TypeError, ValueError):
        return None


def load_annotations(con: sqlite3.Connection, library: str, key: str) -> tuple[list[dict], int] | None:
    """(entries, empty_omitted) for one paper, or None when the library or the item is not in the snapshot."""
    known = zotero_libraries(con)
    if library not in known:
        return None
    row = con.execute("SELECT itemID FROM items WHERE libraryID = ? AND key = ?",
                      (known[library].library_id, key)).fetchone()
    if row is None:
        return None
    paper_id = row[0]

    has_group_items = _has_table(con, "groupItems")
    users: dict[int, str] = {}
    if _has_table(con, "users"):
        users = {uid: name for uid, name in con.execute("SELECT userID, name FROM users")}
    me = _local_user_id(con)

    def author(child_id: int, author_name, external) -> str | None:
        if external:
            return author_name or None
        if library == "user":
            return "user"
        created_by = None
        if has_group_items:
            found = con.execute("SELECT createdByUserID FROM groupItems WHERE itemID = ?", (child_id,)).fetchone()
            created_by = None if found is None else found[0]
        if created_by is None:
            return author_name or None
        if me is not None and created_by == me:
            return "user"
        return users.get(created_by) or author_name or str(created_by)

    entries: list[dict] = []
    empty = 0
    rows = con.execute(
        "SELECT a.itemID, a.type, a.authorName, a.text, a.comment, a.color, a.pageLabel, a.isExternal "
        "FROM itemAttachments ia JOIN itemAnnotations a ON a.parentItemID = ia.itemID "
        "WHERE ia.parentItemID = ? AND ia.itemID NOT IN (SELECT itemID FROM deletedItems) "
        "AND a.itemID NOT IN (SELECT itemID FROM deletedItems) "
        "ORDER BY ia.itemID, a.sortIndex, a.itemID", (paper_id,)).fetchall()
    for child_id, kind, author_name, text, comment, color, page, external in rows:
        text = (text or "").strip()
        comment = (comment or "").strip()
        if not text and not comment:
            empty += 1
            continue
        entry: dict = {"type": TYPE_NAMES.get(kind, "other"), "page": page or None}
        if text:
            entry["text"] = text
        if comment:
            entry["comment"] = comment
        entry["color"] = color or None
        entry["author"] = author(child_id, author_name, external)
        if external:
            entry["external"] = True
        tags = sorted(r[0] for r in con.execute(
            "SELECT t.name FROM itemTags it JOIN tags t ON t.tagID = it.tagID WHERE it.itemID = ?", (child_id,)))
        if tags:
            entry["tags"] = tags
        entries.append(entry)

    for note_id, note in con.execute(
            "SELECT itemID, note FROM itemNotes WHERE parentItemID = ? "
            "AND itemID NOT IN (SELECT itemID FROM deletedItems) ORDER BY itemID", (paper_id,)).fetchall():
        text = note_text(note)
        if not text:
            empty += 1
            continue
        entries.append({"type": "item_note", "text": text, "author": author(note_id, None, False)})
    return entries, empty


def page_entries(entries: list[dict], offset: int, max_chars: int) -> tuple[list[dict], int | None]:
    """A page of entries starting at offset, within max_chars of text and comment; and the next offset."""
    page: list[dict] = []
    total = 0
    pos = offset
    while pos < len(entries):
        entry = entries[pos]
        size = len(entry.get("text", "")) + len(entry.get("comment", ""))
        if page and total + size > max_chars:
            break
        if not page and size > max_chars and entry.get("text"):
            entry = {**entry, "text": entry["text"][:max_chars], "truncated": True}
        page.append(entry)
        total += size
        pos += 1
    return page, (pos if pos < len(entries) else None)
