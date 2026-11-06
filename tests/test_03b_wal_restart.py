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
