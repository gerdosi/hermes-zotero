"""Command line interface: `hermes zotero ...`."""
from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .datadir import resolve_data_dir
from .settings import Settings
from .snapshot import SnapshotError, is_stale, load_info, take_snapshot


def setup_parser(parser: argparse.ArgumentParser) -> None:
    """Register subcommands on the `zotero` parser."""
    sub = parser.add_subparsers(dest="zotero_cmd")
    sub.add_parser("doctor", help="Check settings and Zotero access")
    sub.add_parser("snapshot", help="Copy zotero.sqlite (+WAL) into the plugin data dir")
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
            info = take_snapshot(result.path, Path(data_root()) / "snapshot")
        except SnapshotError as e:
            print(f"snapshot failed ({e.code}): {e.message}")
            return 1
        except Exception as e:
            print(f"snapshot failed: {type(e).__name__}: {e}")
            return 1
        print(f"Snapshot written: {info.path} (attempts {info.attempts})")
        return 0
    parser = getattr(args, "_zparser", None)
    if parser is not None:
        parser.print_help()
    return 0
