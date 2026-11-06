"""Typed, validated plugin settings."""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Callable

DEFAULTS: dict[str, object] = {
    "zotero_data_dir": "",
    "markdown_path": "",
    "libraries": ("user",),
    "coverage_strong_min": 8,
    "coverage_recent_min": 2,
    "coverage_recent_years": 5,
    "sync_batch_items": 200,
    "sync_tool_budget_seconds": 30,
    "read_max_chars_default": 4000,
    "read_max_chars_cap": 12000,
}

_STR_KEYS = ("zotero_data_dir", "markdown_path")
_INT_RANGES = {
    "coverage_strong_min": (1, 1000),
    "coverage_recent_min": (0, 1000),
    "coverage_recent_years": (1, 50),
    "sync_batch_items": (10, 5000),
    "sync_tool_budget_seconds": (5, 60),
    "read_max_chars_cap": (1000, 50000),
    "read_max_chars_default": (500, 50000),
}


@dataclass(frozen=True)
class Settings:
    """Plugin settings; every field defaults to its DEFAULTS value."""

    zotero_data_dir: str = ""
    markdown_path: str = ""
    libraries: tuple[str, ...] = ("user",)
    coverage_strong_min: int = 8
    coverage_recent_min: int = 2
    coverage_recent_years: int = 5
    sync_batch_items: int = 200
    sync_tool_budget_seconds: int = 30
    read_max_chars_default: int = 4000
    read_max_chars_cap: int = 12000
    warnings: tuple[str, ...] = ()

    @classmethod
    def from_getter(cls, get: Callable) -> "Settings":
        """Build settings from get(key, default), validating every value."""
        warnings: list[str] = []
        values: dict[str, object] = {}
        for key, default in DEFAULTS.items():
            try:
                raw = get(key, default)
            except Exception as e:
                warnings.append(f"{key}: could not read setting ({type(e).__name__}: {e}); using default")
                values[key] = default
                continue
            if key in _STR_KEYS:
                if isinstance(raw, str):
                    values[key] = raw
                else:
                    warnings.append(f"{key}: expected a string; using default")
                    values[key] = default
            elif key in _INT_RANGES:
                if isinstance(raw, int) and not isinstance(raw, bool):
                    value = raw
                else:
                    warnings.append(f"{key}: expected an integer; using default")
                    value = default
                lo, hi = _INT_RANGES[key]
                clamped = min(max(value, lo), hi)
                if clamped != value:
                    warnings.append(f"{key}: {value} is outside {lo}-{hi}; using {clamped}")
                values[key] = clamped
            else:
                values[key] = cls._libraries(key, raw, default, warnings)
        if values["read_max_chars_default"] > values["read_max_chars_cap"]:
            values["read_max_chars_default"] = values["read_max_chars_cap"]
            warnings.append("read_max_chars_default: above read_max_chars_cap; using the cap")
        return cls(**values, warnings=tuple(warnings))

    @staticmethod
    def _libraries(key: str, raw: object, default: object, warnings: list[str]) -> tuple[str, ...]:
        if not isinstance(raw, (list, tuple)):
            warnings.append(f"{key}: expected a list; using default")
            return default  # type: ignore[return-value]
        kept: list[str] = []
        dropped = False
        for item in raw:
            if isinstance(item, bool):
                dropped = True
            elif isinstance(item, int):
                kept.append(str(item))
            elif isinstance(item, str) and (item == "user" or item.isdigit()):
                kept.append(item)
            else:
                dropped = True
        if dropped:
            warnings.append(f"{key}: dropped invalid entries (allowed: 'user' or numeric group IDs)")
        if not kept:
            warnings.append(f"{key}: no valid entries; using default")
            return default  # type: ignore[return-value]
        return tuple(kept)

    def as_dict(self) -> dict:
        """All settings except warnings, JSON-friendly."""
        out: dict = {}
        for f in fields(self):
            if f.name == "warnings":
                continue
            v = getattr(self, f.name)
            out[f.name] = list(v) if isinstance(v, tuple) else v
        return out
