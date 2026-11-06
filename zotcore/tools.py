"""Tool specifications exposed to Hermes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import __version__
from .jsonout import ok, safe
from .settings import Settings

STATUS_DESC = ("Zotero library index status: whether the local Zotero index is ready, "
               "how fresh it is, and what it holds.")


@dataclass(frozen=True)
class ToolSpec:
    """One Hermes tool."""

    name: str
    schema: dict
    handler: Callable
    description: str


def tool_specs(settings_provider: Callable[[], Settings]) -> list[ToolSpec]:
    """Build tool specs; settings_provider is called inside handlers only."""

    @safe
    def status(args: dict, **kwargs) -> str:
        s = settings_provider()
        return ok(plugin_version=__version__, stage="scaffold",
                  settings=s.as_dict(), warnings=list(s.warnings))

    return [
        ToolSpec(
            name="zotero_status",
            schema={"name": "zotero_status", "description": STATUS_DESC,
                    "parameters": {"type": "object", "properties": {}}},
            handler=status,
            description=STATUS_DESC,
        ),
    ]
