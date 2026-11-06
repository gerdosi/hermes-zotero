"""Read-only access to a snapshot of zotero.sqlite: libraries, regular items and their attachments."""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

CHUNK = 500
_NON_REGULAR = ("attachment", "note", "annotation")
_PUBLICATION_FIELDS = ("publicationTitle", "bookTitle", "proceedingsTitle", "websiteTitle",
                       "repository", "university", "publisher")
_FIELDS = ("title", "abstractNote", "date", "DOI", "extra") + _PUBLICATION_FIELDS
_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:")
_DOI_SEARCH = re.compile(r"10\.\d{4,9}/[^\s?#]+")
_EXTRA_DOI = re.compile(r"^\s*DOI:\s*(\S+)", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class Library:
    name: str          # "user" or the group ID as a string, e.g. "4805701"
    library_id: int    # libraries.libraryID
    label: str         # "My Library" or the group's name


@dataclass(frozen=True)
class Attachment:
    item_id: int
    key: str
    content_type: str | None
    link_mode: int | None
    path: str | None
    indexed_pages: int | None
    total_pages: int | None


@dataclass(frozen=True)
class ItemRef:
    item_id: int
    key: str
    library: str
    modified: str


@dataclass(frozen=True)
class Item:
    item_id: int
    key: str
    library: str
    item_type: str
    title: str
    creators: tuple[str, ...]
    year: int | None
    date: str
    doi: str
    publication: str
    abstract: str
    collections: tuple[str, ...]
    tags: tuple[str, ...]
    date_added: str
    modified: str
    attachments: tuple[Attachment, ...]


def open_snapshot(path) -> sqlite3.Connection:
    """Open a snapshot database read-only."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def normalize_doi(value) -> str:
    """Return a lowercase bare DOI, or "" when there is none."""
    if not value:
        return ""
    doi = str(value).strip().lower()
    for prefix in _DOI_PREFIXES:
        if doi.startswith(prefix):
            doi = doi[len(prefix):].strip()
            break
    if not doi.startswith("10."):
        match = _DOI_SEARCH.search(doi)
        if match:
            doi = match.group(0)
    return re.sub(r"/\s+", "/", doi)


def parse_date(value) -> tuple[int | None, str]:
    """Split Zotero's "<SQL date> <as typed>" into (year, display string)."""
    if not value:
        return None, ""
    sql, _, typed = str(value).partition(" ")
    head = sql[:4]
    year = int(head) if head.isdigit() and len(head) == 4 and head != "0000" else None
    return year, typed or sql


def libraries(con: sqlite3.Connection) -> dict[str, Library]:
    """Libraries we index (user and groups), keyed by Library.name. Feeds are excluded."""
    result: dict[str, Library] = {}
    for library_id, kind, group_id, group_name in con.execute(
            "SELECT l.libraryID, l.type, g.groupID, g.name FROM libraries l "
            "LEFT JOIN groups g ON g.libraryID = l.libraryID ORDER BY l.libraryID"):
        if kind == "user":
            result["user"] = Library("user", library_id, "My Library")
        elif kind == "group" and group_id is not None:
            result[str(group_id)] = Library(str(group_id), library_id, group_name or str(group_id))
    return result


def _modified(date_modified, client_date_modified, version) -> str:
    return f"{date_modified}|{client_date_modified}|{version}"


def list_items(con: sqlite3.Connection, libs: Iterable[str]) -> list[ItemRef]:
    """Regular, non-trashed items of the requested libraries (in order given), sorted by key."""
    known = libraries(con)
    refs: list[ItemRef] = []
    seen: set[str] = set()
    for name in libs:
        if name in seen or name not in known:
            continue
        seen.add(name)
        rows = con.execute(
            "SELECT i.itemID, i.key, i.dateModified, i.clientDateModified, i.version FROM items i "
            "JOIN itemTypesCombined t ON t.itemTypeID = i.itemTypeID "
            "WHERE i.libraryID = ? AND t.typeName NOT IN (?, ?, ?) "
            "AND i.itemID NOT IN (SELECT itemID FROM deletedItems) ORDER BY i.key",
            (known[name].library_id, *_NON_REGULAR)).fetchall()
        refs.extend(ItemRef(r[0], r[1], name, _modified(*r[2:])) for r in rows)
    return refs


def _chunks(ids: Sequence[int]):
    for start in range(0, len(ids), CHUNK):
        yield ids[start:start + CHUNK]


def _collection_paths(con: sqlite3.Connection) -> dict[int, str]:
    """Full " / " path of every collection; parent loops are cut."""
    rows = {cid: (name, parent) for cid, name, parent in
            con.execute("SELECT collectionID, collectionName, parentCollectionID FROM collections")}
    paths: dict[int, str] = {}
    for cid in rows:
        parts: list[str] = []
        seen: set[int] = set()
        cur: int | None = cid
        while cur is not None and cur in rows and cur not in seen:
            seen.add(cur)
            parts.append(rows[cur][0])
            cur = rows[cur][1]
        paths[cid] = " / ".join(reversed(parts))
    return paths


def load_items(con: sqlite3.Connection, item_ids: Sequence[int]) -> list[Item]:
    """Load full items in the order of item_ids, skipping IDs that do not exist."""
    item_ids = list(item_ids)
    lib_names = {lib.library_id: lib.name for lib in libraries(con).values()}
    base: dict[int, tuple] = {}
    fields: dict[int, dict[str, str]] = defaultdict(dict)
    creators: dict[int, list[str]] = defaultdict(list)
    collections: dict[int, set[str]] = defaultdict(set)
    tags: dict[int, list[str]] = defaultdict(list)
    attachments: dict[int, list[Attachment]] = defaultdict(list)
    paths = _collection_paths(con)
    field_marks = ",".join("?" * len(_FIELDS))

    for chunk in _chunks(item_ids):
        marks = ",".join("?" * len(chunk))
        for row in con.execute(
                "SELECT i.itemID, i.key, i.libraryID, t.typeName, i.dateAdded, i.dateModified, "
                "i.clientDateModified, i.version FROM items i "
                f"JOIN itemTypesCombined t ON t.itemTypeID = i.itemTypeID WHERE i.itemID IN ({marks})", chunk):
            base[row[0]] = row[1:]
        for iid, fname, value in con.execute(
                "SELECT d.itemID, f.fieldName, v.value FROM itemData d "
                "JOIN fieldsCombined f ON f.fieldID = d.fieldID "
                "JOIN itemDataValues v ON v.valueID = d.valueID "
                f"WHERE d.itemID IN ({marks}) AND f.fieldName IN ({field_marks})", (*chunk, *_FIELDS)):
            fields[iid][fname] = "" if value is None else str(value)
        for iid, first, last, mode in con.execute(
                "SELECT ic.itemID, c.firstName, c.lastName, c.fieldMode FROM itemCreators ic "
                f"JOIN creators c ON c.creatorID = ic.creatorID WHERE ic.itemID IN ({marks}) "
                "ORDER BY ic.itemID, ic.orderIndex", chunk):
            last = last or ""
            creators[iid].append(last if mode == 1 or not first else f"{last}, {first}")
        for iid, cid in con.execute(
                f"SELECT itemID, collectionID FROM collectionItems WHERE itemID IN ({marks})", chunk):
            if cid in paths:
                collections[iid].add(paths[cid])
        for iid, name in con.execute(
                "SELECT it.itemID, t.name FROM itemTags it JOIN tags t ON t.tagID = it.tagID "
                f"WHERE it.itemID IN ({marks})", chunk):
            tags[iid].append(name)
        for row in con.execute(
                "SELECT a.parentItemID, a.itemID, i.key, a.contentType, a.linkMode, a.path, "
                "f.indexedPages, f.totalPages FROM itemAttachments a "
                "JOIN items i ON i.itemID = a.itemID "
                "LEFT JOIN fulltextItems f ON f.itemID = a.itemID "
                f"WHERE a.parentItemID IN ({marks}) "
                "AND a.itemID NOT IN (SELECT itemID FROM deletedItems) ORDER BY a.itemID", chunk):
            attachments[row[0]].append(Attachment(*row[1:]))

    items: list[Item] = []
    for iid in item_ids:
        if iid not in base:
            continue
        key, library_id, item_type, date_added, d_mod, c_mod, version = base[iid]
        f = fields.get(iid, {})
        year, date = parse_date(f.get("date", ""))
        doi = normalize_doi(f.get("DOI"))
        if not doi:
            match = _EXTRA_DOI.search(f.get("extra", ""))
            doi = normalize_doi(match.group(1)) if match else ""
        publication = next((f[n] for n in _PUBLICATION_FIELDS if f.get(n)), "")
        items.append(Item(
            item_id=iid, key=key, library=lib_names.get(library_id, str(library_id)), item_type=item_type,
            title=f.get("title", ""), creators=tuple(creators.get(iid, ())), year=year, date=date, doi=doi,
            publication=publication, abstract=f.get("abstractNote", ""),
            collections=tuple(sorted(collections.get(iid, ()))), tags=tuple(sorted(tags.get(iid, ()))),
            date_added=date_added, modified=_modified(d_mod, c_mod, version),
            attachments=tuple(attachments.get(iid, ()))))
    return items
