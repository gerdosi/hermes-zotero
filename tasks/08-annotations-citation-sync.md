# Task 08 — Annotations, the citation line and the time-boxed `zotero_sync` tool

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code |
| Reasoning | **medium** (everything is specified; high is fine too). Set it in the app's model picker before pasting the prompt. |
| Budget | ≤ 60 tool calls |
| Depends on | task 07 committed (106 tests pass) |
| Done when | `.venv/bin/python -m pytest` shows **122 passed** (106 old + 16 new), checksum matches, report committed |

## Goal

Three additions from plan v3.1:

1. **Annotations mode** in `zotero_read`: `mode="annotations"` returns the user's own highlights, comments and child notes on a paper, each tagged with who wrote it (`"author": "user"` for the user's own words). Text mode reports how many there are.
2. **A citation line** in every `zotero_read` result: Zotero's own formatted reference (APA) from Zotero's local API on `127.0.0.1` when Zotero is running with that API switched on, otherwise an approximate author-year line built from the index, labelled `"approximate": true`.
3. **The `zotero_sync` tool**: a sync step that stops after about `budget_seconds` (5–60, default 30 from settings) and resumes on the next call, so the agent can bring the index up to date inside a chat turn. One lock file makes sure only one sync (tool or `hermes zotero sync`) runs at a time.

It also carries over one fix from review: a time-boxed `sync` that stops early now reports unreadable items too.

## Facts (checked on Gábor's real snapshot, 6 Nov 2026, and in Zotero's source)

- **Annotations live in the snapshot, not the index.** `itemAnnotations.parentItemID` is the PDF attachment; the attachment's `itemAttachments.parentItemID` is the paper. Gábor's library has 169 annotations on 28 papers (types 1 highlight: 129, 3 image: 32, 5 underline: 8; none external) and 46 child notes. Adding an annotation does **not** change the paper's `clientDateModified` (annotations from August sit under papers last modified in July), so indexing them during sync would miss changes. Reading them from the current snapshot at call time is always as fresh as the snapshot and costs ≤ 2 ms per paper.
- **Group annotations are not all the user's.** All 111 annotations in group 4805701 were created by another member (`groupItems.createdByUserID` ≠ the local `settings` row `('account', 'userID')`). `authorName` is filled for only 41 of them, so it can't be used to decide. Rule below: My Library → `"user"`; group → `"user"` only when `createdByUserID` equals the local user ID, otherwise that member's name from `users`.
- Annotation type numbers (Zotero `annotations.js`): 1 highlight, 2 note, 3 image, 4 ink, 5 underline, 6 text. Image and ink annotations usually carry no text; they are counted in `empty_omitted`, not listed.
- **Zotero's local API** (`chrome/content/zotero/xpcom/server/server_localAPI.js`, Zotero 11.0 source): `GET /api/users/0/items/<key>` (My Library) or `/api/groups/<groupID>/items/<key>`; `?format=json&include=bib&style=apa` returns one JSON object with `"key"` and `"bib"`, an HTML `<div class="csl-bib-body">…<div class="csl-entry">…</div></div>`. The API is **off by default** (`extensions.zotero.httpServer.localAPI.enabled = false`; then every request gets `403 Local API is not enabled`), listens on `127.0.0.1:23119`, and accepts only a `Host` of `127.0.0.1`/`localhost`. `apa` is one of Zotero's bundled styles, so Zotero never downloads it (a style that isn't installed would make Zotero fetch it from zotero.org).
- Hermes' default deadline for one tool call is 420 s (`timeouts.tools.sequential_call`), so a 60 s sync step is safe. Tool calls in one batch can run in parallel threads, hence the lock.
- A full sync of the real library takes ~70 s from scratch; re-checking an unchanged library takes ~1.7 s. So a 30 s tool call indexes ≈ 8,000 new items, and resuming re-examines the already-indexed items cheaply.

## Files

```
create  zotcore/annotations.py
create  zotcore/citation.py
create  zotcore/synctool.py
modify  zotcore/index.py                   (SyncReport.read_errors; summary line in partial runs)
modify  zotcore/search.py                  (item_info; read_item uses it, output unchanged)
modify  zotcore/tools.py                   (zotero_read: mode, annotations_count, citation; new zotero_sync; citation_api)
modify  zotcore/cli.py                     (sync and snapshot hold the sync lock)
modify  __init__.py                        (pass citation_api)
modify  plugin.yaml                        (provides_tools gains zotero_sync)
create  tests/test_08_annotations_citation_sync.py   (verbatim, below)
create  tasks/08-report.md
commit  tasks/08-annotations-citation-sync.md, tasks/README.md, AGENTS.md   (added or updated by the reviewer; commit them as they are)
```

Do not touch `zotcore/textsource.py`, `zotcore/zdb.py`, `zotcore/snapshot.py`, `zotcore/settings.py` or any existing test.

## Spec — `zotcore/index.py`

1. `SyncReport` gains a last field `read_errors: int = 0`.
2. Move the summary line into a helper and use it in **both** returns of `sync` (the early budget return and the final one):

```python
def _read_error_summary(read_errors: int) -> list[str]:
    if read_errors <= 1:
        return []
    more = "; only the first 20 are listed" if read_errors > MAX_ITEM_WARNINGS else ""
    return [f"{read_errors} items could not be read{more}"]
```

   Both returns pass `tuple(warnings + _read_error_summary(read_errors))` as `warnings` and `read_errors` as the new field. Nothing else in `sync` changes.

## Spec — `zotcore/search.py`

Add `item_info(con, library, key) -> dict`: the `items` row as `{"key", "library", "title", "creators" (first 3), "n_authors", "year", "doi" (None when empty), "publication" (None when empty), "text_source", "flags" (list)}`, exactly the metadata keys `read_item` returns today. `read_item` builds its result as `{**item_info(con, lib, k), "total_chars": ..., "offset": ..., "next_offset": ..., "section": ..., "text": ..., "warnings": ...}`; its output does not change.

## Spec — `zotcore/annotations.py` (standard library only; reads the snapshot, never writes)

```python
TYPE_NAMES = {1: "highlight", 2: "note", 3: "image", 4: "ink", 5: "underline", 6: "text"}
```

- `snapshot_db(data_root) -> Path`: `Path(data_root) / "snapshot" / "current" / "zotero.sqlite"`.
- `open_current_snapshot(data_root) -> sqlite3.Connection | None`: `None` when that file does not exist, else `zdb.open_snapshot(path)` (read-only).
- `note_text(html) -> str`: replace `<br>`, `<br/>`, `<br />` and the closing tags `</p> </div> </li> </h1>…</h6> </tr> </blockquote> </pre>` (case-insensitive) with `"\n"`; remove every other tag (`<[^>]+>`); `html.unescape`; collapse whitespace **within** each line to single spaces; collapse 3 or more newlines to 2; strip. Example: `<div class="zotero-note znv1"><p>My own note &amp; idea</p><p>Second   line</p></div>` → `"My own note & idea\nSecond line"`.
- `load_annotations(con, library, key) -> tuple[list[dict], int] | None`. Returns `(entries, empty_omitted)`, or `None` when `library` is not in `zdb.libraries(con)` or the item key is not in that library (`SELECT itemID FROM items WHERE libraryID = ? AND key = ?`).

  **Annotations**, in this order:

  ```sql
  SELECT a.itemID, a.type, a.authorName, a.text, a.comment, a.color, a.pageLabel, a.isExternal
  FROM itemAttachments ia JOIN itemAnnotations a ON a.parentItemID = ia.itemID
  WHERE ia.parentItemID = ? AND ia.itemID NOT IN (SELECT itemID FROM deletedItems)
    AND a.itemID NOT IN (SELECT itemID FROM deletedItems)
  ORDER BY ia.itemID, a.sortIndex, a.itemID
  ```

  Strip `text` and `comment` (`None` → `""`). If both are empty, count it in `empty_omitted` and skip it. Otherwise the entry is, with keys only as listed:
  `{"type": TYPE_NAMES.get(type, "other"), "page": pageLabel or None, "text": … (only if non-empty), "comment": … (only if non-empty), "color": color or None, "author": …, "external": True (only if isExternal), "tags": sorted tag names (only if any)}`.
  Tags: `SELECT t.name FROM itemTags it JOIN tags t ON t.tagID = it.tagID WHERE it.itemID = ?` with the annotation's itemID.

  **Child notes** come after all annotations: `SELECT itemID, note FROM itemNotes WHERE parentItemID = ? AND itemID NOT IN (SELECT itemID FROM deletedItems) ORDER BY itemID` (with the paper's itemID). `note_text(note)`; empty → count in `empty_omitted`; otherwise `{"type": "item_note", "text": <text>, "author": …}`.

  **Author** of an annotation or note (`child_id` is its own itemID):
  1. external annotation (`isExternal` = 1): `authorName or None`;
  2. `library == "user"`: `"user"`;
  3. group library: `created_by` = `SELECT createdByUserID FROM groupItems WHERE itemID = ?` (only if a `groupItems` table exists). If `created_by` is not `None`: `"user"` when it equals the local user ID, else the name from `users` (`SELECT userID, name FROM users`, if that table exists), else `authorName`, else `str(created_by)`. If `created_by` is `None`: `authorName or None`.

  The local user ID: `SELECT value FROM settings WHERE setting = 'account' AND key = 'userID'` as `int`, or `None` when the `settings` table or the row is missing. Check tables with `SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?`: the test fixture has no `settings`, `users` or `groupItems` table unless a test creates it.
- `page_entries(entries, offset, max_chars) -> (page, next_offset)`: walk from `offset`; an entry's size is `len(text) + len(comment)` (missing = 0). Stop before an entry that would make the running total exceed `max_chars`, except that the first entry of a page is always taken. If that first entry alone is larger than `max_chars` and has a `text`, return a copy with `text` cut to `max_chars` and `"truncated": True`. `next_offset` is the index after the last entry taken, or `None` when nothing is left.

## Spec — `zotcore/citation.py` (the only module that opens a network connection: loopback to Zotero)

```python
ZOTERO_LOCAL_API = "http://127.0.0.1:23119/api"
STYLE = "apa"
TIMEOUT = 2.0
MAX_CHARS = 1000
```

- `approximate_citation(creators, year, title, publication, doi) -> str`. `names` = the part before the first `", "` of each non-empty creator string. Authors: none → `""`; one → `A`; two → `A & B`; three or more → `A et al.`. `when` = `(year)` or `(n.d.)`. Pieces: `"<authors> <when>"` (or just `<when>` without authors), then the stripped `title` and `publication` when non-empty; each of these pieces gets a `.` appended unless it already ends with `.`, `?` or `!`. Then `https://doi.org/<doi>` when there is a DOI (no dot after it). Join with single spaces. Examples are in the test.
- `html_to_text(value) -> str`: remove tags, `html.unescape`, collapse all whitespace to single spaces, strip.
- `item_url(base, library, key) -> str`: `f"{base.rstrip('/')}/users/0/items/{key}?{query}"` for `library == "user"`, else `.../groups/{library}/items/{key}?{query}` (quote `library` and `key` with `urllib.parse.quote(..., safe='')`), where `query = urllib.parse.urlencode({"format": "json", "include": "bib", "style": STYLE})`.
- `fetch_zotero_citation(base, library, key, *, timeout=TIMEOUT) -> str | None`. Use an opener **without proxies**: `urllib.request.build_opener(urllib.request.ProxyHandler({}))` (otherwise `HTTP_PROXY` or the macOS system proxy would receive the request). Send header `Zotero-API-Version: 3`. Any exception, a status other than 200, or invalid JSON → `None`. A one-element JSON list is unwrapped. The answer must be a dict whose `"key"` equals `key` and whose `"bib"` is a string; return `html_to_text(bib)[:MAX_CHARS]`, or `None` if that is empty.
- `citation(base, library, key, *, creators, year, title, publication, doi) -> dict`: if `base` is set and `fetch_zotero_citation` returns text: `{"text": text, "source": "zotero", "style": STYLE, "approximate": False}`. Otherwise `{"text": approximate_citation(...), "source": "index", "approximate": True}`.

## Spec — `zotcore/synctool.py`

`MAX_ITEM_LINES = 3`. `class SyncBusy(Exception)`.

`sync_lock(root)`: a context manager holding an exclusive, **non-blocking** OS lock on `<root>/sync.lock` (create `root` if needed). The OS releases it if the process dies, so a crash never leaves a stale lock. Use exactly this:

```python
@contextmanager
def sync_lock(root):
    path = Path(root) / "sync.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+b")
    try:
        try:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            raise SyncBusy("another sync is running") from e
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    finally:
        f.close()
```

`sync_step(settings, data_root, *, budget_seconds, clock=time.monotonic) -> dict`:

1. `t0 = clock()`. `found = resolve_data_dir(settings.zotero_data_dir)`; no path → `SearchError("no_zotero", "Zotero data directory not found.", "Run `hermes zotero doctor` in a terminal, or set zotero_data_dir.")`.
2. Inside `sync_lock(root)` (`SyncBusy` → `SearchError("busy", "Another Zotero sync is running.", "Try again in a minute.")`):
   - `info = load_info(root / "snapshot")`. **Reuse** it when `info` is not `None`, `Path(info.path).is_file()` and `not is_stale(info, found.path)`; otherwise `take_snapshot(found.path, root / "snapshot")` (`SnapshotError e` → `SearchError(e.code, e.message, "Try again in a minute.")`).
   - `corpus = MarkdownCorpus(settings.markdown_path) if settings.markdown_path else None`.
   - Open `Index(root / "index.sqlite")` (close it in `finally`) and call `sync(index, info.path, found.path, libraries=settings.libraries, corpus=corpus, batch_items=settings.sync_batch_items, budget_seconds=max(budget_seconds - (clock() - t0), 0.0), clock=clock)`. Read `last_sync = index.get_state("last_sync")` before closing.
3. Return, in this order:

```python
{"done": rep.done, "examined": rep.examined, "total": rep.examined + rep.remaining,
 "indexed": rep.indexed, "deleted": rep.deleted, "remaining": rep.remaining,
 "seconds": round(clock() - t0, 1), "eta_seconds": eta,
 "snapshot": {"taken_at": info.taken_at, "reused": reused},
 "index_last_sync": last_sync, "warnings": <capped>,
 "next": None if rep.done else "Call zotero_sync again to continue."}
```

   `eta = round(rep.remaining * rep.seconds / rep.indexed)` when not done and `rep.indexed > 0`, else `None`. Warnings: keep every line, except that only the first `MAX_ITEM_LINES` lines starting with `"item "` are kept (the summary line from `index.py` is always kept).

`sync` finishes at least one batch before it looks at the budget, and already-indexed items are skipped quickly (≈ 1.7 s for the whole real library), so every call of 5 s or more makes progress.

## Spec — `zotcore/cli.py`

- `hermes zotero sync`: after computing `root`, run the snapshot and sync **while holding** `sync_lock(root)` (move the existing body into a helper such as `_sync_locked(settings, root, data_dir)`). On `SyncBusy` print `Another sync is running; try again in a minute.` and return 1.
- `hermes zotero snapshot`: take the snapshot inside `sync_lock(root)` as well, with the same message and return code on `SyncBusy`.

## Spec — `zotcore/tools.py`

`tool_specs(settings_provider, data_root=None, citation_api=None)`. `citation_api` is the base URL of Zotero's local API; `None` (the default, and what every older test uses) means Zotero is never contacted. `zotero_status` and `zotero_search` stay exactly as they are.

**`zotero_read`** (same argument handling as task 07; new optional `mode`):

- `mode`: string argument; missing/empty → `"text"`; compared case-insensitively; anything other than `text` / `annotations` → `err("invalid_argument", "mode must be 'text' or 'annotations'")`.
- `max_chars` and `offset` are parsed and clamped exactly as in task 07, for both modes.
- Text mode: `payload = read_item(...)` as before. Annotations mode: `lib, k = find_item(con, key, library)` (same `not_found` / `ambiguous` errors) and `payload = item_info(con, lib, k)`.
- Both modes: `snap = open_current_snapshot(data_root())`; if not `None`, `loaded = load_annotations(snap, lib, k)` and close `snap` in `finally`.
- `payload["mode"] = mode`.
- Text mode adds `annotations_count`: `None` when there is no snapshot or `loaded` is `None`, else `len(entries)`.
- Annotations mode adds `total_annotations`, `offset` (the given offset or 0), `next_offset`, `annotations` (from `page_entries(entries, offset, max_chars)`), `empty_omitted`, `snapshot_taken_at` (`load_info(root / "snapshot").taken_at`, or `None`), and its own `warnings` list:
  - `query is not used in annotations mode` when a query was given;
  - `no Zotero snapshot yet; run `hermes zotero sync` in a terminal` when there is no snapshot;
  - `this item is not in the current Zotero snapshot` when `loaded` is `None`;
  - `offset <O> is past the last annotation (<N>)` when there are entries and `offset >= N`.
- Both modes: `payload["citation"] = citation(citation_api, lib, k, creators=payload["creators"], year=payload["year"], title=payload["title"], publication=payload["publication"], doi=payload["doi"])`. (`creators` holds at most 3 names; that is enough to decide "et al.".)

New descriptions and schema entries:

```python
READ_DESC = ("Zotero paper reader: read a bounded passage of one paper from the user's library, by item key, "
             "at the best match for a query or at a character offset, with a citation line. "
             "mode=annotations returns the user's own highlights, comments and notes on the paper instead. "
             "Use keys from zotero_search.")
SYNC_DESC = ("Zotero index update: add new and changed papers from the user's Zotero library to the local index. "
             "Each call runs for at most budget_seconds and the next call resumes; it returns progress and "
             "how many items remain. Use it when the user has added papers or zotero_status shows a stale snapshot.")
# add to READ_SCHEMA["properties"]:
    "mode": {"type": "string", "enum": ["text", "annotations"],
             "description": "'text' (default): the paper's text. 'annotations': the user's highlights, comments and notes."}
SYNC_SCHEMA = {"type": "object", "properties": {
    "budget_seconds": {"type": "integer", "minimum": 5, "maximum": 60,
                       "description": "Time limit for this call in seconds (default set by the user)."}}}
```

**`zotero_sync`** (registered after `zotero_read`): wrapped with `safe`; call `settings_provider()` first; `data_root is None` → `err("unavailable", "plugin data dir unavailable")`. `budget_seconds` is an integer argument (task 07's `_int_arg`) defaulting to `settings.sync_tool_budget_seconds`, clamped to 5–60. Parse it **inside** the same `try` as the call, so a bad value becomes `invalid_argument`, not `internal_error`: `try: budget = ...; return ok(**sync_step(settings, Path(data_root()), budget_seconds=budget))` / `except SearchError as e: return err(e.code, e.message, e.hint)`.

## Spec — `__init__.py` and `plugin.yaml`

- `__init__.py` (inside the `if __package__:` block): `from .zotcore.citation import ZOTERO_LOCAL_API` and pass `citation_api=ZOTERO_LOCAL_API` to `tools.tool_specs(...)`.
- `plugin.yaml`: `provides_tools` lists `zotero_status`, `zotero_search`, `zotero_read`, `zotero_sync`.

## Acceptance test (copy verbatim, then verify the checksum)

| File | SHA-256 |
| --- | --- |
| `tests/test_08_annotations_citation_sync.py` | `5d6940a227d2ba8ce33cf54efca3c8df3c125361adcf2ab77459024554c78d09` |

The tests build a small library with annotations, child notes and a group, take a snapshot and sync it the way `hermes zotero sync` does. The citation tests start a fake Zotero on `127.0.0.1` (a random port) and set `HTTP_PROXY` to a dead address, so a request that goes through a proxy fails. If macOS asks whether Python may accept incoming network connections, choose Allow: the connections stay on this Mac.

### `tests/test_08_annotations_citation_sync.py`

```python
import argparse
import hashlib
import json
import shutil
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

import zotcore.index as index_module
from tests.zfixture import ZoteroFixture
from zotcore import cli, tools
from zotcore.citation import approximate_citation, fetch_zotero_citation
from zotcore.index import Index, sync
from zotcore.settings import Settings
from zotcore.snapshot import take_snapshot
from zotcore.synctool import sync_lock, sync_step

ME, COLLEAGUE = 1111111, 2222222
ACCOUNT_DDL = """
CREATE TABLE settings (setting TEXT, key TEXT, value, PRIMARY KEY (setting, key));
CREATE TABLE users (userID INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE groupItems (itemID INTEGER PRIMARY KEY, createdByUserID INT, lastModifiedByUserID INT);
"""
BIB = ('<div class="csl-bib-body" style="line-height: 2; margin-left: 2em; text-indent:-2em;">\n'
       '  <div class="csl-entry">Dixon, S. J., &amp; Stockwell, B. R. (2025). Ferroptosis in adipocytes. '
       '<i>Cell Metabolism</i>, <i>37</i>(2), 100–110. https://doi.org/10.1000/ferro.1</div>\n</div>')
BIB_TEXT = ("Dixon, S. J., & Stockwell, B. R. (2025). Ferroptosis in adipocytes. Cell Metabolism, 37(2), 100–110. "
            "https://doi.org/10.1000/ferro.1")


def annotate(z, attachment, key, text, *, sort, page, kind=1, comment="", color="#ffd400", external=False,
             author_name=None, created_by=None, tags=()):
    item_id = z.add_annotation(attachment, key, text, comment=comment, page_label=page, color=color, kind=kind)
    z.con.execute("UPDATE itemAnnotations SET sortIndex = ?, isExternal = ?, authorName = ? WHERE itemID = ?",
                  (sort, int(external), author_name, item_id))
    if created_by is not None:
        z.con.execute("INSERT INTO groupItems (itemID, createdByUserID) VALUES (?, ?)", (item_id, created_by))
    for tag in tags:
        z.con.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
        tag_id = z.con.execute("SELECT tagID FROM tags WHERE name = ?", (tag,)).fetchone()[0]
        z.con.execute("INSERT INTO itemTags VALUES (?, ?, 0)", (item_id, tag_id))
    return item_id


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lib08")
    z = ZoteroFixture(tmp / "Zotero")
    z.con.executescript(ACCOUNT_DDL)
    z.con.execute("INSERT INTO settings VALUES ('account', 'userID', ?)", (ME,))
    z.con.executemany("INSERT INTO users VALUES (?, ?)", [(ME, "me_myself"), (COLLEAGUE, "colleague_k")])
    group = z.add_group(4805701, "Ancestralize")

    i = z.add_item("ANNOT001", fields={"title": "Ferroptosis in adipocytes", "DOI": "10.1000/ferro.1",
                                       "date": "2025-00-00 2025", "publicationTitle": "Cell Metabolism"},
                   creators=[("Scott", "Dixon", "author"), ("Brent", "Stockwell", "author")])
    a = z.add_attachment(i, "PDFA0001", ft_text="Ferroptosis is an iron-dependent cell death.\n\n" * 20)
    b = z.add_attachment(i, "PDFA0002", ft_text=None)  # a supplement PDF
    # inserted out of order: the output follows attachment, then sortIndex
    annotate(z, a, "ANN00004", None, sort="00003|000001|00001", page="4", kind=2, comment="Compare with Smith 2021",
             tags=("Methods", "For review"))
    annotate(z, b, "ANN00007", "Supplementary figure shows the same.", sort="00000|000001|00001", page="S1",
             color="#5fb236")
    annotate(z, a, "ANN00002", "Lipid peroxides accumulate in adipocytes.", sort="00002|000010|00020", page="3",
             kind=5, color="#f19837")
    z.trash(annotate(z, a, "ANN00006", "Deleted highlight", sort="00000|000001|00001", page="1"))
    annotate(z, a, "ANN00001", "Ferroptosis requires loss of GPX4 activity.", sort="00001|000100|00050", page="2",
             comment="Key mechanism for the review")
    annotate(z, a, "ANN00005", "Imported from the PDF file.", sort="00004|000001|00001", page="5", external=True,
             author_name="Reviewer 2")
    annotate(z, a, "ANN00003", None, sort="00002|000500|00100", page="3", kind=3)  # image: nothing to quote
    z.add_note(i, "NOTE0001", html='<div class="zotero-note znv1"><p>My own note &amp; idea</p><p>Second   line</p></div>')
    z.add_note(i, "NOTE0002", html="<p> </p>")
    z.trash(z.add_note(i, "NOTE0003", html="<p>Deleted note</p>"))

    i = z.add_item("GANNOT01", library_id=group, fields={"title": "Group paper", "date": "2024-00-00 2024"},
                   creators=[("Maria", "Lindqvist", "author"), ("Peter", "Novak", "author"), ("Ann", "Other", "author")])
    g = z.add_attachment(i, "GPDF0001", ft_text="Group paper text about ketone bodies.\n\n" * 20)
    annotate(z, g, "GANN0001", "Group highlight by a colleague.", sort="00006|000001|00001", page="7",
             created_by=COLLEAGUE)
    annotate(z, g, "GANN0002", "My highlight in the group.", sort="00007|000001|00001", page="8", created_by=ME)
    annotate(z, g, "GANN0003", "Unknown creator with a name.", sort="00008|000001|00001", page="9",
             author_name="Visitor")
    note = z.add_note(i, "GNOTE001", html="<p>Colleague note</p>")
    z.con.execute("INSERT INTO groupItems (itemID, createdByUserID) VALUES (?, ?)", (note, COLLEAGUE))

    i = z.add_item("MANYANN1", fields={"title": "Many highlights"})
    m = z.add_attachment(i, "PDFM0001", ft_text="Many highlights body text.\n\n" * 20)
    for n in range(30):
        annotate(z, m, f"MANY{n:04d}", f"Highlight {n:02d} " + "x" * 87, sort=f"{n:05d}|000000|00000", page=str(n + 1))

    i = z.add_item("BIGNOTE1", fields={"title": "Long note"})
    z.add_note(i, "BIGN0001", html="<p>" + "y" * 5000 + "</p>")
    i = z.add_item("PLAIN001", fields={"title": "No annotations"})
    z.add_attachment(i, "PDFP0001", ft_text="Plain body text.\n\n" * 20)

    root = tmp / "pd"
    info = take_snapshot(z.data_dir, root / "snapshot")
    index = Index(root / "index.sqlite")
    rep = sync(index, info.path, z.data_dir, libraries=("user", "4805701"))
    assert rep.done and rep.indexed == 5
    index.close()
    z.close()
    return root


class FakeZotero(BaseHTTPRequestHandler):
    """Answers like Zotero's local API (server_localAPI.js); 404 for unknown items."""

    def do_GET(self):
        self.server.seen.append((self.path, self.headers.get("Host")))
        if self.server.disabled:
            return self._send(403, "text/plain", "Local API is not enabled")
        path = urlsplit(self.path).path
        known = {"/api/users/0/items/ANNOT001": "ANNOT001", "/api/groups/4805701/items/GANNOT01": "GANNOT01",
                 "/api/users/0/items/PLAIN001": "WRONGKEY"}  # an answer for another item must not be used
        if path not in known:
            return self._send(404, "text/plain", "Not found")
        body = {"key": known[path], "version": 5, "library": {"type": "user", "id": 0}, "meta": {}, "bib": BIB}
        self._send(200, "application/json", json.dumps(body, indent=4))

    def _send(self, status, ctype, text):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def zotero_api(monkeypatch):
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")  # a proxy that is never there: loopback must bypass it
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeZotero)
    server.daemon_threads = True
    server.seen, server.disabled = [], False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def base_url(server):
    return f"http://127.0.0.1:{server.server_address[1]}/api"


def read_handler(root, citation_api=None, settings=None):
    settings = settings or Settings(libraries=("user", "4805701"))
    specs = {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root, citation_api=citation_api)}
    return specs["zotero_read"].handler


def call(handler, **args):
    out = handler(args)
    assert isinstance(out, str)
    return json.loads(out)


# ---------- registration ------------------------------------------------------------------------------

def test_sync_tool_is_registered_and_read_has_mode(plugin_module, fake_ctx):
    plugin_module.register(fake_ctx)
    assert {"zotero_status", "zotero_search", "zotero_read", "zotero_sync"} == set(fake_ctx.tools)
    mode = fake_ctx.tools["zotero_read"]["schema"]["parameters"]["properties"]["mode"]
    assert mode["enum"] == ["text", "annotations"]
    props = fake_ctx.tools["zotero_sync"]["schema"]["parameters"]["properties"]
    assert set(props) == {"budget_seconds"}
    assert "Zotero" in fake_ctx.tools["zotero_sync"]["schema"]["description"][:60]
    assert "annotations" in fake_ctx.tools["zotero_read"]["schema"]["description"]


# ---------- annotations mode --------------------------------------------------------------------------

def test_annotations_are_the_users_words_in_reading_order(lib):
    read = read_handler(lib)
    data = call(read, key="ANNOT001", mode="annotations")
    assert data["ok"] is True and data["mode"] == "annotations" and data["key"] == "ANNOT001"
    assert data["title"] == "Ferroptosis in adipocytes" and data["doi"] == "10.1000/ferro.1"
    assert data["annotations"] == [
        {"type": "highlight", "page": "2", "text": "Ferroptosis requires loss of GPX4 activity.",
         "comment": "Key mechanism for the review", "color": "#ffd400", "author": "user"},
        {"type": "underline", "page": "3", "text": "Lipid peroxides accumulate in adipocytes.", "color": "#f19837",
         "author": "user"},
        {"type": "note", "page": "4", "comment": "Compare with Smith 2021", "color": "#ffd400", "author": "user",
         "tags": ["For review", "Methods"]},
        {"type": "highlight", "page": "5", "text": "Imported from the PDF file.", "color": "#ffd400",
         "author": "Reviewer 2", "external": True},
        {"type": "highlight", "page": "S1", "text": "Supplementary figure shows the same.", "color": "#5fb236",
         "author": "user"},
        {"type": "item_note", "text": "My own note & idea\nSecond line", "author": "user"},
    ]
    assert data["total_annotations"] == 6 and data["empty_omitted"] == 2  # the image and the blank note
    assert data["offset"] == 0 and data["next_offset"] is None and data["warnings"] == []
    assert data["snapshot_taken_at"].endswith("Z")


def test_group_annotations_name_their_author(lib):
    read = read_handler(lib)
    data = call(read, key="GANNOT01", mode="annotations")
    assert [(a.get("text"), a["author"]) for a in data["annotations"]] == [
        ("Group highlight by a colleague.", "colleague_k"),
        ("My highlight in the group.", "user"),
        ("Unknown creator with a name.", "Visitor"),
        ("Colleague note", "colleague_k"),
    ]


def test_annotations_paging_and_caps(lib):
    read = read_handler(lib)
    texts, offset, pages = [], 0, 0
    while offset is not None:
        data = call(read, key="MANYANN1", mode="annotations", offset=offset, max_chars=1000)
        assert len(data["annotations"]) == 10 and data["total_annotations"] == 30
        texts += [a["text"] for a in data["annotations"]]
        offset, pages = data["next_offset"], pages + 1
    assert pages == 3 and texts == [f"Highlight {n:02d} " + "x" * 87 for n in range(30)]
    assert len(call(read, key="MANYANN1", mode="annotations")["annotations"]) == 30  # default 4000 chars: all fit
    data = call(read, key="BIGNOTE1", mode="Annotations", max_chars=1000)  # mode is case-insensitive
    note = data["annotations"][0]
    assert note["type"] == "item_note" and note["text"] == "y" * 1000 and note["truncated"] is True
    assert data["next_offset"] is None
    data = call(read, key="MANYANN1", mode="annotations", offset=40)
    assert data["annotations"] == [] and data["next_offset"] is None and data["warnings"]


def test_annotations_edge_cases(lib, tmp_path):
    read = read_handler(lib)
    data = call(read, key="PLAIN001", mode="annotations")
    assert data["annotations"] == [] and data["total_annotations"] == 0 and data["warnings"] == []
    data = call(read, key="ANNOT001", mode="annotations", query="GPX4")
    assert len(data["annotations"]) == 6 and any("query" in w for w in data["warnings"])
    assert call(read, key="ANNOT001", mode="pdf")["error"]["code"] == "invalid_argument"
    assert call(read, key="NOSUCHKY", mode="annotations")["error"]["code"] == "not_found"
    bare = tmp_path / "bare"  # an index but no snapshot
    bare.mkdir()
    shutil.copy(lib / "index.sqlite", bare / "index.sqlite")
    data = call(read_handler(bare), key="ANNOT001", mode="annotations")
    assert data["ok"] is True and data["annotations"] == [] and data["snapshot_taken_at"] is None
    assert any("sync" in w for w in data["warnings"])
    assert call(read_handler(bare), key="ANNOT001")["annotations_count"] is None


def test_text_mode_reports_annotation_count(lib):
    read = read_handler(lib)
    data = call(read, key="ANNOT001", max_chars=300)
    assert data["mode"] == "text" and data["annotations_count"] == 6 and data["text"].startswith("Ferroptosis is")
    assert call(read, key="PLAIN001")["annotations_count"] == 0
    assert call(read, key="GANNOT01")["annotations_count"] == 4


def test_reads_do_not_modify_index_or_snapshot(lib, zotero_api):
    paths = [lib / "index.sqlite", lib / "snapshot" / "current" / "zotero.sqlite"]
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    read = read_handler(lib, base_url(zotero_api))
    for key in ("ANNOT001", "GANNOT01", "MANYANN1", "PLAIN001"):
        call(read, key=key)
        call(read, key=key, mode="annotations")
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths] == before


# ---------- citation line -----------------------------------------------------------------------------

def test_approximate_citation_format():
    assert approximate_citation(["Dixon, Scott", "Stockwell, Brent"], 2025, "Ferroptosis in adipocytes",
                                "Cell Metabolism", "10.1000/ferro.1") == (
        "Dixon & Stockwell (2025). Ferroptosis in adipocytes. Cell Metabolism. https://doi.org/10.1000/ferro.1")
    assert approximate_citation(["World Health Organization"], None, "Is fat bad?", "", "") == (
        "World Health Organization (n.d.). Is fat bad?")
    assert approximate_citation(["Lindqvist, Maria", "Novak, Peter", "Other, Ann"], 2024, "Group paper", None, None) == (
        "Lindqvist et al. (2024). Group paper.")
    assert approximate_citation([], 2020, "Untitled report.", "WHO", "") == "(2020). Untitled report. WHO."


def test_citation_is_approximate_without_zotero(lib):
    data = call(read_handler(lib), key="ANNOT001")  # citation_api=None: Zotero is never called
    assert data["citation"] == {
        "text": "Dixon & Stockwell (2025). Ferroptosis in adipocytes. Cell Metabolism. https://doi.org/10.1000/ferro.1",
        "source": "index", "approximate": True}
    port = socket.socket()
    port.bind(("127.0.0.1", 0))
    closed = f"http://127.0.0.1:{port.getsockname()[1]}/api"
    port.close()  # nothing listens here: like Zotero being closed
    data = call(read_handler(lib, closed), key="GANNOT01", mode="annotations")
    assert data["citation"]["approximate"] is True and data["citation"]["text"] == "Lindqvist et al. (2024). Group paper."


def test_citation_from_zotero_local_api(lib, zotero_api):
    read = read_handler(lib, base_url(zotero_api))
    data = call(read, key="ANNOT001")
    assert data["citation"] == {"text": BIB_TEXT, "source": "zotero", "style": "apa", "approximate": False}
    path, host = zotero_api.seen[-1]
    url = urlsplit(path)
    assert url.path == "/api/users/0/items/ANNOT001" and host == f"127.0.0.1:{zotero_api.server_address[1]}"
    assert parse_qs(url.query) == {"format": ["json"], "include": ["bib"], "style": ["apa"]}
    data = call(read, key="GANNOT01", mode="annotations")
    assert data["citation"]["source"] == "zotero"
    assert urlsplit(zotero_api.seen[-1][0]).path == "/api/groups/4805701/items/GANNOT01"
    data = call(read, key="PLAIN001")  # Zotero answers for a different key: fall back
    assert data["citation"]["source"] == "index" and data["citation"]["text"] == "(n.d.). No annotations."
    assert call(read, key="MANYANN1")["citation"]["source"] == "index"  # Zotero answers 404
    zotero_api.disabled = True  # 403 "Local API is not enabled"
    assert call(read, key="ANNOT001")["citation"]["approximate"] is True


def test_citation_fetch_has_a_timeout():
    class Slow(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(1.5)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        t = time.monotonic()
        assert fetch_zotero_citation(base_url(server), "user", "ANNOT001", timeout=0.3) is None
        assert time.monotonic() - t < 1.2
    finally:
        server.shutdown()
        server.server_close()


# ---------- zotero_sync -------------------------------------------------------------------------------

@pytest.fixture
def zlib(tmp_path):
    z = ZoteroFixture(tmp_path / "Zotero")
    for n in range(9):
        i = z.add_item(f"SYNC{n:04d}", fields={"title": f"Sync paper {n}"})
        z.add_attachment(i, f"SPDF{n:04d}", ft_text=f"Body of sync paper number{n} on brown fat.\n\n" * 10)
    settings = Settings(zotero_data_dir=str(z.data_dir), sync_batch_items=2)
    yield z, settings, tmp_path / "pd"
    z.close()


def sync_handler(settings, root):
    specs = {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root)}
    return specs["zotero_sync"].handler


def test_sync_tool_indexes_then_reuses_the_snapshot(zlib):
    z, settings, root = zlib
    run = sync_handler(settings, root)
    data = call(run)
    assert data["ok"] is True and data["done"] is True and data["indexed"] == 9 and data["remaining"] == 0
    assert data["total"] == 9 and data["eta_seconds"] is None and data["next"] is None
    assert data["snapshot"]["reused"] is False and data["index_last_sync"].endswith("Z")
    data = call(run, budget_seconds=5)
    assert data["done"] is True and data["indexed"] == 0 and data["snapshot"]["reused"] is True
    i = z.add_item("SYNC0100", fields={"title": "A new paper on beige adipocytes"})
    z.add_attachment(i, "SPDF0100", ft_text="Beige adipocytes appear after cold exposure.\n\n" * 10)
    data = call(run, budget_seconds="20")
    assert data["done"] is True and data["indexed"] == 1 and data["snapshot"]["reused"] is False
    search = {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root)}["zotero_search"].handler
    assert [h["key"] for h in call(search, query="beige adipocytes")["hits"]] == ["SYNC0100"]


def test_sync_step_is_time_boxed_and_resumes(zlib, monkeypatch):
    z, settings, root = zlib
    work = {"seconds": 0}
    real_upsert = index_module.Index.upsert

    def slow_upsert(self, *args, **kwargs):
        work["seconds"] += 1  # indexing one item "takes" a second; nothing else does
        return real_upsert(self, *args, **kwargs)

    monkeypatch.setattr(index_module.Index, "upsert", slow_upsert)
    clock = lambda: work["seconds"]
    first = sync_step(settings, root, budget_seconds=3, clock=clock)
    assert first["done"] is False and 0 < first["examined"] < 9 and first["remaining"] == 9 - first["examined"]
    assert first["total"] == 9 and "again" in first["next"] and first["index_last_sync"] is None
    assert first["eta_seconds"] is None or first["eta_seconds"] >= 0
    steps = [first]
    while not steps[-1]["done"]:
        assert len(steps) < 20
        steps.append(sync_step(settings, root, budget_seconds=3, clock=clock))
    assert steps[-1]["remaining"] == 0 and steps[-1]["index_last_sync"].endswith("Z")
    assert sum(s["indexed"] for s in steps) == 9
    assert all(s["snapshot"]["reused"] for s in steps[1:])  # Zotero did not change between the calls


def test_sync_tool_arguments_and_errors(zlib, tmp_path):
    z, settings, root = zlib
    run = sync_handler(settings, root)
    assert call(run, budget_seconds="abc")["error"]["code"] == "invalid_argument"
    assert call(run, budget_seconds=1)["done"] is True  # clamped up to 5 seconds
    missing = Settings(zotero_data_dir=str(tmp_path / "no-zotero-here"))
    data = call(sync_handler(missing, tmp_path / "pd2"))
    assert data["ok"] is False and data["error"]["code"] == "no_zotero" and "doctor" in data["error"]["hint"]
    specs = {s.name: s for s in tools.tool_specs(lambda: settings)}  # no data_root
    assert call(specs["zotero_sync"].handler)["ok"] is False

    def broken():
        raise RuntimeError("kaboom")
    specs = {s.name: s for s in tools.tool_specs(broken, data_root=lambda: root)}
    assert call(specs["zotero_sync"].handler)["error"]["code"] == "internal_error"


def test_only_one_sync_at_a_time(zlib, capsys):
    z, settings, root = zlib
    with sync_lock(root):
        data = call(sync_handler(settings, root))
        assert data["ok"] is False and data["error"]["code"] == "busy"
        parser = argparse.ArgumentParser(prog="hermes zotero")
        cli.setup_parser(parser)
        assert cli.run(parser.parse_args(["sync"]), settings, data_root=lambda: root) == 1
        assert "Another sync is running" in capsys.readouterr().out
    assert call(sync_handler(settings, root))["done"] is True  # the lock is released afterwards
    assert cli.run(parser.parse_args(["sync"]), settings, data_root=lambda: root) == 0


def test_read_errors_are_reported_by_partial_runs_and_capped_in_the_tool(zlib, monkeypatch):
    z, settings, root = zlib

    def broken(item, data_dir, corpus=None):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(index_module, "choose_text", broken)
    index = Index(root / "partial.sqlite")
    try:
        rep = sync(index, z.db_path, z.data_dir, batch_items=2, budget_seconds=0)
        assert rep.done is False and rep.examined == 2 and rep.read_errors == 2
        assert any(w.startswith("2 items could not be read") for w in rep.warnings)
    finally:
        index.close()
    data = call(sync_handler(settings, root))
    assert data["done"] is True and data["indexed"] == 9
    item_lines = [w for w in data["warnings"] if w.startswith("item ")]
    assert len(item_lines) == 3 and any(w.startswith("9 items could not be read") for w in data["warnings"])
```

## Commands

```bash
.venv/bin/python -m pytest                          # expect: 122 passed
shasum -a 256 tests/test_08_annotations_citation_sync.py
```

Finish with `tasks/08-report.md` and one commit: `task 08: annotations, citation line, zotero_sync`.

## Live check (Gábor, in the same or a new Claude Code session, after the commit)

Expected values come from the reference implementation on your snapshot of 6 Nov, 12:32 CET. Small differences are fine if you changed annotations since.

1. **Direct check, Zotero closed.** Quit Zotero, then run this from the repo and paste the output into the report under `## Live check`. It only reads your index and snapshot; the sync part writes to a throw-away folder in `/tmp` (group library only, about 150 MB) and deletes it at the end.

```bash
.venv/bin/python - <<'EOF'
import json, shutil, tempfile, time
from pathlib import Path
from zotcore import tools
from zotcore.citation import ZOTERO_LOCAL_API
from zotcore.settings import Settings
from zotcore.synctool import sync_step
root = Path.home() / ".hermes/plugin-data/hermes-zotero"
S = Settings(libraries=("user", "4805701"))
read = {s.name: s.handler for s in tools.tool_specs(lambda: S, data_root=lambda: root,
                                                     citation_api=ZOTERO_LOCAL_API)}["zotero_read"]
def run(**args):
    t = time.time(); out = read(args); d = json.loads(out)
    print(f"\nzotero_read {args}  {time.time() - t:.2f}s  {len(out)} chars")
    if not d["ok"]: print(d); return
    keys = ("mode", "annotations_count", "total_annotations", "empty_omitted", "next_offset")
    print({k: d[k] for k in keys if k in d})
    if d["mode"] == "annotations":
        who = {}
        for a in d["annotations"]: who[a["author"]] = who.get(a["author"], 0) + 1
        print("on this page:", len(d["annotations"]), "by author:", who)
        print("first:", json.dumps(d["annotations"][:1], ensure_ascii=False)[:300])
    print("citation:", d["citation"])
run(key="Q3K5IWZH", mode="annotations")
run(key="J2CWD6IV", mode="annotations")
run(key="J2CWD6IV", mode="annotations", offset=31)
run(key="GZ66NGZE", mode="annotations")
run(key="Q3K5IWZH", max_chars=500)
run(key="RMRFLJX6", query="ferroptosis", max_chars=500)
tmp = Path(tempfile.mkdtemp(prefix="hz-sync-check-"))
G = Settings(libraries=("4805701",), sync_batch_items=50, markdown_path=str(Path.home() / "Zotero-Markdown"))
try:
    for n in range(1, 30):
        r = sync_step(G, tmp, budget_seconds=1 if n == 1 else 2)
        print(f"sync step {n}: done={r['done']} examined={r['examined']}/{r['total']} indexed={r['indexed']} "
              f"eta={r['eta_seconds']} reused={r['snapshot']['reused']} {r['seconds']}s warnings={r['warnings']}")
        if r["done"]: break
finally:
    shutil.rmtree(tmp, ignore_errors=True)
EOF
```

Expected (Zotero closed, so every citation is `"source": "index", "approximate": true`):

| Call | Expected |
| --- | --- |
| Q3K5IWZH annotations | 19 entries, all `author: user`, `empty_omitted` 0, `next_offset` None; citation "Kotanidis et al. (2025). Managing Obesity. New England Journal of Medicine. https://doi.org/10.1056/nejmclde2413003" |
| J2CWD6IV annotations (group) | `total_annotations` 41, `empty_omitted` 7 (image annotations), 31 on the first page, `next_offset` 31. Author: the group member's Zotero user name, **not** `user` (you did not make these) |
| J2CWD6IV, offset 31 | 10 entries, `next_offset` None |
| GZ66NGZE | `total_annotations` 0, `empty_omitted` 11 (image annotations only) |
| Q3K5IWZH text | `mode: text`, `annotations_count` 19 |
| RMRFLJX6 text | `annotations_count` 0; citation "Bell et al. (2024). Ironing out the role of ferroptosis in immunity. Immunity. https://doi.org/10.1016/j.immuni.2024.03.019" |
| sync steps | step 1: `done=False`, examined 50 of about 693, `reused=False`; later steps `reused=True` and examined grows; the last step `done=True`. Each step takes about its budget plus one batch |

Every read should take well under a second.

2. **Direct check, Zotero open.** Open Zotero. In Zotero's Settings → Advanced, tick **"Allow other applications on this computer to communicate with Zotero"** (this switches on Zotero's local API; it is off by default, and while it is on, any program on your Mac can read your library through it). Run only the six `run(...)` lines again (delete the sync part). Expected: `citation` now has `"source": "zotero", "style": "apa", "approximate": false` and an APA reference written by Zotero. If it still says `index`, paste the output of `curl -s -i "http://127.0.0.1:23119/api/users/0/items/Q3K5IWZH?format=json&include=bib&style=apa" | head -30` into the report. Keep the setting on or off afterwards, as you prefer; the plugin works either way.

3. **Through Hermes.** `hermes gateway restart` first (Hermes keeps the old code otherwise). Then:
   - `hermes -z "What did I highlight in the NEJM paper 'Managing Obesity' in my Zotero library? Quote my highlights with page numbers and give the citation."`
   - `hermes -z "Bring my Zotero index up to date."`

   Paste the tool calls (names and arguments, from `~/.hermes/state.db` as in task 07) and the `tool … completed` lines from `~/.hermes/logs/agent.log`. Expected: `zotero_search` then `zotero_read` with `mode: annotations` for the first; `zotero_sync` returning `done: true` within about 10 s for the second (your index is already complete).

## Out of scope

The skill and tool-description tuning (task 09); README, disclosures (the loopback call to Zotero must be listed there) and the `homepage` placeholder in `plugin.yaml` (task 10). `zotero_status` still reports `stage: "scaffold"`; task 09 fixes it. Do not index annotations or make them searchable.
