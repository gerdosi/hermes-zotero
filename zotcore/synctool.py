"""The time-boxed sync step behind `zotero_sync`, and the lock that lets only one sync run at a time."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from .datadir import resolve_data_dir
from .index import Index, sync
from .search import SearchError
from .settings import Settings
from .snapshot import SnapshotError, is_stale, load_info, take_snapshot
from .textsource import MarkdownCorpus

MAX_ITEM_LINES = 3


class SyncBusy(Exception):
    """Another sync holds the lock."""


@contextmanager
def sync_lock(root):
    """Exclusive, non-blocking OS lock on <root>/sync.lock; released by the OS if the process dies."""
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


def _cap_warnings(warnings) -> list[str]:
    kept: list[str] = []
    item_lines = 0
    for w in warnings:
        if w.startswith("item "):
            item_lines += 1
            if item_lines > MAX_ITEM_LINES:
                continue
        kept.append(w)
    return kept


def sync_step(settings: Settings, data_root, *, budget_seconds: float,
              clock: Callable[[], float] = time.monotonic) -> dict:
    """Snapshot (or reuse the current one) and index for about budget_seconds; the next call resumes."""
    t0 = clock()
    found = resolve_data_dir(settings.zotero_data_dir)
    if not found.path:
        raise SearchError("no_zotero", "Zotero data directory not found.",
                          "Run `hermes zotero doctor` in a terminal, or set zotero_data_dir.")
    root = Path(data_root)
    try:
        with sync_lock(root):
            info = load_info(root / "snapshot")
            reused = info is not None and Path(info.path).is_file() and not is_stale(info, found.path)
            if not reused:
                try:
                    info = take_snapshot(found.path, root / "snapshot")
                except SnapshotError as e:
                    raise SearchError(e.code, e.message, "Try again in a minute.") from e
            corpus = MarkdownCorpus(settings.markdown_path) if settings.markdown_path else None
            index = Index(root / "index.sqlite")
            try:
                rep = sync(index, info.path, found.path, libraries=settings.libraries, corpus=corpus,
                           batch_items=settings.sync_batch_items,
                           budget_seconds=max(budget_seconds - (clock() - t0), 0.0), clock=clock)
                last_sync = index.get_state("last_sync")
            finally:
                index.close()
    except SyncBusy as e:
        raise SearchError("busy", "Another Zotero sync is running.", "Try again in a minute.") from e
    eta = round(rep.remaining * rep.seconds / rep.indexed) if not rep.done and rep.indexed > 0 else None
    return {"done": rep.done, "examined": rep.examined, "total": rep.examined + rep.remaining,
            "indexed": rep.indexed, "deleted": rep.deleted, "remaining": rep.remaining,
            "seconds": round(clock() - t0, 1), "eta_seconds": eta,
            "snapshot": {"taken_at": info.taken_at, "reused": reused},
            "index_last_sync": last_sync, "warnings": _cap_warnings(rep.warnings),
            "next": None if rep.done else "Call zotero_sync again to continue."}
