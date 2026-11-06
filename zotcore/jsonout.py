"""JSON string helpers for tool handlers."""
from __future__ import annotations

import functools
import json
from typing import Callable


def ok(**data) -> str:
    """Success payload as a JSON string."""
    return json.dumps({"ok": True, **data}, ensure_ascii=False)


def err(code: str, message: str, hint: str | None = None) -> str:
    """Error payload as a JSON string."""
    error = {"code": code, "message": message}
    if hint is not None:
        error["hint"] = hint
    return json.dumps({"ok": False, "error": error}, ensure_ascii=False)


def safe(fn: Callable) -> Callable:
    """Wrap a handler so it takes (args=None, **kwargs) and never raises."""

    @functools.wraps(fn)
    def wrapper(args=None, **kwargs):
        try:
            return fn(args if isinstance(args, dict) else {}, **kwargs)
        except Exception as e:
            return err("internal_error", f"{type(e).__name__}: {e}")

    return wrapper
