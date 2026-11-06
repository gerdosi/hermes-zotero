# Task 04 — Read items from the snapshot

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code |
| Reasoning | **medium**: many small rules, all listed below |
| Budget | ≤ 50 tool calls |
| Depends on | tasks 01–03b committed |
| Done when | `.venv/bin/python -m pytest` shows **62 passed** (52 old + 10 new), checksums match, report committed |

## Goal

Read the papers, books and other "regular" items from the private snapshot of `zotero.sqlite`, with their metadata and attachments. Later tasks pick each item's text and index it. This task touches no files outside the plugin and runs no network calls.

## Facts (verified on Gábor's Zotero 11 database, 5 Nov 2026)

- Item types, fields and creator types are looked up **by name** through `itemTypesCombined.typeName`, `fieldsCombined.fieldName` and `creatorTypes.creatorType`. Never hard-code numeric IDs; the test fixture uses different IDs on purpose.
- "Regular" items are every item type except `attachment`, `note` and `annotation`. Trashed items are listed in `deletedItems`. Gábor's library: 18,597 regular items in My Library and 693 in group 4805701, among about 42,700 records.
- Libraries: `libraries.type` is `user`, `group` (the group ID lives in `groups.groupID`, the name in `groups.name`) or `feed`. Feeds are never indexed.
- Field values come from `itemData` → `itemDataValues.value`. The `date` field is stored as `"<SQL date> <as typed>"`, e.g. `"2001-00-00 2001"` or `"2019-03-00 March 2019"`; `"0000-00-00 n.d."` means no year.
- DOIs: 35 are stored as `https://doi.org/...` URLs; 51 more items carry `DOI: ...` only in the `extra` field; 8 have data-entry slips (a publisher link pasted in, or a stray space after the slash).
- Creators: `itemCreators.orderIndex` gives the order. `creators.fieldMode = 1` means a single-field name, stored in `lastName`.
- Attachments: `itemAttachments.parentItemID` → the parent item. `linkMode` 0 and 1 are files stored in Zotero, and 3 is a link only. `fulltextItems` holds `indexedPages`/`totalPages` per attachment.
- Reading all 19,290 items with the reference implementation took 0.6 s. Batch the queries: SQLite allows at most 999 bound parameters per statement by default, so use chunks of 500.

## Files

```
create  zotcore/zdb.py
create  tests/zfixture.py         (verbatim, below: a test helper that builds a small Zotero-like database)
create  tests/test_04_zdb.py      (verbatim, below)
create  tasks/04-report.md
```

`tests/zfixture.py` is an acceptance file like the tests: copy it byte-for-byte and never edit it.

## Spec — `zotcore/zdb.py`

```python
@dataclass(frozen=True)
class Library:
    name: str          # "user" or the group ID as a string, e.g. "4805701"
    library_id: int    # libraries.libraryID
    label: str         # "My Library" or the group's name

@dataclass(frozen=True)
class Attachment:
    item_id: int; key: str; content_type: str | None; link_mode: int | None; path: str | None
    indexed_pages: int | None; total_pages: int | None

@dataclass(frozen=True)
class ItemRef:
    item_id: int; key: str; library: str; modified: str

@dataclass(frozen=True)
class Item:
    item_id: int; key: str; library: str; item_type: str; title: str
    creators: tuple[str, ...]; year: int | None; date: str; doi: str; publication: str; abstract: str
    collections: tuple[str, ...]; tags: tuple[str, ...]; date_added: str; modified: str
    attachments: tuple[Attachment, ...]

def open_snapshot(path) -> sqlite3.Connection        # read-only: sqlite3.connect(f"file:{path}?mode=ro", uri=True)
def normalize_doi(value) -> str
def parse_date(value) -> tuple[int | None, str]
def libraries(con) -> dict[str, Library]              # keyed by Library.name; feeds excluded
def list_items(con, libs: Iterable[str]) -> list[ItemRef]
def load_items(con, item_ids: Sequence[int]) -> list[Item]
```

Rules:

1. `normalize_doi`: `None` or empty → `""`. Otherwise strip and lowercase. Remove the first matching prefix among `https://doi.org/`, `http://doi.org/`, `https://dx.doi.org/`, `http://dx.doi.org/` and `doi:`, then strip again. If the result does not start with `10.`, look for the regex `10\.\d{4,9}/[^\s?#]+` inside it and use the match. Finally replace `/` followed by whitespace with `/`. Do **not** URL-decode: `%3C` stays `%3c`, because the Markdown file names depend on it.
2. `parse_date`: empty → `(None, "")`. Split once on the first space into the SQL part and the as-typed part. The year is the first 4 characters of the SQL part if they are digits and not `0000`, otherwise `None`. The display string is the as-typed part, or the SQL part if there is none.
3. `list_items`: for each requested library name, **in the order given**, skip unknown names and repeats. List its regular, non-trashed items **sorted by key**. `modified` = `f"{dateModified}|{clientDateModified}|{version}"` from `items`; it changes whenever Zotero saves the item.
4. `load_items`: return items in the order of `item_ids`, silently skipping IDs that don't exist. Per item:
   - `title`, `abstract` (`abstractNote`) and `date`/`year` (rule 2) come from the fields; missing fields give `""` / `None`.
   - `doi` comes from the `DOI` field via rule 1. If that is empty, take the first `^\s*DOI:\s*(\S+)` line (case-insensitive, multiline) of `extra`, normalized.
   - `publication`: the first non-empty field among `publicationTitle`, `bookTitle`, `proceedingsTitle`, `websiteTitle`, `repository`, `university`, `publisher`.
   - `creators`: every creator in `orderIndex` order. Format `"Last, First"`, or just `lastName` when `fieldMode = 1` or the first name is empty.
   - `collections`: the full path of every collection the item is directly in, joined with `" / "` from the top (e.g. `"Metabolism / Ferroptosis"`), sorted. Guard against parent loops.
   - `tags`: tag names, sorted.
   - `attachments`: non-trashed child attachments ordered by `itemID`, with `content_type`, `link_mode`, `path`, plus `indexed_pages`/`total_pages` from `fulltextItems` (a LEFT JOIN, so `None` when absent). Notes and annotations are not attachments.
   - `date_added` = `items.dateAdded`; `modified` exactly as in rule 3.
   - `library` = the `Library.name` of the item's library.
5. Query in chunks of 500 IDs, one query per kind of data (fields, creators, collections, tags, attachments), not one query per item.
6. Never open the live Zotero database. Callers pass the snapshot path; `open_snapshot` is read-only.

## Acceptance tests (copy verbatim, then verify checksums)

| File | SHA-256 |
| --- | --- |
| `tests/zfixture.py` | `e9d3b368c150a42c375c99b3564ce9ebb5c52cb485663896d9f1d644326e724c` |
| `tests/test_04_zdb.py` | `61764a3cfb7631b26146f86eab5fd65c8a41ee4f1a01189f80582a7550e5e0e8` |

### `tests/zfixture.py`

```python
"""Builds a small Zotero-like data directory for tests (tables copied from Zotero 11's schema).

IDs deliberately differ from a real Zotero install, so code must look fields, item types and
creator types up by NAME, never by numeric ID."""
import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE libraries (libraryID INTEGER PRIMARY KEY, type TEXT NOT NULL, editable INT NOT NULL, filesEditable INT NOT NULL, version INT NOT NULL DEFAULT 0, storageVersion INT NOT NULL DEFAULT 0, lastSync INT NOT NULL DEFAULT 0, archived INT NOT NULL DEFAULT 0, isAdmin INT NOT NULL DEFAULT 0, clientVersion INT NOT NULL DEFAULT 0);
CREATE TABLE groups (groupID INTEGER PRIMARY KEY, libraryID INT NOT NULL UNIQUE, name TEXT NOT NULL, description TEXT NOT NULL, version INT NOT NULL);
CREATE TABLE itemTypesCombined (itemTypeID INT NOT NULL, typeName TEXT NOT NULL, display INT DEFAULT 1 NOT NULL, custom INT NOT NULL, PRIMARY KEY (itemTypeID));
CREATE TABLE fieldsCombined (fieldID INT NOT NULL, fieldName TEXT NOT NULL, label TEXT, fieldFormatID INT, custom INT NOT NULL, PRIMARY KEY (fieldID));
CREATE TABLE items (itemID INTEGER PRIMARY KEY, itemTypeID INT NOT NULL, dateAdded TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, dateModified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, clientDateModified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, libraryID INT NOT NULL, key TEXT NOT NULL, version INT NOT NULL DEFAULT 0, synced INT NOT NULL DEFAULT 0, clientVersion INT NOT NULL DEFAULT 0, UNIQUE (libraryID, key));
CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value UNIQUE, valueNormalized TEXT);
CREATE TABLE itemData (itemID INT, fieldID INT, valueID, PRIMARY KEY (itemID, fieldID));
CREATE TABLE creators (creatorID INTEGER PRIMARY KEY, firstName TEXT, lastName TEXT, fieldMode INT, firstNameNormalized TEXT, lastNameNormalized TEXT, UNIQUE (lastName, firstName, fieldMode));
CREATE TABLE creatorTypes (creatorTypeID INTEGER PRIMARY KEY, creatorType TEXT);
CREATE TABLE itemCreators (itemID INT NOT NULL, creatorID INT NOT NULL, creatorTypeID INT NOT NULL DEFAULT 1, orderIndex INT NOT NULL DEFAULT 0, PRIMARY KEY (itemID, creatorID, creatorTypeID, orderIndex), UNIQUE (itemID, orderIndex));
CREATE TABLE collections (collectionID INTEGER PRIMARY KEY, collectionName TEXT NOT NULL, parentCollectionID INT DEFAULT NULL, clientDateModified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, libraryID INT NOT NULL, key TEXT NOT NULL, version INT NOT NULL DEFAULT 0, synced INT NOT NULL DEFAULT 0, clientVersion INT NOT NULL DEFAULT 0, UNIQUE (libraryID, key));
CREATE TABLE collectionItems (collectionID INT NOT NULL, itemID INT NOT NULL, orderIndex INT NOT NULL DEFAULT 0, PRIMARY KEY (collectionID, itemID));
CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, parentItemID INT, linkMode INT, contentType TEXT, charsetID INT, path TEXT, syncState INT DEFAULT 0, storageModTime INT, storageHash TEXT, lastProcessedModificationTime INT, lastRead INT);
CREATE TABLE itemNotes (itemID INTEGER PRIMARY KEY, parentItemID INT, note TEXT, title TEXT);
CREATE TABLE itemAnnotations (itemID INTEGER PRIMARY KEY, parentItemID INT NOT NULL, type INTEGER NOT NULL, authorName TEXT, text TEXT, comment TEXT, color TEXT, pageLabel TEXT, sortIndex TEXT NOT NULL, position TEXT NOT NULL, isExternal INT NOT NULL, textNormalized TEXT, commentNormalized TEXT);
CREATE TABLE deletedItems (itemID INTEGER PRIMARY KEY, dateDeleted DEFAULT CURRENT_TIMESTAMP NOT NULL);
CREATE TABLE tags (tagID INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, nameNormalized TEXT);
CREATE TABLE itemTags (itemID INT NOT NULL, tagID INT NOT NULL, type INT NOT NULL, PRIMARY KEY (itemID, tagID));
CREATE TABLE fulltextItems (itemID INTEGER PRIMARY KEY, indexedPages INT, totalPages INT, indexedChars INT, totalChars INT, version INT NOT NULL DEFAULT 0, synced INT NOT NULL DEFAULT 0);
"""

ITEM_TYPES = ["attachment", "note", "annotation", "journalArticle", "book", "bookSection",
              "preprint", "conferencePaper", "webpage", "report", "thesis"]
FIELDS = ["title", "abstractNote", "date", "DOI", "extra", "publicationTitle", "bookTitle",
          "proceedingsTitle", "websiteTitle", "repository", "university", "publisher", "url"]
CREATOR_TYPES = ["editor", "contributor", "author", "translator"]


class ZoteroFixture:
    """A writable fake Zotero data dir: <data_dir>/zotero.sqlite and <data_dir>/storage/."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "storage").mkdir(exist_ok=True)
        self.db_path = self.data_dir / "zotero.sqlite"
        self.con = sqlite3.connect(self.db_path, isolation_level=None)
        self.con.executescript(DDL)
        self.con.execute("INSERT INTO libraries(libraryID, type, editable, filesEditable) VALUES (1, 'user', 1, 1)")
        for i, name in enumerate(ITEM_TYPES):
            self.con.execute("INSERT INTO itemTypesCombined VALUES (?, ?, 1, 0)", (200 + 3 * i, name))
        for i, name in enumerate(FIELDS):
            self.con.execute("INSERT INTO fieldsCombined VALUES (?, ?, NULL, NULL, 0)", (500 + 7 * i, name))
        for i, name in enumerate(CREATOR_TYPES):
            self.con.execute("INSERT INTO creatorTypes VALUES (?, ?)", (30 + i, name))
        self._next_lib = 10
        self._clock = 0

    # --- lookups -----------------------------------------------------------------------------
    def _type_id(self, name):
        return self.con.execute("SELECT itemTypeID FROM itemTypesCombined WHERE typeName=?", (name,)).fetchone()[0]

    def _field_id(self, name):
        return self.con.execute("SELECT fieldID FROM fieldsCombined WHERE fieldName=?", (name,)).fetchone()[0]

    def _value_id(self, value):
        row = self.con.execute("SELECT valueID FROM itemDataValues WHERE value=?", (value,)).fetchone()
        if row:
            return row[0]
        return self.con.execute("INSERT INTO itemDataValues(value) VALUES (?)", (value,)).lastrowid

    def _stamp(self):
        self._clock += 1
        return f"2026-01-01 10:{self._clock // 60:02d}:{self._clock % 60:02d}"

    # --- builders ------------------------------------------------------------------------------
    def add_group(self, group_id: int, name: str) -> int:
        lib = self._next_lib
        self._next_lib += 1
        self.con.execute("INSERT INTO libraries(libraryID, type, editable, filesEditable) VALUES (?, 'group', 1, 1)", (lib,))
        self.con.execute("INSERT INTO groups VALUES (?, ?, ?, '', 0)", (group_id, lib, name))
        return lib

    def add_feed_library(self) -> int:
        lib = self._next_lib
        self._next_lib += 1
        self.con.execute("INSERT INTO libraries(libraryID, type, editable, filesEditable) VALUES (?, 'feed', 0, 0)", (lib,))
        return lib

    def _insert_item(self, key, type_name, library_id, date_added=None):
        stamp = self._stamp()
        return self.con.execute(
            "INSERT INTO items(itemTypeID, dateAdded, dateModified, clientDateModified, libraryID, key, version) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            (self._type_id(type_name), date_added or stamp, stamp, stamp, library_id, key)).lastrowid

    def add_item(self, key, item_type="journalArticle", *, library_id=1, fields=None, creators=(),
                 collections=(), tags=(), date_added=None) -> int:
        """creators: ("First", "Last", "author") tuples, or ("Single Name", "author") for one-field names."""
        item_id = self._insert_item(key, item_type, library_id, date_added)
        for name, value in (fields or {}).items():
            self.con.execute("INSERT INTO itemData VALUES (?, ?, ?)", (item_id, self._field_id(name), self._value_id(value)))
        for order, creator in reversed(list(enumerate(creators))):  # reversed: orderIndex must decide, not rowid
            if len(creator) == 2:
                first, last, mode, ctype = "", creator[0], 1, creator[1]
            else:
                first, last, ctype = creator
                mode = 0
            row = self.con.execute("SELECT creatorID FROM creators WHERE lastName=? AND firstName=? AND fieldMode=?",
                                   (last, first, mode)).fetchone()
            cid = row[0] if row else self.con.execute(
                "INSERT INTO creators(firstName, lastName, fieldMode) VALUES (?, ?, ?)", (first, last, mode)).lastrowid
            ct = self.con.execute("SELECT creatorTypeID FROM creatorTypes WHERE creatorType=?", (ctype,)).fetchone()[0]
            self.con.execute("INSERT INTO itemCreators VALUES (?, ?, ?, ?)", (item_id, cid, ct, order))
        for coll in collections:
            self.con.execute("INSERT INTO collectionItems VALUES (?, ?, 0)", (coll, item_id))
        for tag in tags:
            row = self.con.execute("SELECT tagID FROM tags WHERE name=?", (tag,)).fetchone()
            tid = row[0] if row else self.con.execute("INSERT INTO tags(name) VALUES (?)", (tag,)).lastrowid
            self.con.execute("INSERT INTO itemTags VALUES (?, ?, 0)", (item_id, tid))
        return item_id

    def add_collection(self, name, *, parent=None, library_id=1, key=None) -> int:
        n = self.con.execute("SELECT count(*) FROM collections").fetchone()[0]
        return self.con.execute(
            "INSERT INTO collections(collectionName, parentCollectionID, libraryID, key) VALUES (?, ?, ?, ?)",
            (name, parent, library_id, key or f"COLL{n:04d}")).lastrowid

    def add_attachment(self, parent_id, key, *, content_type="application/pdf", link_mode=0,
                       path="storage:paper.pdf", ft_text=None, indexed_pages=None, total_pages=None,
                       library_id=None) -> int:
        lib = library_id or self.con.execute("SELECT libraryID FROM items WHERE itemID=?", (parent_id,)).fetchone()[0]
        item_id = self._insert_item(key, "attachment", lib)
        self.con.execute("INSERT INTO itemAttachments(itemID, parentItemID, linkMode, contentType, path) VALUES (?, ?, ?, ?, ?)",
                         (item_id, parent_id, link_mode, content_type, path))
        if indexed_pages is not None or total_pages is not None:
            self.con.execute("INSERT INTO fulltextItems(itemID, indexedPages, totalPages) VALUES (?, ?, ?)",
                             (item_id, indexed_pages, total_pages))
        if ft_text is not None:
            self.write_ft_cache(key, ft_text)
        return item_id

    def write_ft_cache(self, attachment_key, text):
        folder = self.data_dir / "storage" / attachment_key
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ".zotero-ft-cache").write_text(text, encoding="utf-8")

    def add_note(self, parent_id, key, html="<p>note</p>") -> int:
        lib = self.con.execute("SELECT libraryID FROM items WHERE itemID=?", (parent_id,)).fetchone()[0]
        item_id = self._insert_item(key, "note", lib)
        self.con.execute("INSERT INTO itemNotes(itemID, parentItemID, note, title) VALUES (?, ?, ?, '')",
                         (item_id, parent_id, html))
        return item_id

    def add_annotation(self, attachment_id, key, text, *, comment="", page_label="1", color="#ffd400", kind=1) -> int:
        lib = self.con.execute("SELECT libraryID FROM items WHERE itemID=?", (attachment_id,)).fetchone()[0]
        item_id = self._insert_item(key, "annotation", lib)
        self.con.execute("INSERT INTO itemAnnotations(itemID, parentItemID, type, text, comment, color, pageLabel, "
                         "sortIndex, position, isExternal) VALUES (?, ?, ?, ?, ?, ?, ?, '00000|000000|00000', '{}', 0)",
                         (item_id, attachment_id, kind, text, comment, color, page_label))
        return item_id

    def set_field(self, item_id, name, value):
        self.con.execute("INSERT OR REPLACE INTO itemData VALUES (?, ?, ?)", (item_id, self._field_id(name), self._value_id(value)))
        self.touch(item_id)

    def touch(self, item_id):
        stamp = self._stamp()
        self.con.execute("UPDATE items SET dateModified=?, clientDateModified=?, version=version+1 WHERE itemID=?",
                         (stamp, stamp, item_id))

    def trash(self, item_id):
        self.con.execute("INSERT INTO deletedItems(itemID) VALUES (?)", (item_id,))

    def close(self):
        self.con.close()
```

### `tests/test_04_zdb.py`

```python
import sqlite3
import time

import pytest

from tests.zfixture import ZoteroFixture
from zotcore.zdb import (Attachment, Item, ItemRef, libraries, list_items, load_items, normalize_doi,
                         open_snapshot, parse_date)


@pytest.fixture
def lib(tmp_path):
    z = ZoteroFixture(tmp_path / "Zotero")
    group_lib = z.add_group(4805701, "Ancestralize")
    z.add_feed_library()
    parent = z.add_collection("Metabolism")
    child = z.add_collection("Ferroptosis", parent=parent)
    art = z.add_item("ART00001", fields={
        "title": "Fatty acid desaturation and ferroptosis", "date": "2026-06-29 2026-06-29",
        "DOI": "https://doi.org/10.1016/J.CELL.2026.10.001", "publicationTitle": "Cell",
        "abstractNote": "We show that SCD1 ..."},
        creators=[("Lena", "Kuehnemann", "author"), ("WHO Consortium", "author"), ("Ann", "Editor", "editor")],
        collections=[child], tags=["Important", "lipids"])
    z.add_attachment(art, "PDF00001", ft_text="x" * 500, indexed_pages=10, total_pages=12)
    z.add_attachment(art, "HTM00001", content_type="text/html", link_mode=1, path="storage:page.html")
    z.add_attachment(art, "URL00001", content_type="text/html", link_mode=3, path=None)
    trashed_att = z.add_attachment(art, "PDF0GONE")
    z.trash(trashed_att)
    z.add_note(art, "NOTE0001")
    z.add_item("SEC00001", "bookSection", fields={"title": "A chapter", "date": "2001-00-00 2001",
                                                   "bookTitle": "Big Book", "extra": "PMID: 1\nDOI: 10.1000/ABC"})
    z.add_item("NODATE01", "report", fields={"title": "Undated", "date": "0000-00-00 n.d."})
    gone = z.add_item("TRASHED1", fields={"title": "In the trash"})
    z.trash(gone)
    z.add_item("GRP00001", library_id=group_lib, fields={"title": "Group paper"})
    z.close()
    con = open_snapshot(z.db_path)
    yield con
    con.close()


def test_normalize_doi():
    assert normalize_doi("https://doi.org/10.1016/J.CELL.2026.10.001") == "10.1016/j.cell.2026.10.001"
    assert normalize_doi("http://dx.doi.org/10.2741/4160") == "10.2741/4160"
    assert normalize_doi("doi: 10.1/X ") == "10.1/x"
    assert normalize_doi("  10.1002/(SICI)1096-8644(1998)107:27<177::AID-AJPA7>3.0.CO;2-B") == \
        "10.1002/(sici)1096-8644(1998)107:27<177::aid-ajpa7>3.0.co;2-b"
    assert normalize_doi("https://journals.physiology.org/doi/full/10.1152/ajpendo.00323.2019") == \
        "10.1152/ajpendo.00323.2019"  # a publisher link pasted into the DOI field
    assert normalize_doi("10.1038/ s41577-018-0113-4") == "10.1038/s41577-018-0113-4"
    assert normalize_doi("") == "" and normalize_doi(None) == ""


def test_parse_date():
    assert parse_date("2026-06-29 2026-06-29") == (2026, "2026-06-29")
    assert parse_date("2001-00-00 2001") == (2001, "2001")
    assert parse_date("2019-03-00 March 2019") == (2019, "March 2019")
    assert parse_date("0000-00-00 n.d.") == (None, "n.d.")
    assert parse_date("") == (None, "")


def test_open_snapshot_is_read_only(lib):
    with pytest.raises(sqlite3.OperationalError):
        lib.execute("CREATE TABLE x(y)")


def test_libraries(lib):
    libs = libraries(lib)
    assert set(libs) == {"user", "4805701"}  # the feed library is not a library we index
    assert libs["user"].label == "My Library"
    assert libs["4805701"].label == "Ancestralize"


def test_list_items_regular_only(lib):
    refs = list_items(lib, ["user"])
    assert [r.key for r in refs] == ["ART00001", "NODATE01", "SEC00001"]  # sorted; no attachments, notes, trash
    assert all(isinstance(r, ItemRef) and r.library == "user" and r.modified for r in refs)
    assert [r.key for r in list_items(lib, ["4805701"])] == ["GRP00001"]
    both = [r.key for r in list_items(lib, ["user", "4805701", "999", "user"])]  # unknown group and repeats ignored
    assert both == ["ART00001", "NODATE01", "SEC00001", "GRP00001"]  # libraries in the order asked, keys sorted


def test_modified_changes_when_item_changes(tmp_path):
    z = ZoteroFixture(tmp_path / "Z")
    iid = z.add_item("AAAA0001", fields={"title": "t"})
    before = list_items(open_snapshot(z.db_path), ["user"])[0].modified
    z.set_field(iid, "title", "t2")
    after = list_items(open_snapshot(z.db_path), ["user"])[0].modified
    assert before != after


def test_load_item_fields(lib):
    ref = {r.key: r for r in list_items(lib, ["user"])}
    (art,) = load_items(lib, [ref["ART00001"].item_id])
    assert isinstance(art, Item)
    assert art.title == "Fatty acid desaturation and ferroptosis"
    assert art.item_type == "journalArticle"
    assert art.creators == ("Kuehnemann, Lena", "WHO Consortium", "Editor, Ann")
    assert (art.year, art.date) == (2026, "2026-06-29")
    assert art.doi == "10.1016/j.cell.2026.10.001"
    assert art.publication == "Cell"
    assert art.abstract.startswith("We show")
    assert art.collections == ("Metabolism / Ferroptosis",)
    assert art.tags == ("Important", "lipids")
    assert art.library == "user"
    assert art.modified == ref["ART00001"].modified
    assert [a.key for a in art.attachments] == ["PDF00001", "HTM00001", "URL00001"]  # trashed one excluded
    pdf = art.attachments[0]
    assert isinstance(pdf, Attachment)
    assert (pdf.content_type, pdf.link_mode, pdf.path) == ("application/pdf", 0, "storage:paper.pdf")
    assert (pdf.indexed_pages, pdf.total_pages) == (10, 12)
    assert art.attachments[2].link_mode == 3 and art.attachments[2].path is None


def test_load_item_fallbacks(lib):
    ref = {r.key: r for r in list_items(lib, ["user"])}
    sec, nodate = load_items(lib, [ref["SEC00001"].item_id, ref["NODATE01"].item_id])
    assert sec.publication == "Big Book"  # bookTitle when there is no publicationTitle
    assert sec.doi == "10.1000/abc"  # DOI taken from the Extra field
    assert (sec.year, sec.date) == (2001, "2001")
    assert sec.creators == () and sec.collections == () and sec.tags == () and sec.attachments == ()
    assert (nodate.year, nodate.date, nodate.doi, nodate.publication) == (None, "n.d.", "", "")


def test_load_items_keeps_order_and_skips_unknown(lib):
    ref = {r.key: r for r in list_items(lib, ["user"])}
    ids = [ref["SEC00001"].item_id, 999999, ref["ART00001"].item_id]
    assert [i.key for i in load_items(lib, ids)] == ["SEC00001", "ART00001"]


def test_load_many_items_quickly(tmp_path):
    z = ZoteroFixture(tmp_path / "Z")
    z.con.execute("BEGIN")
    for n in range(1500):  # more than SQLite's default limit of 999 bound parameters
        iid = z.add_item(f"K{n:07d}", fields={"title": f"Paper {n}", "date": "2020-00-00 2020"},
                         creators=[("A", f"Author{n}", "author")])
        z.add_attachment(iid, f"A{n:07d}")
    z.con.execute("COMMIT")
    z.close()
    con = open_snapshot(z.db_path)
    refs = list_items(con, ["user"])
    started = time.monotonic()
    items = load_items(con, [r.item_id for r in refs])
    assert len(items) == 1500
    assert all(len(i.attachments) == 1 for i in items)
    assert time.monotonic() - started < 5
```


## Commands

```bash
.venv/bin/python -m pytest          # expect: 62 passed
shasum -a 256 tests/zfixture.py tests/test_04_zdb.py
```

No live check for this task; task 06's live check exercises it on the real library.

## Out of scope

Text, passages, the index, annotations content, citations.
