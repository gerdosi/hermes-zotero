"""Consistent private snapshot of zotero.sqlite + its WAL. The source is only ever read."""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class SnapshotError(Exception):
    """Snapshot failure. code: no_database | copy_failed | source_busy | corrupt_copy."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SnapshotInfo:
    """Metadata of the current snapshot (stored as snapshot.json next to the copy)."""

    path: str
    taken_at: str
    attempts: int
    source_db_size: int
    source_db_mtime_ns: int
    source_wal_size: int
    source_wal_mtime_ns: int
    quick_check: str


def _stat(path: Path) -> tuple[int, int] | None:
    """(size, mtime_ns) of a file, or None if it is absent."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)


def _finalize_copy(db_copy: Path) -> str:
    """Verify the copy, fold the WAL into it and make it a single file. Returns the quick_check."""
    try:
        con = sqlite3.connect(str(db_copy), isolation_level=None)
        try:
            row = con.execute("PRAGMA quick_check").fetchone()
            result = str(row[0]) if row else ""
            if result != "ok":
                raise SnapshotError("corrupt_copy", f"quick_check reported: {result[:200]}")
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
            con.execute("PRAGMA journal_mode=DELETE").fetchall()
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        raise SnapshotError("corrupt_copy", f"copy is not a usable database: {e}") from e
    for suffix in ("-wal", "-shm"):
        Path(str(db_copy) + suffix).unlink(missing_ok=True)
    return result


def _swap_in(tmp: Path, dest_root: Path) -> None:
    """Replace dest_root/current with tmp, keeping the old one until the swap has worked."""
    current = dest_root / "current"
    previous = dest_root / "previous"
    shutil.rmtree(previous, ignore_errors=True)
    had_current = current.exists()
    if had_current:
        os.replace(current, previous)
    try:
        os.replace(tmp, current)
    except BaseException:
        if had_current:
            os.replace(previous, current)
        raise
    shutil.rmtree(previous, ignore_errors=True)


def take_snapshot(data_dir, dest_root, *, retries: int = 3, settle_seconds: float = 0.2,
                  copy: Callable = shutil.copyfile) -> SnapshotInfo:
    """Copy zotero.sqlite (+ -wal) into dest_root/current and return its info."""
    data_dir, dest_root = Path(data_dir), Path(dest_root)
    db = data_dir / "zotero.sqlite"
    wal = data_dir / "zotero.sqlite-wal"
    if not db.is_file():
        raise SnapshotError("no_database", f"no zotero.sqlite in {data_dir}")
    dest_root.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, retries + 1):
        tmp = dest_root / f".tmp-{uuid.uuid4().hex}"
        try:
            tmp.mkdir()
            before_db = _stat(db)
            before_wal = _stat(wal)
            try:
                copy(str(db), str(tmp / "zotero.sqlite"))
                if before_wal is not None:
                    copy(str(wal), str(tmp / "zotero.sqlite-wal"))
            except OSError as e:
                raise SnapshotError("copy_failed", f"copying failed: {e}") from e
            after_db = _stat(db)
            after_wal = _stat(wal)
            consistent = after_db == before_db and before_db is not None and (
                before_wal is None or (after_wal is not None and after_wal[0] >= before_wal[0]))
            if not consistent:
                shutil.rmtree(tmp, ignore_errors=True)
                if attempt < retries:
                    time.sleep(settle_seconds)
                continue

            quick_check = _finalize_copy(tmp / "zotero.sqlite")
            info = SnapshotInfo(
                path=str(dest_root / "current" / "zotero.sqlite"),
                taken_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                attempts=attempt,
                source_db_size=before_db[0],
                source_db_mtime_ns=before_db[1],
                source_wal_size=before_wal[0] if before_wal else 0,
                source_wal_mtime_ns=before_wal[1] if before_wal else 0,
                quick_check=quick_check,
            )
            (tmp / "snapshot.json").write_text(json.dumps(dataclasses.asdict(info)),
                                               encoding="utf-8")
            _swap_in(tmp, dest_root)
            return info
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
    raise SnapshotError("source_busy",
                        f"zotero.sqlite kept changing during {retries} copy attempts")


def load_info(dest_root) -> SnapshotInfo | None:
    """Read the current snapshot's info, or None if missing or unreadable."""
    try:
        text = (Path(dest_root) / "current" / "snapshot.json").read_text(encoding="utf-8")
        return SnapshotInfo(**json.loads(text))
    except (OSError, ValueError, TypeError):
        return None


def is_stale(info: SnapshotInfo, data_dir) -> bool:
    """True if the source db or WAL differs from what the snapshot was taken from."""
    data_dir = Path(data_dir)
    db = _stat(data_dir / "zotero.sqlite")
    wal = _stat(data_dir / "zotero.sqlite-wal") or (0, 0)
    return (db != (info.source_db_size, info.source_db_mtime_ns)
            or wal != (info.source_wal_size, info.source_wal_mtime_ns))
