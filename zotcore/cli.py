"""Command line interface: `hermes zotero ...`."""
from __future__ import annotations

import argparse

from . import __version__
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
        return 0
    parser = getattr(args, "_zparser", None)
    if parser is not None:
        parser.print_help()
    return 0
