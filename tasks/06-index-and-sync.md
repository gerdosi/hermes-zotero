# Task 06 — The search index and `hermes zotero sync`

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code |
| Reasoning | **high**: transactions, resumable state and deletions. Set it right before pasting the prompt and check the report's first lines. |
| Budget | ≤ 60 tool calls |
| Depends on | task 05 committed |
| Done when | `.venv/bin/python -m pytest` shows **85 passed** (73 old + 12 new), checksums match, report committed |

## Goal

Build the plugin's own full-text index, an SQLite FTS5 database in the plugin data folder, from the snapshot plus the chosen texts. Add `hermes zotero sync`, which takes a snapshot and updates the index incrementally, and report the index in `zotero_status`. A sync must be safe to interrupt at any point and resume on the next run.

## Facts (reference implementation on Gábor's real library, 6 Nov 2026)

- Full first build: about 70 s for 19,290 items. It produced 1,067,137 passages and a 3.5 GB index file. The run was killed partway through and resumed correctly.
- Re-sync with no changes: 1.7 s. Queries with `bm25()` and `snippet()` on that index: under 0.3 s.
- FTS5 `UNINDEXED` columns can be filtered but not looked up quickly. So a small regular table (`passage_map`) maps each passage `rowid` to its item, which makes deleting an item's passages fast.

## Files

```
create  zotcore/index.py
create  tests/test_06_index.py   (verbatim, below)
modify  zotcore/cli.py           (new `sync` subcommand)
modify  zotcore/tools.py         (status gains an `index` block)
create  tasks/06-report.md
```

## Spec — `zotcore/index.py`

Schema, created with `CREATE ... IF NOT EXISTS` on every open:

```sql
CREATE TABLE IF NOT EXISTS items (library TEXT NOT NULL, item_key TEXT NOT NULL, item_id INTEGER, item_type TEXT, title TEXT,
  creators TEXT, year INTEGER, date TEXT, doi TEXT, publication TEXT, abstract TEXT, collections TEXT, tags TEXT, date_added TEXT,
  modified TEXT, text_source TEXT, text_path TEXT, flags TEXT, signature TEXT, n_passages INTEGER, PRIMARY KEY (library, item_key));
CREATE INDEX IF NOT EXISTS items_doi ON items(doi);
CREATE TABLE IF NOT EXISTS passage_map (rowid INTEGER PRIMARY KEY, library TEXT NOT NULL, item_key TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS passage_map_item ON passage_map(library, item_key);
CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(title, section, body, library UNINDEXED, item_key UNINDEXED,
  start UNINDEXED, end UNINDEXED, tokenize='porter unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
```

`creators`, `collections`, `tags` and `flags` are JSON lists (`json.dumps(list(...))`).

```python
@dataclass(frozen=True)
class SyncReport:
    examined: int; indexed: int; deleted: int; remaining: int; done: bool; seconds: float; warnings: tuple[str, ...]

class Index:
    def __init__(self, path): ...      # creates parent folders; sqlite3.connect(..., isolation_level=None); PRAGMA journal_mode=WAL; schema
    con: sqlite3.Connection            # public: tests query passages directly
    def close(self): ...
    def transaction(self): ...         # context manager: BEGIN ... COMMIT, ROLLBACK on any exception
    def indexed(self, library) -> dict[str, tuple[str, str]]   # item_key -> (modified, signature)
    def libraries(self) -> list[str]   # libraries present in the index
    def upsert(self, item, text, passages): ...   # replaces the item row and ALL its passages
    def delete(self, library, keys) -> int: ...   # number of item rows removed (with their passages)
    def get_state(self, key, default=None): ...
    def set_state(self, key, value): ...
    def counts(self) -> dict          # {"items", "passages", "libraries": {lib: n}, "by_source": {src: n}, "flags": {flag: n}, "last_sync"}

def sync(index, snapshot_path, data_dir, *, libraries=("user",), corpus=None, batch_items=200,
         budget_seconds=None, clock=time.monotonic, progress=None) -> SyncReport
```

`upsert`: delete the item's old passages via `passage_map` (rowids, in chunks of 500), then `INSERT OR REPLACE` the item row. Then for each passage, insert a `passage_map` row and insert the FTS row with **the same rowid**. Columns: title = item title, section, body = passage text, library, item_key, start, end.

`sync` algorithm:

1. `t0 = clock()`. Open the snapshot with `open_snapshot`. Requested libraries that Zotero doesn't have produce the warning `library <name> not found in Zotero; skipped`; duplicates are ignored.
2. `refs = list_items(con, wanted)`. Load `index.indexed(lib)` once per wanted library.
3. In one transaction, delete every item of any library in the index that is no longer wanted, plus every indexed item no longer in `refs` (trashed or deleted in Zotero). Count them as `deleted`.
4. Walk `refs` in batches of `batch_items`. Per batch, `load_items` and open one transaction. For each item, compute `text_signature`; if `(item.modified, signature)` equals what the index has, skip it. Otherwise `choose_text`, `split_passages` and `upsert`, then `indexed += 1`. After the batch, `examined += len(batch)` and call `progress(examined, total)` if given.
5. After a batch, if `budget_seconds` is set, items remain and `clock() - t0 >= budget_seconds`, return `done=False, remaining=total - examined`. Do **not** set `last_sync`.
6. When all batches are done, set state `last_sync` to UTC `%Y-%m-%dT%H:%M:%SZ` and return `done=True, remaining=0`. `seconds = clock() - t0`.
7. Close the snapshot connection in `finally`. Resuming needs no saved cursor: the next run re-examines everything, and unchanged items are skipped cheaply.

## Spec — integration

`zotcore/cli.py`: new subcommand `sync` ("Snapshot Zotero and update the search index").

- If no data directory is found, print the same hint as `snapshot` and return **2**. If `data_root` is `None`, return 1.
- `root = Path(data_root())`. Take a snapshot into `root/"snapshot"`; on `SnapshotError`, print `snapshot failed (<code>): <message>` and return 1. Otherwise print `Snapshot: <path> (attempts N)`.
- `corpus = MarkdownCorpus(settings.markdown_path)` if `markdown_path` is set, else `None`. Open `Index(root/"index.sqlite")` and call `sync(..., libraries=settings.libraries, corpus=corpus, batch_items=settings.sync_batch_items, progress=...)`. Progress prints `  <done>/<total> items examined` at roughly every 10%.
- Print each warning as `  warning: ...`, then exactly `Sync: indexed {indexed}, deleted {deleted}, examined {examined} in {seconds:.1f}s`, then `Index: {items} items, {passages} passages; text sources {by_source}; flags {flags}`. Close the index in `finally`. Return 0.

`zotcore/tools.py` (`zotero_status`): add an `index` key. It is `None` unless `data_root` is given and `data_root()/"index.sqlite"` **already exists**; then it is `Index(...).counts()`, with the index closed afterwards. Status must never create the index file. Keep every existing key.

## Acceptance tests (copy verbatim, then verify checksums)

| File | SHA-256 |
| --- | --- |
| `tests/test_06_index.py` | `e3b7ddc519306760586ed7e68f94ede2eeede23be916627a19deb3577d96ceda` |

### `tests/test_06_index.py`

```python
import argparse
import json
import time

import pytest

from tests.zfixture import ZoteroFixture
from zotcore import cli, tools
from zotcore.index import Index, SyncReport, sync
from zotcore.settings import Settings
from zotcore.textsource import MarkdownCorpus

TEXT = "Stearoyl-CoA desaturase protects cancer cells from lipid peroxidation and ferroptosis.\n\n" * 30


def hits(index, query):
    rows = index.con.execute("SELECT DISTINCT item_key FROM passages WHERE passages MATCH ? ORDER BY item_key", (query,))
    return [r[0] for r in rows]


@pytest.fixture
def setup(tmp_path):
    z = ZoteroFixture(tmp_path / "Zotero")
    group = z.add_group(4805701, "Ancestralize")
    a = z.add_item("MDPAPER1", fields={"title": "Markdown paper", "DOI": "10.1/md"})
    z.add_attachment(a, "PDFMD001", ft_text="cache that loses to markdown " * 20)
    b = z.add_item("FTPAPER1", fields={"title": "Cache paper"})
    z.add_attachment(b, "PDFFT001", ft_text=TEXT, indexed_pages=5, total_pages=9)
    c = z.add_item("SCANNED1", fields={"title": "Scanned paper", "abstractNote": "Mitochondrial uncoupling in brown fat."})
    z.add_attachment(c, "PDFSC001")
    g = z.add_item("GROUPPP1", library_id=group, fields={"title": "Group paper"})
    z.add_attachment(g, "PDFGR001", ft_text="Group text about insulin resistance and myokines.\n\n" * 10)
    md = tmp_path / "md"
    md.mkdir()
    (md / "doi_10.1_md.md").write_text("# Markdown paper\n\nIntro.\n\n## Results\n\nKetogenic diet lowered hepatic triglycerides.\n" * 3,
                                       encoding="utf-8")
    index = Index(tmp_path / "plugin" / "index.sqlite")
    yield z, index, MarkdownCorpus(md), tmp_path
    index.close()
    z.close()


def run(index, z, corpus=None, **kw):
    return sync(index, z.db_path, z.data_dir, corpus=corpus, **kw)


def test_first_sync_builds_the_index(setup):
    z, index, corpus, _ = setup
    rep = run(index, z, corpus)
    assert isinstance(rep, SyncReport)
    assert (rep.examined, rep.indexed, rep.deleted, rep.remaining, rep.done) == (3, 3, 0, 0, True)
    c = index.counts()
    assert c["items"] == 3 and c["libraries"] == {"user": 3}
    assert c["by_source"] == {"markdown": 1, "ft-cache": 1, "metadata": 1}
    assert c["flags"] == {"truncated": 1, "body_not_read": 1, "scanned_or_empty": 1}
    assert c["passages"] >= 4
    assert c["last_sync"].endswith("Z")
    assert hits(index, "triglycerides") == ["MDPAPER1"]
    assert hits(index, "peroxidation") == ["FTPAPER1"]
    assert hits(index, "uncoupling") == ["SCANNED1"]  # metadata-only items are searchable too
    assert hits(index, "loses") == []  # the losing ft-cache text is not indexed
    assert hits(index, "desaturases") == ["FTPAPER1"]  # porter stemming


def test_item_row_holds_metadata(setup):
    z, index, corpus, _ = setup
    run(index, z, corpus)
    row = index.con.execute("SELECT title, doi, text_source, flags, n_passages, creators FROM items WHERE item_key='FTPAPER1'").fetchone()
    assert row[0] == "Cache paper" and row[2] == "ft-cache"
    assert json.loads(row[3]) == ["truncated"] and row[4] >= 1 and json.loads(row[5]) == []
    assert index.con.execute("SELECT doi FROM items WHERE item_key='MDPAPER1'").fetchone()[0] == "10.1/md"


def test_second_sync_does_nothing(setup):
    z, index, corpus, _ = setup
    run(index, z, corpus)
    passages = index.counts()["passages"]
    rep = run(index, z, corpus)
    assert (rep.examined, rep.indexed, rep.deleted, rep.done) == (3, 0, 0, True)
    assert index.counts()["passages"] == passages


def test_changes_are_reindexed_without_duplicates(setup):
    z, index, corpus, _ = setup
    run(index, z, corpus)
    before = index.counts()["passages"]
    item_id = z.con.execute("SELECT itemID FROM items WHERE key='FTPAPER1'").fetchone()[0]
    z.set_field(item_id, "title", "Cache paper, renamed")
    assert run(index, z, corpus).indexed == 1
    assert index.counts()["passages"] == before
    assert index.con.execute("SELECT title FROM items WHERE item_key='FTPAPER1'").fetchone()[0] == "Cache paper, renamed"


def test_new_text_cache_triggers_reindex(setup):
    z, index, corpus, _ = setup
    run(index, z, corpus)
    z.write_ft_cache("PDFSC001", "Now indexed: thermogenesis and UCP1 expression.\n\n" * 10)
    rep = run(index, z, corpus)
    assert rep.indexed == 1
    assert hits(index, "thermogenesis") == ["SCANNED1"]
    assert index.con.execute("SELECT text_source FROM items WHERE item_key='SCANNED1'").fetchone()[0] == "ft-cache"


def test_trashed_items_are_removed(setup):
    z, index, corpus, _ = setup
    run(index, z, corpus)
    z.trash(z.con.execute("SELECT itemID FROM items WHERE key='FTPAPER1'").fetchone()[0])
    rep = run(index, z, corpus)
    assert rep.deleted == 1
    assert hits(index, "peroxidation") == []
    assert index.counts()["items"] == 2


def test_group_libraries_are_opt_in(setup):
    z, index, corpus, _ = setup
    rep = run(index, z, corpus, libraries=("user", "4805701", "999"))
    assert rep.indexed == 4
    assert any("999" in w for w in rep.warnings)
    assert hits(index, "myokines") == ["GROUPPP1"]
    assert index.con.execute("SELECT library FROM items WHERE item_key='GROUPPP1'").fetchone()[0] == "4805701"
    rep = run(index, z, corpus, libraries=("user",))
    assert rep.deleted == 1 and hits(index, "myokines") == []  # a library removed from settings leaves the index


def test_budget_stops_early_and_next_run_resumes(tmp_path):
    z = ZoteroFixture(tmp_path / "Z")
    for n in range(10):
        iid = z.add_item(f"K{n:07d}", fields={"title": f"Paper {n}"})
        z.add_attachment(iid, f"A{n:07d}", ft_text=f"unique{n} " * 50)
    index = Index(tmp_path / "idx.sqlite")
    ticks = iter(range(1000))
    rep = sync(index, z.db_path, z.data_dir, batch_items=2, budget_seconds=3, clock=lambda: next(ticks))
    assert rep.done is False and 0 < rep.examined < 10 and rep.remaining == 10 - rep.examined
    assert index.counts()["last_sync"] is None  # not complete yet
    rep2 = sync(index, z.db_path, z.data_dir, batch_items=2)
    assert rep2.done is True and rep2.indexed == 10 - rep.indexed
    assert index.counts()["items"] == 10
    assert len(hits(index, "unique7")) == 1
    index.close()
    z.close()


def test_progress_and_persistence(setup):
    z, index, corpus, tmp_path = setup
    seen = []
    run(index, z, corpus, batch_items=1, progress=lambda done, total: seen.append((done, total)))
    assert seen == [(1, 3), (2, 3), (3, 3)]
    counts = index.counts()
    index.close()
    again = Index(tmp_path / "plugin" / "index.sqlite")  # reopening must not reset anything
    assert again.counts() == counts
    again.close()


def test_sync_speed(tmp_path):
    z = ZoteroFixture(tmp_path / "Z")
    z.con.execute("BEGIN")
    for n in range(300):
        iid = z.add_item(f"K{n:07d}", fields={"title": f"Paper {n}"})
        z.add_attachment(iid, f"A{n:07d}", ft_text=("Insulin signalling in adipocytes. " * 30 + "\n\n") * 8)
    z.con.execute("COMMIT")
    index = Index(tmp_path / "idx.sqlite")
    started = time.monotonic()
    rep = sync(index, z.db_path, z.data_dir)
    assert rep.indexed == 300
    assert time.monotonic() - started < 20
    index.close()
    z.close()


def test_cli_sync_and_status(setup, capsys):
    z, _, _, tmp_path = setup
    parser = argparse.ArgumentParser(prog="hermes zotero")
    cli.setup_parser(parser)
    root = tmp_path / "pd"
    settings = Settings(zotero_data_dir=str(z.data_dir), markdown_path=str(tmp_path / "md"))
    assert cli.run(parser.parse_args(["sync"]), settings, data_root=lambda: root) == 0
    out = capsys.readouterr().out
    assert "Sync: indexed 3," in out and "Index: 3 items" in out
    assert (root / "index.sqlite").is_file() and (root / "snapshot" / "current" / "zotero.sqlite").is_file()
    assert cli.run(parser.parse_args(["sync"]), settings, data_root=lambda: root) == 0
    assert "Sync: indexed 0," in capsys.readouterr().out
    status = {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root)}["zotero_status"].handler
    data = json.loads(status({}))
    assert data["index"]["items"] == 3
    assert data["index"]["by_source"]["markdown"] == 1
    assert data["index"]["last_sync"].endswith("Z")
    assert cli.run(parser.parse_args(["sync"]), Settings(zotero_data_dir=str(tmp_path / "nope")),
                   data_root=lambda: root) == 2


def test_status_without_index(tmp_path):
    root = tmp_path / "pd"
    status = {s.name: s for s in tools.tool_specs(Settings, data_root=lambda: root)}["zotero_status"].handler
    data = json.loads(status({}))
    assert data["ok"] is True and data["index"] is None
    assert not (root / "index.sqlite").exists()  # status never creates the index
```


## Commands

```bash
.venv/bin/python -m pytest                  # expect: 85 passed
shasum -a 256 tests/test_06_index.py
```

## Live check (Gábor, in the same or a new Claude Code session)

1. Point the plugin at the Markdown corpus and include the group library: in `~/.hermes/config.yaml`, under `plugins.entries.hermes-zotero.settings`, set `markdown_path: ~/Zotero-Markdown` and `libraries: [user, 4805701]`. Show the edited block in the report.
2. `time hermes zotero sync`. Expected (reference run): about 19,290 items, about 18,336 from Markdown, about 1.07 million passages, around 1–2 minutes, and an index of about 3.5 GB in `~/.hermes/plugin-data/hermes-zotero/`.
3. Run `hermes zotero sync` again. Expect `Sync: indexed 0` within a few seconds.
4. `hermes zotero doctor`, then ask Hermes to "call zotero_status". Paste the `index` block.
5. Report times, counts, the index size (`du -sh ~/.hermes/plugin-data/hermes-zotero`) and any warnings.

## Out of scope

Search ranking and the `zotero_search`/`zotero_read` tools (task 07), the time-boxed `zotero_sync` tool, annotations, citations.
