"""Locate the Zotero data directory the way Zotero does."""
from __future__ import annotations

import configparser
import json
import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

_PREF_RE = re.compile(r'^\s*user_pref\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*(.*?)\s*\)\s*;\s*$')


@dataclass(frozen=True)
class Candidate:
    """One data directory that was checked."""

    path: str
    source: str
    ok: bool
    reason: str


@dataclass(frozen=True)
class DataDirResult:
    """Outcome of the data directory search."""

    path: str | None
    source: str | None
    candidates: list[Candidate]

    def as_dict(self) -> dict:
        """JSON-friendly form."""
        return {"path": self.path, "source": self.source,
                "checked": [{"path": c.path, "source": c.source, "ok": c.ok, "reason": c.reason}
                            for c in self.candidates]}


def _unescape(raw: str) -> str:
    """Simple fallback unescape for JS string bodies."""
    simple = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}
    out: list[str] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            if nxt == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", raw[i + 2:i + 6]):
                out.append(chr(int(raw[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append(simple.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _value(raw: str) -> object:
    if raw == "true":
        return True
    if raw == "false":
        return False
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        try:
            return json.loads(raw)
        except ValueError:
            return _unescape(raw[1:-1])
    return raw


def parse_prefs(text: str) -> dict[str, object]:
    """Parse user_pref lines from a prefs.js text; never raises."""
    prefs: dict[str, object] = {}
    try:
        for line in text.splitlines():
            m = _PREF_RE.match(line)
            if not m:
                continue
            key = _value('"' + m.group(1) + '"')
            if isinstance(key, str):
                prefs[key] = _value(m.group(2))
    except Exception:
        pass
    return prefs


def profile_roots(system: str, home: Path, env: Mapping[str, str]) -> list[Path]:
    """Zotero profile root directories for this OS."""
    if system == "Darwin":
        return [home / "Library" / "Application Support" / "Zotero"]
    if system == "Windows":
        appdata = env.get("APPDATA")
        return [Path(appdata) / "Zotero" / "Zotero"] if appdata else []
    return [home / ".zotero" / "zotero"]


def _profiles(system: str, root: Path) -> list[Path]:
    """Profile dirs under a root: profiles.ini first (Default=1 first), then others."""
    found: list[Path] = []

    def add(p: Path) -> None:
        if p not in found:
            found.append(p)

    try:
        ini = configparser.RawConfigParser(strict=False)
        ini.read_string((root / "profiles.ini").read_text(encoding="utf-8", errors="replace"))
        listed: list[tuple[int, Path]] = []
        for section in ini.sections():
            if not section.lower().startswith("profile"):
                continue
            path = ini.get(section, "Path", fallback="").strip()
            if not path:
                continue
            rel = ini.get(section, "IsRelative", fallback="1").strip() != "0"
            default = ini.get(section, "Default", fallback="0").strip() == "1"
            listed.append((0 if default else 1, root / path if rel else Path(path)))
        for _, p in sorted(listed, key=lambda t: t[0]):
            add(p)
    except Exception:
        pass
    try:
        base = root / "Profiles" if system in ("Darwin", "Windows") else root
        for p in sorted(base.glob("*/")):
            if (p / "prefs.js").is_file():
                add(p)
    except Exception:
        pass
    return found


def check_data_dir(path: Path) -> tuple[bool, str]:
    """Check a candidate directory without opening the database."""
    try:
        if not path.is_dir():
            return False, "no zotero.sqlite here (not a directory)"
        if not (path / "zotero.sqlite").is_file():
            return False, "no zotero.sqlite here"
        if not (path / "storage").is_dir():
            return True, "ok, but no storage/ folder (library may have no attachments)"
        return True, "ok"
    except OSError as e:
        return False, f"cannot check zotero.sqlite here ({type(e).__name__})"


def resolve_data_dir(configured: str, *, system: str | None = None,
                     home: Path | None = None,
                     env: Mapping[str, str] | None = None) -> DataDirResult:
    """Find the data directory: config, then profile prefs, then ~/Zotero."""
    system = system or platform.system()
    home = home if home is not None else Path.home()
    env = env if env is not None else os.environ
    candidates: list[Candidate] = []

    if configured:
        if configured == "~" or configured.startswith(("~/", "~\\")):
            path = home / configured[2:] if len(configured) > 1 else home
        else:
            path = Path(configured)
        ok, reason = check_data_dir(path)
        candidates.append(Candidate(str(path), "config", ok, reason))
        return DataDirResult(str(path) if ok else None, "config", candidates)

    for root in profile_roots(system, home, env):
        for profile in _profiles(system, root):
            try:
                text = (profile / "prefs.js").read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            prefs = parse_prefs(text)
            value = prefs.get("extensions.zotero.dataDir")
            if isinstance(value, str) and value and prefs.get("extensions.zotero.useDataDir") is not False:
                ok, reason = check_data_dir(Path(value))
                candidates.append(Candidate(value, f"prefs:{profile}", ok, reason))

    default = home / "Zotero"
    ok, reason = check_data_dir(default)
    candidates.append(Candidate(str(default), "default", ok, reason))

    for c in candidates:
        if c.ok:
            return DataDirResult(c.path, c.source, candidates)
    return DataDirResult(None, None, candidates)
