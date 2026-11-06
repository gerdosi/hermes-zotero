# Task 01 — Scaffold: manifest, settings, status tool, CLI

| | |
| --- | --- |
| Executor | DeepSeek V4.1 Flash 1017 |
| Reasoning | **low** (`/reasoning low`). Rerun at **medium** only if the report says BLOCKED. |
| Budget | ≤ 40 tool calls |
| Depends on | an empty git repo with `AGENTS.md` and `tasks/` committed |
| Done when | `python -m pytest` shows **23 passed**, checksums match, report committed |

## Goal

Create a plugin that Hermes can load. It has one tool (`zotero_status`), one CLI command (`hermes zotero doctor`) and a typed settings layer. Later tasks build on this, so follow the names exactly.

## Files

Create exactly these, and nothing else:

```
plugin.yaml            (content below; only requires_hermes changes)
pyproject.toml         (content below, verbatim)
LICENSE                (MIT, "Copyright (c) 2026 Gábor Erdősi")
README.md              (stub: title + one paragraph + "Status: work in progress")
.gitignore             (__pycache__/, *.pyc, .pytest_cache/, .venv/)
__init__.py            (content below, verbatim)
zotcore/__init__.py
zotcore/settings.py
zotcore/jsonout.py
zotcore/tools.py
zotcore/cli.py
tests/conftest.py              (verbatim, below)
tests/test_01_settings.py      (verbatim, below)
tests/test_01_tools.py         (verbatim, below)
tests/test_01_register.py      (verbatim, below)
tests/test_01_manifest.py      (verbatim, below)
```

## Spec

### `plugin.yaml`

Use this content. Replace `>=0.0.0` with `>=` plus the version printed by `hermes --version` (digits and dots only, e.g. `>=0.24.1`). If `hermes` is not on PATH, leave `>=0.0.0` and say so in the report.

```yaml
name: hermes-zotero
version: "0.1.0"
manifest_version: 2
description: "Read-only local index of your Zotero library: search and read papers you already own, even with Zotero closed. No network, no writes."
author: "Gábor Erdősi"
license: MIT
homepage: "https://github.com/<owner>/hermes-zotero"
requires_hermes: ">=0.0.0"
provides_tools:
  - zotero_status
config_schema:
  zotero_data_dir: {type: str, default: "", description: "Zotero data directory. Empty = find it from Zotero's prefs.js, then ~/Zotero."}
  markdown_path: {type: str, default: "", description: "Optional folder of your own converted Markdown papers; preferred over Zotero's text cache."}
  libraries: {type: list, default: [user], description: "Libraries to index: 'user' and/or numeric group IDs."}
  coverage_strong_min: {type: int, default: 8, description: "Matching papers needed for a 'strong' coverage verdict."}
  coverage_recent_min: {type: int, default: 2, description: "Recent matching papers needed for 'strong'."}
  coverage_recent_years: {type: int, default: 5, description: "How many years count as recent."}
  sync_batch_items: {type: int, default: 200, description: "Items indexed per transaction during sync."}
  sync_tool_budget_seconds: {type: int, default: 30, description: "Time limit for one zotero_sync tool call (5-60)."}
  read_max_chars_default: {type: int, default: 4000, description: "Default characters returned by zotero_read."}
  read_max_chars_cap: {type: int, default: 12000, description: "Hard cap on characters returned by zotero_read."}
```

### `pyproject.toml`

```toml
[project]
name = "hermes-zotero"
version = "0.1.0"
description = "Read-only local Zotero index for Hermes Agent"
requires-python = ">=3.11"
license = "MIT"
authors = [{ name = "Gábor Erdősi" }]
dependencies = []

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
addopts = "--import-mode=importlib -q"
```

### `__init__.py` (repo root, Hermes glue)

```python
"""Hermes glue for hermes-zotero. All logic lives in zotcore/."""
from .zotcore import __version__, cli, tools
from .zotcore.settings import Settings


def register(ctx):
    def settings() -> Settings:
        return Settings.from_getter(ctx.get_config)

    for spec in tools.tool_specs(settings):
        ctx.register_tool(name=spec.name, toolset="zotero", schema=spec.schema,
                          handler=spec.handler, description=spec.description, emoji="📚")

    ctx.register_cli_command(
        name="zotero",
        help="Local, read-only Zotero library index",
        setup_fn=cli.setup_parser,
        handler_fn=lambda args: cli.run(args, settings()),
        description="Check and maintain the local Zotero index used by the zotero_* tools.",
    )
```

Settings are read **at call time** through `ctx.get_config(key, default)`. That method reads `plugins.entries.hermes-zotero.settings.<key>` from `~/.hermes/config.yaml`.

### `zotcore/__init__.py`

Only `__version__ = "0.1.0"` (plus a docstring).

### `zotcore/settings.py`

- `DEFAULTS: dict[str, object]`, one entry per setting, with the defaults from `plugin.yaml`. `libraries` defaults to the tuple `("user",)`.
- `@dataclass(frozen=True) class Settings` with these fields in this order, each defaulting to its `DEFAULTS` value: `zotero_data_dir: str`, `markdown_path: str`, `libraries: tuple[str, ...]`, `coverage_strong_min: int`, `coverage_recent_min: int`, `coverage_recent_years: int`, `sync_batch_items: int`, `sync_tool_budget_seconds: int`, `read_max_chars_default: int`, `read_max_chars_cap: int`. Last comes `warnings: tuple[str, ...] = ()`.
- `Settings.from_getter(get) -> Settings`, where `get(key, default)` is `ctx.get_config`. Rules:
  1. Call `get(key, DEFAULTS[key])` for every key. If the call raises, use the default and add a warning that names the key.
  2. String settings must be `str`; otherwise use the default and add a warning naming the key.
  3. Integer settings must be `int` and **not** `bool`; otherwise use the default and add a warning. Then clamp to these ranges, with a warning when clamped: `coverage_strong_min` 1–1000, `coverage_recent_min` 0–1000, `coverage_recent_years` 1–50, `sync_batch_items` 10–5000, `sync_tool_budget_seconds` 5–60, `read_max_chars_cap` 1000–50000, `read_max_chars_default` 500–50000.
  4. After clamping, if `read_max_chars_default > read_max_chars_cap`, set it to the cap and add a warning.
  5. `libraries` must be a list or tuple. Keep entries that are `"user"`, strings of digits, or non-bool ints (converted to `str`). Drop anything else with a warning containing `libraries`. If nothing is left, use `("user",)` with a warning.
- `Settings.as_dict() -> dict`: every field except `warnings`, with tuples turned into lists (JSON-friendly).

### `zotcore/jsonout.py`

- `ok(**data) -> str`: `json.dumps({"ok": True, **data}, ensure_ascii=False)`.
- `err(code, message, hint=None) -> str`: `{"ok": false, "error": {"code", "message", "hint"?}}`.
- `safe(fn)` decorator: the wrapper takes `(args=None, **kwargs)`, passes `args` through if it is a dict and `{}` otherwise, and turns any `Exception` into `err("internal_error", f"{type(e).__name__}: {e}")`.

### `zotcore/tools.py`

- `@dataclass(frozen=True) class ToolSpec: name: str; schema: dict; handler: Callable; description: str`.
- `tool_specs(settings_provider) -> list[ToolSpec]`. `settings_provider()` returns a `Settings` and is called inside each handler, never at import time.
- One tool for now, `zotero_status`:
  - schema `{"name": "zotero_status", "description": DESC, "parameters": {"type": "object", "properties": {}}}`
  - `DESC = "Zotero library index status: whether the local Zotero index is ready, how fresh it is, and what it holds."`
  - The handler is wrapped in `safe` and returns `ok(plugin_version=__version__, stage="scaffold", settings=s.as_dict(), warnings=list(s.warnings))`.

### `zotcore/cli.py`

- `setup_parser(parser)`: adds subparsers with `dest="zotero_cmd"` and one subcommand, `doctor` ("Check settings and Zotero access"). Store the parser so `run` can print help (e.g. `parser.set_defaults(_zparser=parser)`).
- `run(args, settings) -> int`:
  - `doctor`: print `hermes-zotero <version>`, then each setting as `  key: value`, then each warning as `  warning: ...`. Return 0.
  - No subcommand: print the parser's help. Return 0.

## Acceptance tests (copy verbatim, then verify checksums)

| File | SHA-256 |
| --- | --- |
| `tests/conftest.py` | `2f3c8090988e03d2ddc00ce0dcf6a255654688b1f5ed8d8b88ed861dbde30f23` |
| `tests/test_01_settings.py` | `00bd02767cea6f6d573d07b88d680d45f54ec30e82360d9db0cf2a708f63b6de` |
| `tests/test_01_tools.py` | `7eae6e382bc128cead30a07912c39963d5248707502564f5e8853a2877e29bfc` |
| `tests/test_01_register.py` | `6607ff97a3bbf1d03dafaa657610ca28efd92e6ecf1cd3b7fd83a5be62024f24` |
| `tests/test_01_manifest.py` | `f073b1a55bcd9c7828b5911686c522241ad5cdb116e1982d7d372c9e8a2349f0` |

### `tests/conftest.py`

```python
"""Shared test helpers. Created by task 01; later tasks may only ADD fixtures here."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


class FakeCtx:
    """Minimal stand-in for Hermes' PluginContext (signatures from hermes_cli/plugins.py @ ed1afb0)."""

    def __init__(self, config=None):
        self.config = dict(config or {})
        self.tools = {}
        self.cli = {}
        self.skills = {}

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def register_tool(self, name, toolset, schema, handler, check_fn=None, requires_env=None,
                      is_async=False, description="", emoji="", override=False):
        assert name not in self.tools, f"duplicate tool {name}"
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler,
                            "description": description}

    def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
        self.cli[name] = {"help": help, "setup_fn": setup_fn, "handler_fn": handler_fn}

    def register_skill(self, name, path, description="", frontmatter=None):
        self.skills[name] = {"path": Path(path), "description": description}


@pytest.fixture
def plugin_module():
    """Load the repo root as a package the way Hermes' loader does (submodule_search_locations)."""
    name = "hermes_zotero_under_test"
    for key in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        sys.modules.pop(key)
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_ctx():
    return FakeCtx()
```

### `tests/test_01_settings.py`

```python
from dataclasses import fields

from zotcore.settings import DEFAULTS, Settings


def getter(values):
    return lambda key, default=None: values.get(key, default)


def test_defaults():
    s = Settings.from_getter(getter({}))
    assert s.zotero_data_dir == ""
    assert s.markdown_path == ""
    assert s.libraries == ("user",)
    assert s.coverage_strong_min == 8
    assert s.coverage_recent_min == 2
    assert s.coverage_recent_years == 5
    assert s.sync_batch_items == 200
    assert s.sync_tool_budget_seconds == 30
    assert s.read_max_chars_default == 4000
    assert s.read_max_chars_cap == 12000
    assert s.warnings == ()


def test_defaults_table_matches_dataclass():
    assert set(DEFAULTS) == {f.name for f in fields(Settings)} - {"warnings"}


def test_wrong_type_falls_back_with_warning():
    s = Settings.from_getter(getter({"sync_batch_items": "lots", "zotero_data_dir": 5}))
    assert s.sync_batch_items == 200
    assert s.zotero_data_dir == ""
    assert any("sync_batch_items" in w for w in s.warnings)
    assert any("zotero_data_dir" in w for w in s.warnings)


def test_bool_is_not_accepted_as_int():
    s = Settings.from_getter(getter({"sync_batch_items": True}))
    assert s.sync_batch_items == 200
    assert s.warnings


def test_clamping():
    s = Settings.from_getter(getter({"sync_tool_budget_seconds": 600, "read_max_chars_default": 50000}))
    assert s.sync_tool_budget_seconds == 60
    assert s.read_max_chars_default == 12000  # never above read_max_chars_cap
    assert len(s.warnings) >= 2


def test_libraries_accepts_yaml_ints_and_drops_junk():
    s = Settings.from_getter(getter({"libraries": ["user", 4805701, "123", "bad", None]}))
    assert s.libraries == ("user", "4805701", "123")
    assert any("libraries" in w for w in s.warnings)


def test_empty_libraries_falls_back_to_user():
    s = Settings.from_getter(getter({"libraries": []}))
    assert s.libraries == ("user",)
    assert s.warnings


def test_getter_that_raises_gives_defaults():
    def boom(key, default=None):
        raise RuntimeError("config unreadable")
    s = Settings.from_getter(boom)
    assert s.sync_batch_items == 200
    assert s.warnings


def test_settings_is_immutable():
    s = Settings()
    try:
        s.sync_batch_items = 5
    except Exception:
        return
    raise AssertionError("Settings must be frozen")
```

### `tests/test_01_tools.py`

```python
import json

from zotcore import __version__, tools
from zotcore.settings import Settings


def specs(provider=Settings):
    return {spec.name: spec for spec in tools.tool_specs(provider)}


def test_status_tool_exists_and_schema_is_well_formed():
    all_specs = specs()
    assert "zotero_status" in all_specs
    for name, spec in all_specs.items():
        assert spec.schema["name"] == name
        assert isinstance(spec.schema["description"], str) and 20 <= len(spec.schema["description"]) <= 1024
        # Tool Search lists the first ~60 characters: they must say what library this is.
        assert "Zotero" in spec.schema["description"][:60]
        assert spec.schema["parameters"]["type"] == "object"
        assert name.startswith("zotero_")


def test_status_returns_json_string():
    out = specs()["zotero_status"].handler({})
    assert isinstance(out, str)
    data = json.loads(out)
    assert data["ok"] is True
    assert data["plugin_version"] == __version__
    assert data["settings"]["libraries"] == ["user"]
    assert data["warnings"] == []


def test_handler_tolerates_junk_args_and_kwargs():
    handler = specs()["zotero_status"].handler
    assert json.loads(handler({"junk": 1}, task_id="t1"))["ok"] is True
    assert json.loads(handler(None))["ok"] is True


def test_handler_never_raises():
    def broken_provider():
        raise RuntimeError("kaboom")
    handler = specs(broken_provider)["zotero_status"].handler
    data = json.loads(handler({}))
    assert data["ok"] is False
    assert data["error"]["code"] == "internal_error"
    assert "kaboom" in data["error"]["message"]
```

### `tests/test_01_register.py`

```python
import argparse
import json


def test_register_tools_and_cli(plugin_module, fake_ctx):
    plugin_module.register(fake_ctx)
    assert "zotero_status" in fake_ctx.tools
    assert {t["toolset"] for t in fake_ctx.tools.values()} == {"zotero"}
    assert "zotero" in fake_ctx.cli


def test_handler_reads_config_at_call_time(plugin_module, fake_ctx):
    plugin_module.register(fake_ctx)
    handler = fake_ctx.tools["zotero_status"]["handler"]
    fake_ctx.config["sync_batch_items"] = 321
    assert json.loads(handler({}))["settings"]["sync_batch_items"] == 321


def test_cli_doctor(plugin_module, fake_ctx, capsys):
    plugin_module.register(fake_ctx)
    entry = fake_ctx.cli["zotero"]
    parser = argparse.ArgumentParser(prog="hermes zotero")
    entry["setup_fn"](parser)
    rc = entry["handler_fn"](parser.parse_args(["doctor"]))
    out = capsys.readouterr().out
    assert rc == 0
    assert "hermes-zotero" in out
    assert plugin_module.__version__ in out


def test_cli_without_subcommand_prints_help(plugin_module, fake_ctx, capsys):
    plugin_module.register(fake_ctx)
    entry = fake_ctx.cli["zotero"]
    parser = argparse.ArgumentParser(prog="hermes zotero")
    entry["setup_fn"](parser)
    rc = entry["handler_fn"](parser.parse_args([]))
    assert rc == 0
    assert "doctor" in capsys.readouterr().out
```

### `tests/test_01_manifest.py`

```python
import ast
import re
import sys
import tomllib
from pathlib import Path

from zotcore import __version__, tools
from zotcore.settings import DEFAULTS, Settings

ROOT = Path(__file__).resolve().parents[1]


def manifest_text():
    return (ROOT / "plugin.yaml").read_text(encoding="utf-8")


def yaml_list(text, key):
    block = re.search(rf"^{key}:\s*\n((?:\s+-\s+.+\n?)+)", text, re.M)
    return [] if not block else [l.split("-", 1)[1].strip().strip("'\"") for l in block.group(1).splitlines() if l.strip()]


def yaml_scalar(text, key):
    m = re.search(rf"^{key}:\s*(.+)$", text, re.M)
    return None if not m else m.group(1).strip().strip("'\"")


def test_manifest_identity():
    text = manifest_text()
    assert yaml_scalar(text, "name") == "hermes-zotero"
    assert yaml_scalar(text, "version") == __version__
    assert yaml_scalar(text, "manifest_version") == "2"
    assert yaml_scalar(text, "license") == "MIT"
    assert (yaml_scalar(text, "requires_hermes") or "").startswith(">=")


def test_pyproject_version_matches():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__
    assert data["project"].get("dependencies", []) == []


def test_provides_tools_matches_registered_tools():
    declared = set(yaml_list(manifest_text(), "provides_tools"))
    registered = {spec.name for spec in tools.tool_specs(Settings)}
    assert declared == registered


def test_config_schema_declares_every_setting():
    text = manifest_text()
    for key in DEFAULTS:
        assert re.search(rf"^\s+{key}:", text, re.M), f"config_schema is missing {key}"


def test_no_python_dependencies_declared():
    assert yaml_list(manifest_text(), "python_dependencies") == []


def test_zotcore_imports_stdlib_only():
    allowed = set(sys.stdlib_module_names) | {"zotcore"}
    for path in (ROOT / "zotcore").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                assert name in allowed, f"{path.name} imports non-stdlib module {name}"
```


## Commands

```bash
python -m pytest                                  # expect: 23 passed
shasum -a 256 tests/conftest.py tests/test_01_*.py # must match the table above
```

## Live check (Gábor, on your Mac)

```bash
ln -s ~/Developer/hermes-zotero ~/.hermes/plugins/hermes-zotero
hermes plugins enable hermes-zotero
hermes plugins validate ~/Developer/hermes-zotero --install-deps   # expect: no failures; read every warning
hermes plugins doctor ~/Developer/hermes-zotero                    # expect: zotero_status + CLI command "zotero"
hermes zotero doctor                                               # expect: version and settings, no warnings
```

Then, in a Hermes chat: "Call zotero_status." Expect JSON with `"stage": "scaffold"`. Note whether the model found the tool directly or through `tool_search`.

## Out of scope

The data directory, snapshots, indexing, search, the skill and the README's real content all come in later tasks.
