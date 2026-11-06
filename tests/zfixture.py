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
