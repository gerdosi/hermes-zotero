# Task 03b — Retry when Zotero restarts its WAL during the copy

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code (or DeepSeek V4.1 Flash 1017 in Hermes) |
| Reasoning | **low**: the fix is fully specified below |
| Budget | ≤ 20 tool calls |
| Depends on | task 03 committed |
| Done when | `.venv/bin/python -m pytest` shows **52 passed**, checksums match, report committed |

## Why

Review of task 03 found a race that task 03's spec missed. It is not a coding error. After a full checkpoint, Zotero's next write **restarts the WAL from frame 1** and writes a new header with new salts. A copy that reads the old header and the first old frames, then frames already overwritten by the new transaction, makes SQLite replay an *older* transaction over a *newer* main file. That is a state that never existed. Size and mtime checks cannot see this, and `quick_check` passes. The new test reproduces it: on the task 03 code the snapshot takes 1 attempt and returns the stale value.

The fix: compare the WAL's 32-byte header before the copy, after the copy, and in the copied file. If they differ, the copy is inconsistent; retry.

## Files

```
modify  zotcore/snapshot.py
create  tests/test_03b_wal_restart.py   (verbatim, below)
create  tasks/03b-report.md
```

Touch nothing else.

## Spec

1. Add to `zotcore/snapshot.py`:

```python
def _wal_header(path: Path) -> bytes | None:
    """First 32 bytes of a WAL file (magic, page size, checkpoint sequence, salts), or None if absent."""
    try:
        with open(path, "rb") as f:
            return f.read(32)
    except OSError:
        return None
```

2. In `take_snapshot`, read `before_hdr = _wal_header(wal)` right after `before_wal`. After the copy, read `after_hdr = _wal_header(wal)` and `copied_hdr = _wal_header(tmp / "zotero.sqlite-wal")`.
3. Extend the consistency rule. When a WAL existed before the copy, it now also requires `before_hdr == after_hdr == copied_hdr`. Everything else stays as it is: the main file unchanged, and the WAL present afterwards and not shorter.
4. Update the docstring or comment near the rule to say why: a WAL restart rewrites the header.

## Acceptance test (copy verbatim, then verify checksum)

| File | SHA-256 |
| --- | --- |
| `tests/test_03b_wal_restart.py` | `ac7cbd1205c3a4a505f236e69a0cac5c13e88b5227b7e4cdf36eeeb768ba5426` |

### `tests/test_03b_wal_restart.py`

```python
import shutil
import sqlite3
import struct
from pathlib import Path

from zotcore.snapshot import take_snapshot


def test_wal_restart_during_copy_is_retried(tmp_path):
    """Zotero restarts its WAL from frame 1 after a full checkpoint. A copy that reads the old
    WAL header and early frames, then frames already overwritten by the new transaction, would
    replay an older transaction over a newer main file: a state that never existed. The WAL
    header changes on restart, so the snapshot must notice and retry."""
    data_dir = tmp_path / "Zotero"
    data_dir.mkdir()
    writer = sqlite3.connect(data_dir / "zotero.sqlite", isolation_level=None)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("CREATE TABLE kv(k TEXT PRIMARY KEY, v INTEGER)")
    writer.execute("INSERT INTO kv VALUES ('x', 0)")
    writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    writer.execute("PRAGMA locking_mode=EXCLUSIVE")
    writer.execute("UPDATE kv SET v=1 WHERE k='x'")  # transaction A, frame 1 of the WAL
    writer.execute("UPDATE kv SET v=2 WHERE k='x'")  # transaction B, frame 2
    writer.execute("PRAGMA wal_checkpoint(PASSIVE)")  # main file now holds v=2; WAL still holds A, B
    raced = {"done": False}

    def racing_copy(src, dst):
        if not src.endswith("-wal") or raced["done"]:
            return shutil.copyfile(src, dst)
        raced["done"] = True
        old = Path(src).read_bytes()  # the reader has consumed the header and frame 1 ...
        writer.executescript("BEGIN; UPDATE kv SET v=3 WHERE k='x'; "
                             "INSERT INTO kv VALUES ('big', zeroblob(9000)); COMMIT;")  # WAL restart
        new = Path(src).read_bytes()  # ... and reads the rest after the restart
        page_size = struct.unpack(">I", old[8:12])[0]
        cut = 32 + (24 + page_size)
        Path(dst).write_bytes(old[:cut] + new[cut:])

    info = take_snapshot(data_dir, tmp_path / "snap", settle_seconds=0, copy=racing_copy)
    writer.close()
    value = sqlite3.connect(info.path).execute("SELECT v FROM kv WHERE k='x'").fetchone()[0]
    assert info.attempts == 2
    assert value == 3
```

## Commands

```bash
.venv/bin/python -m pytest                          # expect: 52 passed
shasum -a 256 tests/test_03b_wal_restart.py         # must match
```

Finish with `tasks/03b-report.md` (same template as before) and one commit: `task 03b: retry on WAL restart`.
