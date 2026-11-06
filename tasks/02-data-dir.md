# Task 02 — Find the Zotero data directory

| | |
| --- | --- |
| Executor | DeepSeek V4.1 Flash 1017 |
| Reasoning | **low** (`/reasoning low`). If the `profiles.ini` or escaping tests fail twice, rerun at **medium**. |
| Budget | ≤ 40 tool calls |
| Depends on | task 01 committed, all its tests green |
| Done when | `python -m pytest` shows **37 passed** (23 old + 14 new), checksums match, report committed |

## Goal

Locate the user's Zotero data directory the way Zotero does: a configured override first, then the `extensions.zotero.dataDir` preference in Zotero's profile, then `~/Zotero`. Explain every candidate checked. Report the result in `zotero_status` and `hermes zotero doctor`.

## Files

```
create  zotcore/datadir.py
create  tests/test_02_datadir.py   (verbatim, below)
modify  zotcore/tools.py           (status gains a data_dir block)
modify  zotcore/cli.py             (doctor prints the data dir and the candidates)
```

Touch nothing else. Do not edit task 01 tests.

## Facts (verified against zotero-mcp's working code)

- Zotero profile roots:
  - macOS: `~/Library/Application Support/Zotero`, with profiles under `Profiles/*/`
  - Windows: `%APPDATA%\Zotero\Zotero`, with profiles under `Profiles\*\`
  - Linux: `~/.zotero/zotero`, with profiles **directly** under it (`*/`)
- Each profile has a `prefs.js` with lines like `user_pref("extensions.zotero.dataDir", "/Users/g/Zotero");` and `user_pref("extensions.zotero.useDataDir", true);`. Values are JavaScript literals: strings with JSON-style escapes (`\\`, `\"`, `\uXXXX`), `true`/`false`, or integers.
- A root may hold a Firefox-style `profiles.ini` with sections `[ProfileN]` and keys `Path=`, `IsRelative=1|0` and `Default=1`.
- A data directory is valid when it contains a **file** `zotero.sqlite`. The `storage/` folder may be missing in a library without attachments; that is still valid, with a note.

## Spec — `zotcore/datadir.py`

```python
@dataclass(frozen=True)
class Candidate:
    path: str          # as checked
    source: str        # "config" | "prefs:<profile dir>" | "default"
    ok: bool
    reason: str        # "ok" | "ok, but no storage/ folder (...)" | "no zotero.sqlite here" | ...

@dataclass(frozen=True)
class DataDirResult:
    path: str | None
    source: str | None
    candidates: list[Candidate]
    def as_dict(self) -> dict  # {"path", "source", "checked": [ {path, source, ok, reason}, ... ]}

def parse_prefs(text: str) -> dict[str, object]
def profile_roots(system: str, home: Path, env: Mapping[str, str]) -> list[Path]
def check_data_dir(path: Path) -> tuple[bool, str]
def resolve_data_dir(configured: str, *, system: str | None = None,
                     home: Path | None = None, env: Mapping[str, str] | None = None) -> DataDirResult
```

Rules:

1. `parse_prefs` ignores lines that are not `user_pref(...)`. It decodes strings with JSON rules and falls back to a simple unescape if that fails. It never raises.
2. `profile_roots`: one root per OS as above. On Windows without `APPDATA`, return `[]`. `system` uses `platform.system()` names: `"Darwin"`, `"Windows"`, `"Linux"`.
3. Profile order within a root: profiles listed in `profiles.ini` first, with `Default=1` before others; `IsRelative=1` paths are relative to the root. Then any other profile folders containing `prefs.js` (glob as above), sorted. Each profile at most once. A broken `profiles.ini` is ignored.
4. `resolve_data_dir`:
   - Defaults: `system=platform.system()`, `home=Path.home()`, `env=os.environ`.
   - If `configured` is non-empty: expand a leading `~` against `home` (not the real home) and check it. **No fallback:** return `path=None, source="config"` if it is invalid. An explicit setting that is wrong must be fixed, not silently replaced.
   - Otherwise, for each root and profile in order: read `prefs.js` (UTF-8, `errors="replace"`, skip on any error). If `extensions.zotero.dataDir` is a non-empty string and `extensions.zotero.useDataDir` is **not** `False`, add a candidate with source `"prefs:<profile dir>"`.
   - Then add the candidate `home / "Zotero"` with source `"default"`.
   - Return the first `ok` candidate; if there is none, `path=None, source=None`. `candidates` always lists everything checked, in order.
   - Never open `zotero.sqlite`; check existence only (AGENTS.md rule 1).
5. `zotero_status` adds `data_dir=resolve_data_dir(s.zotero_data_dir).as_dict()` to its output. Keep every existing key.
6. `hermes zotero doctor` adds a `Zotero data directory:` section showing the chosen path and source (or `not found`), then one line per candidate: `  [ok|--] <source>: <path> (<reason>)`. If it is not found, add a hint: set `zotero_data_dir` under `plugins.entries.hermes-zotero.settings` in `~/.hermes/config.yaml`.

## Acceptance tests (copy verbatim, then verify checksums)

| File | SHA-256 |
| --- | --- |
| `tests/test_02_datadir.py` | `c2fc38ac192dcb590bbd8aedf0c622c4a9469bd6445d7728110236e79d9798e2` |

### `tests/test_02_datadir.py`

```python
import json
from pathlib import Path

from zotcore import tools
from zotcore.datadir import parse_prefs, profile_roots, resolve_data_dir
from zotcore.settings import Settings


def make_data_dir(path: Path, storage=True) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "zotero.sqlite").write_bytes(b"")
    if storage:
        (path / "storage").mkdir(exist_ok=True)
    return path


def write_prefs(profile: Path, data_dir: Path | None, use_data_dir=True):
    profile.mkdir(parents=True, exist_ok=True)
    lines = ['// Mozilla User Preferences', 'user_pref("extensions.zotero.firstRun2", false);']
    if data_dir is not None:
        lines.append(f'user_pref("extensions.zotero.dataDir", {json.dumps(str(data_dir))});')
        lines.append(f'user_pref("extensions.zotero.useDataDir", {"true" if use_data_dir else "false"});')
    (profile / "prefs.js").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_parse_prefs_types_and_escapes():
    text = "\n".join([
        "// comment line",
        'user_pref("extensions.zotero.dataDir", "/Users/g/Zotero Data");',
        'user_pref("extensions.zotero.useDataDir", true);',
        'user_pref("extensions.zotero.flag", false);',
        'user_pref("extensions.zotero.count", 42);',
        r'user_pref("x.win", "C:\\Users\\G\u00e1bor\\Zotero \"q\"");',
        "garbage that is not a pref",
    ])
    prefs = parse_prefs(text)
    assert prefs["extensions.zotero.dataDir"] == "/Users/g/Zotero Data"
    assert prefs["extensions.zotero.useDataDir"] is True
    assert prefs["extensions.zotero.flag"] is False
    assert prefs["extensions.zotero.count"] == 42
    assert prefs["x.win"] == 'C:\\Users\\Gábor\\Zotero "q"'


def test_profile_roots_per_os(tmp_path):
    home = tmp_path / "home"
    assert profile_roots("Darwin", home, {}) == [home / "Library" / "Application Support" / "Zotero"]
    assert profile_roots("Linux", home, {}) == [home / ".zotero" / "zotero"]
    appdata = tmp_path / "AppData" / "Roaming"
    assert profile_roots("Windows", home, {"APPDATA": str(appdata)}) == [appdata / "Zotero" / "Zotero"]
    assert profile_roots("Windows", home, {}) == []


def test_mac_profile_data_dir(tmp_path):
    home = tmp_path / "home"
    data_dir = make_data_dir(tmp_path / "custom data")
    write_prefs(home / "Library/Application Support/Zotero/Profiles/abc.default", data_dir)
    result = resolve_data_dir("", system="Darwin", home=home, env={})
    assert result.path == str(data_dir)
    assert result.source.startswith("prefs:")


def test_default_home_zotero(tmp_path):
    home = tmp_path / "home"
    data_dir = make_data_dir(home / "Zotero")
    result = resolve_data_dir("", system="Linux", home=home, env={})
    assert result.path == str(data_dir)
    assert result.source == "default"


def test_use_data_dir_false_is_ignored(tmp_path):
    home = tmp_path / "home"
    default = make_data_dir(home / "Zotero")
    other = make_data_dir(tmp_path / "old place")
    write_prefs(home / ".zotero/zotero/p1.default", other, use_data_dir=False)
    result = resolve_data_dir("", system="Linux", home=home, env={})
    assert result.path == str(default)


def test_profiles_ini_default_profile_wins(tmp_path):
    home = tmp_path / "home"
    root = home / ".zotero" / "zotero"
    dir_a = make_data_dir(tmp_path / "A")
    dir_b = make_data_dir(tmp_path / "B")
    write_prefs(root / "a.default", dir_a)
    write_prefs(root / "b.default", dir_b)
    (root / "profiles.ini").write_text(
        "[General]\nStartWithLastProfile=1\n\n"
        "[Profile0]\nName=a\nIsRelative=1\nPath=a.default\n\n"
        "[Profile1]\nName=b\nIsRelative=1\nPath=b.default\nDefault=1\n", encoding="utf-8")
    result = resolve_data_dir("", system="Linux", home=home, env={})
    assert result.path == str(dir_b)


def test_windows_appdata_profile(tmp_path):
    home = tmp_path / "home"
    appdata = tmp_path / "AppData" / "Roaming"
    data_dir = make_data_dir(tmp_path / "D")
    write_prefs(appdata / "Zotero/Zotero/Profiles/x.default", data_dir)
    result = resolve_data_dir("", system="Windows", home=home, env={"APPDATA": str(appdata)})
    assert result.path == str(data_dir)


def test_configured_path_wins(tmp_path):
    home = tmp_path / "home"
    make_data_dir(home / "Zotero")
    configured = make_data_dir(tmp_path / "configured")
    result = resolve_data_dir(str(configured), system="Linux", home=home, env={})
    assert result.path == str(configured)
    assert result.source == "config"


def test_invalid_configured_path_does_not_fall_back(tmp_path):
    home = tmp_path / "home"
    make_data_dir(home / "Zotero")
    result = resolve_data_dir(str(tmp_path / "nope"), system="Linux", home=home, env={})
    assert result.path is None
    assert result.source == "config"
    assert result.candidates[0].ok is False
    assert "zotero.sqlite" in result.candidates[0].reason


def test_tilde_expands_against_given_home(tmp_path):
    home = tmp_path / "home"
    data_dir = make_data_dir(home / "Library" / "ZoteroData")
    result = resolve_data_dir("~/Library/ZoteroData", system="Darwin", home=home, env={})
    assert result.path == str(data_dir)


def test_nothing_found_lists_what_was_checked(tmp_path):
    result = resolve_data_dir("", system="Linux", home=tmp_path / "home", env={})
    assert result.path is None and result.source is None
    assert result.candidates
    assert all(c.ok is False and c.reason for c in result.candidates)


def test_missing_storage_is_ok_but_noted(tmp_path):
    home = tmp_path / "home"
    make_data_dir(home / "Zotero", storage=False)
    result = resolve_data_dir("", system="Linux", home=home, env={})
    assert result.path == str(home / "Zotero")
    chosen = [c for c in result.candidates if c.ok][0]
    assert "storage" in chosen.reason


def test_unreadable_prefs_do_not_crash(tmp_path):
    home = tmp_path / "home"
    profile = home / ".zotero/zotero/bad.default"
    profile.mkdir(parents=True)
    (profile / "prefs.js").write_bytes(b"\xff\xfe\x00garbage\x00")
    make_data_dir(home / "Zotero")
    result = resolve_data_dir("", system="Linux", home=home, env={})
    assert result.path == str(home / "Zotero")


def test_status_reports_data_dir(tmp_path):
    data_dir = make_data_dir(tmp_path / "Z")
    specs = {s.name: s for s in tools.tool_specs(lambda: Settings(zotero_data_dir=str(data_dir)))}
    out = json.loads(specs["zotero_status"].handler({}))
    assert out["ok"] is True
    assert out["data_dir"]["path"] == str(data_dir)
    assert out["data_dir"]["source"] == "config"
    assert isinstance(out["data_dir"]["checked"], list)
```


## Commands

```bash
python -m pytest                        # expect: 37 passed
shasum -a 256 tests/test_02_datadir.py  # must match
```

## Live check (Gábor)

```bash
hermes zotero doctor
```

Compare the path with Zotero → Settings → Advanced → Files and Folders → Data Directory Location. Paste both into the report, along with the candidate list.

## Out of scope

Reading the database, snapshots and groups.
