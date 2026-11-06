"""Command line interface: `hermes zotero ...`."""
from __future__ import annotations

import argparse

from . import __version__
from .datadir import resolve_data_dir
from .settings import Settings


def setup_parser(parser: argparse.ArgumentParser) -> None:
    """Register subcommands on the `zotero` parser."""
    sub = parser.add_subparsers(dest="zotero_cmd")
    sub.add_parser("doctor", help="Check settings and Zotero access")
    parser.set_defaults(_zparser=parser)


def run(args: argparse.Namespace, settings: Settings) -> int:
    """Run the parsed command and return an exit code."""
    if getattr(args, "zotero_cmd", None) == "doctor":
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
        return 0
    parser = getattr(args, "_zparser", None)
    if parser is not None:
        parser.print_help()
    return 0
