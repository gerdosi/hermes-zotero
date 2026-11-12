"""Command line interface: `hermes zotero ...`."""
from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .datadir import resolve_data_dir
from .index import Index, sync
from .settings import Settings
from .snapshot import SnapshotError, is_stale, load_info, take_snapshot
from .synctool import SyncBusy, sync_lock
from .textsource import MarkdownCorpus


def setup_parser(parser: argparse.ArgumentParser) -> None:
    """Register subcommands on the `zotero` parser."""
    sub = parser.add_subparsers(dest="zotero_cmd")
    sub.add_parser("doctor", help="Check settings and Zotero access")
    sub.add_parser("snapshot", help="Copy zotero.sqlite (+WAL) into the plugin data dir")
    sub.add_parser("sync", help="Snapshot Zotero and update the search index")
    parser.set_defaults(_zparser=parser)


def _print_snapshot_block(result, data_root) -> None:
    """Print the snapshot status lines for `doctor`."""
    print("Snapshot:")
    try:
        root = Path(data_root()) / "snapshot"
    except Exception as e:
        print(f"  plugin data dir unavailable: {e}")
        return
    info = load_info(root)
    if info is None:
        print("  none yet (run `hermes zotero snapshot`)")
        return
    print(f"  taken_at: {info.taken_at}")
    print(f"  stale: {is_stale(info, result.path) if result.path else None}")


def _run_sync(settings: Settings, data_root) -> int:
    """`hermes zotero sync`: take a snapshot, then update the index from it."""
    result = resolve_data_dir(settings.zotero_data_dir)
    if not result.path:
        print("Zotero data directory not found; run `hermes zotero doctor` for details.")
        return 2
    if data_root is None:
        print("sync failed: plugin data dir unavailable")
        return 1
    root = Path(data_root())
    try:
        with sync_lock(root):
            return _sync_locked(settings, root, result.path)
    except SyncBusy:
        print("Another sync is running; try again in a minute.")
        return 1


def _sync_locked(settings: Settings, root: Path, data_dir) -> int:
    """Snapshot and index while the sync lock is held."""
    try:
        info = take_snapshot(data_dir, root / "snapshot")
    except SnapshotError as e:
        print(f"snapshot failed ({e.code}): {e.message}")
        return 1
    print(f"Snapshot: {info.path} (attempts {info.attempts})")
    corpus = MarkdownCorpus(settings.markdown_path) if settings.markdown_path else None
    marks = {"next": 10}

    def progress(done: int, total: int) -> None:
        pct = 100 * done // total if total else 100
        if pct >= marks["next"] or done == total:
            print(f"  {done}/{total} items examined")
            marks["next"] = (pct // 10 + 1) * 10

    index = Index(root / "index.sqlite")
    try:
        report = sync(index, info.path, data_dir, libraries=settings.libraries, corpus=corpus,
                      batch_items=settings.sync_batch_items, progress=progress)
        for warning in report.warnings:
            print(f"  warning: {warning}")
        print(f"Sync: indexed {report.indexed}, deleted {report.deleted}, "
              f"examined {report.examined} in {report.seconds:.1f}s")
        c = index.counts()
        print(f"Index: {c['items']} items, {c['passages']} passages, {c['tables']} tables; "
              f"text sources {c['by_source']}; flags {c['flags']}")
    finally:
        index.close()
    return 0


def run(args: argparse.Namespace, settings: Settings, data_root=None) -> int:
    """Run the parsed command and return an exit code."""
    cmd = getattr(args, "zotero_cmd", None)
    if cmd == "doctor":
        print(f"hermes-zotero {__version__}")
        for key, value in settings.as_dict().items():
            print(f"  {key}: {value}")
        for warning in settings.warnings:
            print(f"  warning: {warning}")
        result = resolve_data_dir(settings.zotero_data_dir)
        print("Zotero data directory:")
        if result.path:
            print(f"  {result.path} (source: {result.source})")
        else:
            print("  not found")
        for c in result.candidates:
            print(f"  [{'ok' if c.ok else '--'}] {c.source}: {c.path} ({c.reason})")
        if not result.path:
            print("  hint: set zotero_data_dir under plugins.entries.hermes-zotero.settings "
                  "in ~/.hermes/config.yaml")
        if data_root is not None:
            _print_snapshot_block(result, data_root)
        return 0
    if cmd == "snapshot":
        result = resolve_data_dir(settings.zotero_data_dir)
        if not result.path:
            print("Zotero data directory not found; run `hermes zotero doctor` for details.")
            return 2
        if data_root is None:
            print("snapshot failed: plugin data dir unavailable")
            return 1
        try:
            root = Path(data_root())
            with sync_lock(root):
                info = take_snapshot(result.path, root / "snapshot")
        except SyncBusy:
            print("Another sync is running; try again in a minute.")
            return 1
        except SnapshotError as e:
            print(f"snapshot failed ({e.code}): {e.message}")
            return 1
        except Exception as e:
            print(f"snapshot failed: {type(e).__name__}: {e}")
            return 1
        print(f"Snapshot written: {info.path} (attempts {info.attempts})")
        return 0
    if cmd == "sync":
        return _run_sync(settings, data_root)
    parser = getattr(args, "_zparser", None)
    if parser is not None:
        parser.print_help()
    return 0
