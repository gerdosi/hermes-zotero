"""Tool specifications exposed to Hermes."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__
from .datadir import resolve_data_dir
from .index import Index
from .jsonout import err, ok, safe
from .search import MAX_SEARCH_CHARS, SearchError, open_index, read_item, search
from .settings import Settings
from .snapshot import is_stale, load_info

STATUS_DESC = ("Zotero library index status: whether the local Zotero index is ready, "
               "how fresh it is, and what it holds.")

SEARCH_DESC = ("Zotero library search: find papers the user already has, by full text, offline. "
               "Returns ranked papers with short passages and a coverage verdict (strong / thin / none) "
               "for the topic; doi= checks whether one specific paper is held. Search here before the web.")
READ_DESC = ("Zotero paper reader: read a bounded passage of one paper from the user's library, by item key, "
             "at the best match for a query or at a character offset. Use keys from zotero_search.")
SEARCH_SCHEMA = {"type": "object", "properties": {
    "query": {"type": "string", "description": "Keywords, e.g. 'SCD1 ferroptosis'. Every word counts."},
    "doi": {"type": "string", "description": "Check whether this DOI is in the library."},
    "collection": {"type": "string", "description": "Only this Zotero collection (and its subcollections)."},
    "library": {"type": "string", "description": "'user' or a group ID. Default: all indexed libraries."},
    "year_from": {"type": "integer"},
    "year_to": {"type": "integer"},
    "limit": {"type": "integer", "minimum": 1, "maximum": 25, "description": "Papers to return (default 10)."}}}
READ_SCHEMA = {"type": "object", "properties": {
    "key": {"type": "string", "description": "Item key from zotero_search, e.g. 'ABCD2345'."},
    "library": {"type": "string", "description": "Only needed when the key exists in two libraries."},
    "query": {"type": "string", "description": "Start at the passage that best matches these words."},
    "offset": {"type": "integer", "minimum": 0, "description": "Start at this character (next_offset of a previous read)."},
    "max_chars": {"type": "integer", "description": "Characters to return (default and cap set by the user)."}},
    "required": ["key"]}


def _int_arg(args: dict, name: str, default=None):
    """Integer argument; accepts ints and digit strings."""
    v = args.get(name)
    if v is None or v == "":
        return default
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    if isinstance(v, str) and re.fullmatch(r"-?\d+", v.strip()):
        return int(v.strip())
    raise SearchError("invalid_argument", f"{name} must be an integer")


def _str_arg(args: dict, name: str):
    """String argument; accepts strings and ints; empty becomes None."""
    v = args.get(name)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (str, int)):
        raise SearchError("invalid_argument", f"{name} must be a string")
    return str(v).strip() or None


@dataclass(frozen=True)
class ToolSpec:
    """One Hermes tool."""

    name: str
    schema: dict
    handler: Callable
    description: str


def tool_specs(settings_provider: Callable[[], Settings],
               data_root: Callable[[], object] | None = None) -> list[ToolSpec]:
    """Build tool specs; settings_provider and data_root are called inside handlers only."""

    @safe
    def status(args: dict, **kwargs) -> str:
        s = settings_provider()
        warnings = list(s.warnings)
        found = resolve_data_dir(s.zotero_data_dir)
        snapshot = None
        index = None
        if data_root is not None:
            try:
                plugin_root = Path(data_root())
                root = plugin_root / "snapshot"
            except Exception:
                warnings.append("plugin data dir unavailable; snapshot status not shown")
            else:
                index_path = plugin_root / "index.sqlite"
                if index_path.exists():  # status must never create the index
                    idx = Index(index_path)
                    try:
                        index = idx.counts()
                    finally:
                        idx.close()
                info = load_info(root)
                if info is not None:
                    snapshot = {"taken_at": info.taken_at,
                                "stale": is_stale(info, found.path) if found.path else None}
        return ok(plugin_version=__version__, stage="scaffold",
                  settings=s.as_dict(), warnings=warnings,
                  data_dir=found.as_dict(), snapshot=snapshot, index=index)

    def with_index(run: Callable) -> str:
        """Open the index read-only, run, close; SearchError becomes an error payload."""
        if data_root is None:
            return err("no_index", "plugin data dir unavailable")
        try:
            con = open_index(Path(data_root()) / "index.sqlite")
            try:
                return run(con)
            finally:
                con.close()
        except SearchError as e:
            return err(e.code, e.message, e.hint)

    @safe
    def zsearch(args: dict, **kwargs) -> str:
        s = settings_provider()

        def run(con) -> str:
            limit = min(max(_int_arg(args, "limit", 10), 1), 25)
            payload = search(con, s, query=_str_arg(args, "query"), doi=_str_arg(args, "doi"),
                             library=_str_arg(args, "library"), collection=_str_arg(args, "collection"),
                             year_from=_int_arg(args, "year_from"), year_to=_int_arg(args, "year_to"), limit=limit)
            out = ok(**payload)
            dropped = 0
            while len(out) > MAX_SEARCH_CHARS and payload["hits"]:
                payload["hits"].pop()
                dropped += 1
                payload["hits_dropped_for_size"] = dropped
                out = ok(**payload)
            return out

        return with_index(run)

    @safe
    def zread(args: dict, **kwargs) -> str:
        s = settings_provider()

        def run(con) -> str:
            max_chars = _int_arg(args, "max_chars", s.read_max_chars_default)
            offset = _int_arg(args, "offset")
            payload = read_item(con, key=_str_arg(args, "key"), library=_str_arg(args, "library"),
                                query=_str_arg(args, "query"), offset=None if offset is None else max(offset, 0),
                                max_chars=min(max(max_chars, 200), s.read_max_chars_cap))
            return ok(**payload)

        return with_index(run)

    return [
        ToolSpec(
            name="zotero_status",
            schema={"name": "zotero_status", "description": STATUS_DESC,
                    "parameters": {"type": "object", "properties": {}}},
            handler=status,
            description=STATUS_DESC,
        ),
        ToolSpec(
            name="zotero_search",
            schema={"name": "zotero_search", "description": SEARCH_DESC, "parameters": SEARCH_SCHEMA},
            handler=zsearch,
            description=SEARCH_DESC,
        ),
        ToolSpec(
            name="zotero_read",
            schema={"name": "zotero_read", "description": READ_DESC, "parameters": READ_SCHEMA},
            handler=zread,
            description=READ_DESC,
        ),
    ]
