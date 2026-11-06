import argparse
import ast
import json
import re
from pathlib import Path

from zotcore import cli, tools
from zotcore.settings import DEFAULTS, Settings
from zotcore.skill import SKILL_NAME

ROOT = Path(__file__).resolve().parents[1]
HOMEPAGE = "https://github.com/gerdosi/hermes-zotero"
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "review", "node_modules"}
SKIP_FILES = {".DS_Store"}
TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".toml", ".txt", ".json", ".cfg", ".ini", ".sh", ""}
# Two of Hermes' install-scanner rules (tools/skills_guard.py, both "critical": one hit blocks every install
# from GitHub). They are the two that task 09's text tripped. Hermes compiles its patterns with IGNORECASE.
HERMES_CONFIG = r"\.hermes/(?:config\.yaml|SOUL\.md)"
CRITICAL = {
    "prompt_injection_ignore": r"ignore\s+(?:\w+\s+)*(previous|all|above|prior)\s+instructions",
    "hermes_config_mod_shell": (
        rf"(?:>>|[\w\"'`)\]]\s*>)\s*[~\w./-]*{HERMES_CONFIG}(?!\.?\w)"
        rf"|\bsed\b[^\n]*\s(?:-[A-Za-z]*i[A-Za-z]*|--in-place)\b[^\n]*{HERMES_CONFIG}(?!\.?\w)"
        rf"|\btee\s+(?:-a\s+)?[~\w./\"'-]*{HERMES_CONFIG}(?!\.?\w)"
        rf"|\b(?:cp|mv)\s+[^\s|;&]+\s+[^\n|;&]{{0,40}}?{HERMES_CONFIG}(?!\.?\w)"),
}
BINARY_MAGIC = (b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce",
                b"\xca\xfe\xba\xbe", b"MZ", b"\x00asm")


def readme():
    return (ROOT / "README.md").read_text(encoding="utf-8")


def manifest():
    return (ROOT / "plugin.yaml").read_text(encoding="utf-8")


def repo_files():
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts) or path.name in SKIP_FILES or not path.is_file():
            continue
        yield rel, path


def section(text, heading):
    start = text.index(f"\n## {heading}\n")
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else len(text)]


def cli_commands():
    parser = argparse.ArgumentParser(prog="hermes zotero")
    cli.setup_parser(parser)
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return set(sub.choices)


# ---------- README -----------------------------------------------------------------------------------

def test_readme_names_every_tool_command_setting_and_the_skill():
    text = readme()
    for spec in tools.tool_specs(Settings):
        assert f"`{spec.name}`" in text
    for command in cli_commands():
        assert f"hermes zotero {command}" in text or f"`{command}`" in text
    for key in DEFAULTS:
        assert f"`{key}`" in text
    assert f"`hermes-zotero:{SKILL_NAME}`" in text
    assert "hermes plugins install " + HOMEPAGE in text and "hermes plugins enable hermes-zotero" in text


def test_readme_commands_exist():
    used = set(re.findall(r"hermes zotero ([a-z]+)", readme()))
    assert used and used <= cli_commands()


def test_readme_settings_table_matches_the_defaults():
    rows = dict(re.findall(r"^\| `([a-z_]+)` \| ([^|]+?) \|", section(readme(), "Settings"), re.M))
    assert set(rows) == set(DEFAULTS)
    for key, default in DEFAULTS.items():
        if default == "":
            assert rows[key] == "empty", key
        elif isinstance(default, tuple):
            assert json.loads(rows[key].strip("`")) == list(default), key
        else:
            assert rows[key] == str(default), key


def test_readme_disclosures():
    text = section(readme(), "Disclosures")
    for needle in ("zotero.sqlite", "prefs.js", ".zotero-ft-cache", "markdown_path", "plugin-data/hermes-zotero",
                   "127.0.0.1:23119", "telemetry", "proxy"):
        assert needle in text, needle
    assert "local API is off by default" in section(readme(), "Citations")


def test_readme_cron_script_parses_and_is_silent_on_success():
    text = readme()
    block = re.search(r"\n  ```python\n(.*?)\n  ```\n", text, re.S).group(1)
    code = "\n".join(line[2:] for line in block.split("\n"))
    tree = ast.parse(code)
    prints = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "print"]
    assert len(prints) == 1 and isinstance(tree.body[-1], ast.If)  # the only print is inside the failure branch
    assert '"zotero", "sync"' in code and "redirect_stdout" in code
    assert "--no-agent --script zotero-sync.py" in text


def test_readme_links_point_to_files():
    links = re.findall(r"\]\(([^)#]+)\)", readme())
    local = [link for link in links if not link.startswith(("http://", "https://"))]
    assert local and all((ROOT / link).exists() for link in local)


def test_readme_matches_the_manifest():
    text = readme()
    floor = re.search(r'^requires_hermes:\s*"?>=([0-9.]+)"?', manifest(), re.M).group(1)
    assert f"Hermes Agent {floor} or later" in text
    assert "MIT" in section(text, "License") and (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")


# ---------- manifest ---------------------------------------------------------------------------------

def test_manifest_release_fields():
    text = manifest()
    assert re.search(r'^homepage:\s*"?' + re.escape(HOMEPAGE) + r'"?\s*$', text, re.M)
    description = re.search(r'^description:\s*"(.+)"\s*$', text, re.M).group(1)
    assert 60 <= len(description) <= 300 and "Zotero" in description
    assert "no network" not in description.lower() and "telemetry" in description
    for rel, path in repo_files():
        if path.suffix in (".md", ".yaml", ".toml") and not str(rel).startswith("tasks"):
            assert "<owner>" not in path.read_text(encoding="utf-8"), rel


# ---------- what Hermes' installer scans -------------------------------------------------------------

def test_repo_text_passes_two_critical_scanner_rules():
    rules = {name: re.compile(rx, re.IGNORECASE) for name, rx in CRITICAL.items()}
    hits = []
    for rel, path in repo_files():
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            hits += [f"{rel}:{n} {name}" for name, rx in rules.items() if rx.search(line)]
    assert hits == []


def test_rules_still_catch_what_they_should():
    shell = re.compile(CRITICAL["hermes_config_mod_shell"], re.IGNORECASE)
    config = "~/.hermes/" + "config.yaml"  # built at run time, so this file itself stays clean
    assert shell.search(f"cp {config}.bak {config}") and shell.search(f"echo x >> {config}")
    assert not shell.search(f"cp {config} {config}.bak")
    phrase = " ".join(("ignore", "previous", "instructions"))
    assert re.search(CRITICAL["prompt_injection_ignore"], phrase.upper(), re.IGNORECASE)


def test_no_binaries_or_bytecode():
    for rel, path in repo_files():
        assert path.suffix not in (".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".wasm"), rel
        with path.open("rb") as f:
            head = f.read(4)
        assert not head.startswith(BINARY_MAGIC), rel


def test_gitignore_keeps_local_files_out():
    lines = set((ROOT / ".gitignore").read_text(encoding="utf-8").split())
    assert {"review/", ".venv/", "__pycache__/", "*.pyc"} <= lines
