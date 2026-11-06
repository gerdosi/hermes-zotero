"""Tool specifications exposed to Hermes."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__
from .datadir import resolve_data_dir
from .jsonout import ok, safe
from .settings import Settings
from .snapshot import is_stale, load_info

STATUS_DESC = ("Zotero library index status: whether the local Zotero index is ready, "
               "how fresh it is, and what it holds.")


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
        if data_root is not None:
            try:
                root = Path(data_root()) / "snapshot"
            except Exception:
                warnings.append("plugin data dir unavailable; snapshot status not shown")
            else:
                info = load_info(root)
                if info is not None:
                    snapshot = {"taken_at": info.taken_at,
                                "stale": is_stale(info, found.path) if found.path else None}
        return ok(plugin_version=__version__, stage="scaffold",
                  settings=s.as_dict(), warnings=warnings,
                  data_dir=found.as_dict(), snapshot=snapshot)

    return [
        ToolSpec(
            name="zotero_status",
            schema={"name": "zotero_status", "description": STATUS_DESC,
                    "parameters": {"type": "object", "properties": {}}},
            handler=status,
            description=STATUS_DESC,
        ),
    ]
