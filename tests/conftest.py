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
