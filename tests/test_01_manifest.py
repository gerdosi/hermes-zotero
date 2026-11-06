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
