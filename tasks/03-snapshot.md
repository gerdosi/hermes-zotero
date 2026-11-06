# Task 03 — Consistent snapshot of zotero.sqlite + WAL

| | |
| --- | --- |
| Executor | DeepSeek V4.1 Flash 1017 |
| Reasoning | **max** (`/reasoning max`). This is concurrency-sensitive file handling; detailed specs do not remove debugging work. |
| Budget | ≤ 60 tool calls |
| Depends on | tasks 01–02 committed, all tests green |
| Done when | `python -m pytest` shows **51 passed** (37 old + 14 new), checksums match, report committed |

## Goal

Make a private, self-contained copy of the user's Zotero database that includes changes still sitting in the WAL file. Never touch the original. Retry if Zotero changes the main file mid-copy. Keep the previous good copy if anything fails.

## Background (read before coding)

- Zotero keeps `zotero.sqlite` in **WAL mode under an exclusive lock** while it runs. A normal read-only connection is refused ("database is locked"). An `immutable=1` connection gets past the lock but **skips the `-wal` file**, so recent changes are invisible (zotero-mcp issue #536). The first test demonstrates this.
- The fix is to copy `zotero.sqlite` **and** `zotero.sqlite-wal` (never `-shm`) into a private folder and open the copy normally. SQLite then replays the WAL.
- **The WAL may grow during the copy.** That is safe: SQLite ignores frames after the last complete commit, so a shorter WAL is an earlier consistent state.
- **The main file changing during the copy is not safe:** it means a checkpoint wrote pages into it. Retry.
- After a successful copy, checkpoint the copy (`PRAGMA wal_checkpoint(TRUNCATE)`) and switch it to `journal_mode=DELETE`. The snapshot is then one self-contained file.

## Files

```
create  zotcore/snapshot.py
create  tests/test_03_snapshot.py  (verbatim, below)
modify  zotcore/tools.py           (tool_specs gains data_root; status gains a snapshot block)
modify  zotcore/cli.py             (new `snapshot` subcommand; run() gains data_root)
modify  __init__.py                (content below, verbatim)
```

## Spec — `zotcore/snapshot.py`

```python
class SnapshotError(Exception):
    code: str   # "no_database" | "copy_failed" | "source_busy" | "corrupt_copy"
    def __init__(self, code: str, message: str): ...

@dataclass(frozen=True)
class SnapshotInfo:
    path: str                 # <dest_root>/current/zotero.sqlite
    taken_at: str             # UTC, format "%Y-%m-%dT%H:%M:%SZ"
    attempts: int
    source_db_size: int
    source_db_mtime_ns: int
    source_wal_size: int      # 0 if there was no WAL
    source_wal_mtime_ns: int  # 0 if there was no WAL
    quick_check: str          # "ok"

def take_snapshot(data_dir, dest_root, *, retries: int = 3, settle_seconds: float = 0.2,
                  copy=shutil.copyfile) -> SnapshotInfo
def load_info(dest_root) -> SnapshotInfo | None
def is_stale(info: SnapshotInfo, data_dir) -> bool
```

`take_snapshot` algorithm:

1. `db = data_dir/"zotero.sqlite"`, `wal = data_dir/"zotero.sqlite-wal"`. If `db` is not a file, raise `SnapshotError("no_database", ...)`. Create `dest_root` if needed.
2. For `attempt` in `1..retries`:
   1. Make a fresh `dest_root/.tmp-<uuid4 hex>/` folder.
   2. `before_db = (size, mtime_ns)` of `db`; `before_wal` likewise, or `None` if the WAL is absent.
   3. `copy(str(db), str(tmp/"zotero.sqlite"))`, then, if the WAL existed, `copy(str(wal), str(tmp/"zotero.sqlite-wal"))`. Always pass `str` paths and always go through the `copy` argument (tests inject it). Turn an `OSError` into `SnapshotError("copy_failed", ...)`.
   4. Take `after_db` and `after_wal`. The copy is consistent iff `after_db == before_db` **and** (`before_wal is None`, or `after_wal` exists with size ≥ `before_wal` size).
   5. If it is not consistent: delete the tmp folder, sleep `settle_seconds` unless this was the last attempt, and continue.
   6. Open `tmp/"zotero.sqlite"` with `sqlite3.connect` (normal mode, `isolation_level=None`). Run `PRAGMA quick_check`; anything other than `"ok"`, or any `sqlite3.DatabaseError`, raises `SnapshotError("corrupt_copy", ...)`. Then run `PRAGMA wal_checkpoint(TRUNCATE)` and `PRAGMA journal_mode=DELETE`, and close. Delete any leftover `-wal`/`-shm` in tmp.
   7. Build `SnapshotInfo` (from the **before** stats; `path` points at `dest_root/current/zotero.sqlite`) and write it as `tmp/"snapshot.json"` (`dataclasses.asdict`, UTF-8).
   8. Swap: delete any old `dest_root/previous`; rename `current` → `previous` if it exists; rename `tmp` → `current`. If that fails, rename `previous` back to `current` and re-raise. On success, delete `previous`. Use `os.replace`.
   9. Return the info.
3. If all attempts were inconsistent, raise `SnapshotError("source_busy", ...)`.
4. On **any** exception, delete the tmp folder before propagating. Afterwards `dest_root` holds only `current` (if a good snapshot ever existed): no `.tmp-*`, no `previous`.
5. Never open, create or modify anything inside `data_dir`.

`load_info`: read `dest_root/current/snapshot.json` into `SnapshotInfo`. Return `None` if it is missing or unreadable.

`is_stale`: `True` if the current `(size, mtime_ns)` of the source db differs from the info, or if the current WAL `(size, mtime_ns)` (treat an absent WAL as `(0, 0)`) differs.

## Spec — integration

`__init__.py` (verbatim):

```python
"""Hermes glue for hermes-zotero. All logic lives in zotcore/."""
from .zotcore import __version__, cli, tools
from .zotcore.settings import Settings


def register(ctx):
    def settings() -> Settings:
        return Settings.from_getter(ctx.get_config)

    def data_root():
        from plugins.plugin_storage import plugin_data_dir  # Hermes public API; per-profile folder
        return plugin_data_dir("hermes-zotero")

    for spec in tools.tool_specs(settings, data_root=data_root):
        ctx.register_tool(name=spec.name, toolset="zotero", schema=spec.schema,
                          handler=spec.handler, description=spec.description, emoji="📚")

    ctx.register_cli_command(
        name="zotero",
        help="Local, read-only Zotero library index",
        setup_fn=cli.setup_parser,
        handler_fn=lambda args: cli.run(args, settings(), data_root=data_root),
        description="Check and maintain the local Zotero index used by the zotero_* tools.",
    )
```

`zotcore/tools.py`:

- Change the signature to `tool_specs(settings_provider, data_root=None)`. `data_root` is a zero-argument callable returning the plugin data folder; snapshots live in `data_root()/"snapshot"`. **Do not import Hermes in `zotcore`**: the stdlib-only test enforces it.
- `zotero_status` adds a `snapshot` key: `None` if `data_root` is `None` or no snapshot exists; otherwise `{"taken_at": info.taken_at, "stale": is_stale(info, data_dir) if a data dir was found else None}`. If calling `data_root()` raises, `snapshot` is `None` and a warning containing `plugin data dir unavailable` is appended to `warnings`. Keep every existing key.

`zotcore/cli.py`:

- New subcommand `snapshot` ("Copy zotero.sqlite (+WAL) into the plugin data dir").
- Signature `run(args, settings, data_root=None) -> int`.
- `snapshot`: resolve the data dir. If none is found, print a hint to run `hermes zotero doctor` and return **2**. Otherwise call `take_snapshot(data_dir, Path(data_root())/"snapshot")`. On `SnapshotError`, print `snapshot failed (<code>): <message>` and return **1**. On success, print `Snapshot written: <path> (attempts N)` and return 0.
- `doctor` also prints the snapshot block (`taken_at`, `stale`) when `data_root` is given.

## Acceptance tests (copy verbatim, then verify checksums)

| File | SHA-256 |
| --- | --- |
| `tests/test_03_snapshot.py` | `c440f8457b65e3b7fff84a982ac410b6c9ab3051493e7233d4866db597912b77` |

### `tests/test_03_snapshot.py`

```python
import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from zotcore import tools
from zotcore.settings import Settings
from zotcore.snapshot import SnapshotError, is_stale, load_info, take_snapshot


def count_items(db_path, immutable=False):
    uri = f"file:{db_path}?immutable=1" if immutable else f"file:{db_path}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        return con.execute("SELECT count(*) FROM items").fetchone()[0]
    finally:
        con.close()


@pytest.fixture
def zotero_like(tmp_path):
    """A data dir whose zotero.sqlite behaves like a running Zotero: WAL mode, exclusive lock,
    one row checkpointed into the main file and one row still only in the -wal file."""
    data_dir = tmp_path / "Zotero"
    data_dir.mkdir()
    con = sqlite3.connect(data_dir / "zotero.sqlite", isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA wal_autocheckpoint=0")
    con.execute("CREATE TABLE items(itemID INTEGER PRIMARY KEY, key TEXT)")
    con.execute("INSERT INTO items(key) VALUES ('AAAA1111')")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("PRAGMA locking_mode=EXCLUSIVE")
    con.execute("INSERT INTO items(key) VALUES ('BBBB2222')")
    yield data_dir, con
    con.close()


def fingerprint(directory: Path):
    return {p.name: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(directory.iterdir()) if p.is_file()}


def bump_mtime(path):
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))


def test_snapshot_includes_rows_still_in_wal(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    # Why this module exists: an immutable read of the live file misses the WAL row.
    assert count_items(data_dir / "zotero.sqlite", immutable=True) == 1
    info = take_snapshot(data_dir, tmp_path / "snap", settle_seconds=0)
    assert info.attempts == 1
    assert info.quick_check == "ok"
    assert info.source_wal_size > 0
    assert count_items(info.path) == 2


def test_snapshot_is_self_contained(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    info = take_snapshot(data_dir, tmp_path / "snap", settle_seconds=0)
    current = Path(info.path).parent
    assert current.name == "current"
    assert sorted(p.name for p in current.iterdir()) == ["snapshot.json", "zotero.sqlite"]
    assert count_items(info.path, immutable=True) == 2


def test_source_is_never_modified(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    before = fingerprint(data_dir)
    take_snapshot(data_dir, tmp_path / "snap", settle_seconds=0)
    assert fingerprint(data_dir) == before


def test_retries_when_main_file_changes_during_copy(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    calls = {"bumped": False}

    def flaky_copy(src, dst):
        shutil.copyfile(src, dst)
        if Path(src).name == "zotero.sqlite" and not calls["bumped"]:
            calls["bumped"] = True
            bump_mtime(src)

    info = take_snapshot(data_dir, tmp_path / "snap", settle_seconds=0, copy=flaky_copy)
    assert info.attempts == 2
    assert count_items(info.path) == 2


def test_wal_growth_after_copy_is_accepted(zotero_like, tmp_path):
    data_dir, writer = zotero_like

    def copy_then_write(src, dst):
        shutil.copyfile(src, dst)
        if Path(src).name == "zotero.sqlite-wal":
            writer.execute("INSERT INTO items(key) VALUES ('CCCC3333')")

    info = take_snapshot(data_dir, tmp_path / "snap", settle_seconds=0, copy=copy_then_write)
    assert info.attempts == 1
    assert count_items(info.path) == 2  # the late row is not in the copy, and that is consistent


def test_gives_up_and_keeps_previous_snapshot(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    dest = tmp_path / "snap"
    first = take_snapshot(data_dir, dest, settle_seconds=0)

    def always_busy(src, dst):
        shutil.copyfile(src, dst)
        if Path(src).name == "zotero.sqlite":
            bump_mtime(src)

    with pytest.raises(SnapshotError) as exc:
        take_snapshot(data_dir, dest, retries=3, settle_seconds=0, copy=always_busy)
    assert exc.value.code == "source_busy"
    assert load_info(dest) == first
    assert count_items(first.path) == 2
    assert sorted(os.listdir(dest)) == ["current"]


def test_corrupt_copy_is_rejected(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    dest = tmp_path / "snap"
    first = take_snapshot(data_dir, dest, settle_seconds=0)

    def corrupting_copy(src, dst):
        if Path(src).name == "zotero.sqlite":
            Path(dst).write_bytes(b"this is not a database" * 500)
        else:
            shutil.copyfile(src, dst)

    with pytest.raises(SnapshotError) as exc:
        take_snapshot(data_dir, dest, settle_seconds=0, copy=corrupting_copy)
    assert exc.value.code == "corrupt_copy"
    assert load_info(dest) == first
    assert sorted(os.listdir(dest)) == ["current"]


def test_second_snapshot_replaces_first(zotero_like, tmp_path):
    data_dir, writer = zotero_like
    dest = tmp_path / "snap"
    take_snapshot(data_dir, dest, settle_seconds=0)
    writer.execute("INSERT INTO items(key) VALUES ('DDDD4444')")
    info = take_snapshot(data_dir, dest, settle_seconds=0)
    assert count_items(info.path) == 3
    assert sorted(os.listdir(dest)) == ["current"]


def test_load_info_round_trip_and_staleness(zotero_like, tmp_path):
    data_dir, writer = zotero_like
    dest = tmp_path / "snap"
    assert load_info(dest) is None
    info = take_snapshot(data_dir, dest, settle_seconds=0)
    assert load_info(dest) == info
    meta = json.loads((Path(info.path).parent / "snapshot.json").read_text(encoding="utf-8"))
    assert meta["taken_at"].endswith("Z")
    assert is_stale(info, data_dir) is False
    writer.execute("INSERT INTO items(key) VALUES ('EEEE5555')")
    assert is_stale(info, data_dir) is True


def test_plain_database_without_wal(tmp_path):
    data_dir = tmp_path / "Zotero"
    data_dir.mkdir()
    con = sqlite3.connect(data_dir / "zotero.sqlite")
    con.execute("CREATE TABLE items(itemID INTEGER PRIMARY KEY, key TEXT)")
    con.execute("INSERT INTO items(key) VALUES ('AAAA1111')")
    con.commit()
    con.close()
    info = take_snapshot(data_dir, tmp_path / "snap", settle_seconds=0)
    assert info.source_wal_size == 0
    assert count_items(info.path) == 1


def test_missing_database(tmp_path):
    (tmp_path / "Zotero").mkdir()
    with pytest.raises(SnapshotError) as exc:
        take_snapshot(tmp_path / "Zotero", tmp_path / "snap", settle_seconds=0)
    assert exc.value.code == "no_database"


def test_status_reports_snapshot(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    plugin_data = tmp_path / "plugin-data"
    provider = lambda: Settings(zotero_data_dir=str(data_dir))
    specs = {s.name: s for s in tools.tool_specs(provider, data_root=lambda: plugin_data)}
    status = specs["zotero_status"].handler
    assert json.loads(status({}))["snapshot"] is None
    take_snapshot(data_dir, plugin_data / "snapshot", settle_seconds=0)
    snap = json.loads(status({}))["snapshot"]
    assert snap["stale"] is False
    assert snap["taken_at"].endswith("Z")


def test_status_survives_unavailable_plugin_data_dir(zotero_like):
    data_dir, _ = zotero_like
    def broken_root():
        raise RuntimeError("no hermes home")
    provider = lambda: Settings(zotero_data_dir=str(data_dir))
    specs = {s.name: s for s in tools.tool_specs(provider, data_root=broken_root)}
    data = json.loads(specs["zotero_status"].handler({}))
    assert data["ok"] is True
    assert data["snapshot"] is None
    assert any("plugin data" in w for w in data["warnings"])


def test_cli_snapshot_command(zotero_like, tmp_path, capsys):
    import argparse
    from zotcore import cli
    data_dir, _ = zotero_like
    parser = argparse.ArgumentParser(prog="hermes zotero")
    cli.setup_parser(parser)
    settings = Settings(zotero_data_dir=str(data_dir))
    rc = cli.run(parser.parse_args(["snapshot"]), settings, data_root=lambda: tmp_path / "pd")
    assert rc == 0
    assert "snapshot" in capsys.readouterr().out.lower()
    assert count_items(tmp_path / "pd" / "snapshot" / "current" / "zotero.sqlite") == 2
    # A missing data dir is a clean non-zero exit, not a traceback.
    rc = cli.run(parser.parse_args(["snapshot"]), Settings(zotero_data_dir=str(tmp_path / "nope")),
                 data_root=lambda: tmp_path / "pd")
    assert rc == 2
```


## Commands

```bash
python -m pytest                          # expect: 51 passed
shasum -a 256 tests/test_03_snapshot.py   # must match
```

## Live check (Gábor, with Zotero running)

```bash
ls -lh "<your data dir>/zotero.sqlite"*          # note the sizes of the db and -wal
time hermes zotero snapshot                       # note the duration
SNAP=~/.hermes/plugin-data/hermes-zotero/snapshot/current/zotero.sqlite   # adjust if you use a Hermes profile
sqlite3 "$SNAP" "select count(*) from items"
# add one item in Zotero (e.g. by DOI), then:
hermes zotero snapshot && sqlite3 "$SNAP" "select count(*) from items"   # expect +1 (or more, with attachments/notes)
hermes zotero doctor                              # snapshot block: stale = False right after the snapshot
```

Report the sizes, the duration, both counts, and whether Zotero showed any error while the snapshot ran.

## Out of scope

- **Windows with a database over 1 GiB while Zotero runs.** SQLite's lock-byte page at offset 1 GiB is locked by Windows mandatory locks, so the copy may fail with `PermissionError`. Report it as `copy_failed` and mention it in the report; a fix (zero-filling that unused page) is a later task.
- Sync, indexing and scheduling.
