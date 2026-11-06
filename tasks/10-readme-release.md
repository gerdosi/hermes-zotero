# Task 10 — README, disclosures and a repo that Hermes' installer accepts

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code |
| Reasoning | **medium** (mostly verbatim copies; high is fine too). Set it in the app's model picker before pasting the prompt. |
| Budget | ≤ 30 tool calls |
| Depends on | task 09 committed (133 tests pass) |
| Done when | `.venv/bin/python -m pytest` shows **145 passed** (133 old + 12 new), all checksums match, report committed |

## Goal

Make the plugin ready for strangers and for the catalog:

1. **A real README** with install steps, the tools, settings, the no-agent nightly sync, and the disclosures the catalog requires (admission rule 13: reads outside the plugin's own data, network calls, telemetry).
2. **`plugin.yaml`**: the real `homepage`, and a description that no longer says "No network" (the citation call goes to Zotero on `127.0.0.1`).
3. **Fix a blocker found in review:** Hermes' install scanner reads every file in the repo, documentation included, and two lines of text from task 09 make it return `dangerous`. With that verdict `hermes plugins install` refuses the plugin outright (`--force` does not override it) and `hermes plugins validate` fails. The reviewer has already rewritten those lines; this task commits them and adds a test so it cannot happen again.

## Facts (checked in the Hermes source at 90d6b98, v0.23.0+209)

- `hermes plugins validate <dir>` runs `tools.plugin_guard.scan_plugin` over the whole directory. A `critical` finding gives `dangerous` and fails validation; `high` gives `caution` (passes, with warnings for the catalog reviewer); `medium` and `low` are informational.
- Run on commit c9b19d0 (task 09) it fails with exactly two critical findings, both in `tasks/09-skill-tags-descriptions.md`: line 201, the list of prompt-injection phrases in the embedded test (`prompt_injection_ignore`), and line 487, the `cp` command that restores `config.yaml` in the `.hermes` folder (`hermes_config_mod_shell`). Installing that commit from a Git URL ends with `Decision: BLOCKED`.
- With the reviewer's rewrites below, `hermes plugins validate` (with and without `--install-deps`) passes, the scan verdict is `safe`, and a fresh `hermes plugins install` from the repo, `hermes plugins enable`, `hermes zotero doctor`, `hermes zotero sync` and calls to all four tools through Hermes' tool registry work. The README's nightly sync script was run through `hermes cron create … --no-agent` and `hermes cron run`: silent on success, a message on failure.
- A `caution` verdict also matters: `hermes plugins install` from a Git URL then stops and asks for confirmation (non-interactive installs are refused). So the goal is `safe`, and it is `safe` now: the remaining findings are `medium` or `low`.
- The scanner also reads untracked folders when you validate a working directory. `review/` (the reviewer's notes, with copies of Gábor's own skills) is not part of the plugin, so it goes into `.gitignore`, and validation runs on a fresh clone.
- `hermes config set plugins.entries.hermes-zotero.settings.libraries '["user", "1234567"]'` stores a list, which the plugin reads (checked).

## Files

```
replace README.md                              (verbatim, below)
modify  plugin.yaml                            (description, homepage)
modify  .gitignore                             (add review/)
create  tests/test_10_release.py               (verbatim, below)
create  tasks/10-report.md
commit  tasks/10-readme-release.md, tasks/09-skill-tags-descriptions.md, tasks/09-report.md,
        tests/test_09_skill_and_tags.py, AGENTS.md, tasks/README.md
        (added or updated by the reviewer; commit them as they are and check the checksums below)
```

Do not touch any file in `zotcore/`, `__init__.py`, `skills/`, `pyproject.toml`, `LICENSE`, `tests/conftest.py`, `tests/zfixture.py` or any other test.

## What the reviewer changed (already on disk; commit as is)

- `tests/test_09_skill_and_tags.py`: the two `INJECTION = [...]` lines now build the same phrases from word lists, so the file no longer contains them literally. The test checks exactly what it checked before.
- `tasks/09-skill-tags-descriptions.md`: the same lines in its embedded copy of that test, a note under its checksum table with the new SHA-256, and live-check step 4 reworded without the `cp` command.
- `tasks/09-report.md`: Gábor's calibration marks (agrees with all 20 verdicts).
- `AGENTS.md`: the project summary mentions the loopback call; a new Style paragraph says that committed text must not contain shell commands writing into Hermes' configuration files or prompt-injection phrases, because the installer scans documentation too.
- `tasks/README.md`: the row for this task.

## Spec — `plugin.yaml`

Change exactly two lines (keep the quotes):

```yaml
description: "Search and read the papers in your Zotero library before the web: a local, read-only full-text index that works with Zotero closed. No writes to Zotero, no telemetry; its only network call goes to Zotero on this computer, for citations."
homepage: "https://github.com/gerdosi/hermes-zotero"
```

## Spec — `.gitignore`

Add one line at the end: `review/`

## Spec — `README.md`

Replace the whole file with this text, byte-for-byte (it ends with one newline; the outer fence has four backticks because the README contains code blocks). Do not reword it; if something in it looks wrong, say so in the report.

````markdown
# hermes-zotero

A Hermes Agent plugin that lets the agent search and read the papers in your Zotero library before it goes to the web. It builds a local, read-only full-text index from a copy of Zotero's database, so it works with Zotero open or closed, needs no API key and installs no Python packages.

Ask Hermes things like:

- "What does my library say about SCD1 and ferroptosis? Cite the papers."
- "Is the retatrutide phase 3 trial in my Zotero library? If not, find it online."
- "What did I highlight in the NEJM paper 'Managing Obesity'?"

The agent searches your library first, sees whether it covers the topic well (`strong`), partly (`thin`) or not at all (`none`), reads the relevant passages, and cites them. It uses the web only for what your library lacks.

## What you get

- **Four tools:** `zotero_search`, `zotero_read`, `zotero_status` and `zotero_sync` (details below).
- **A skill**, `hermes-zotero:zotero-library`, that tells the agent to use your library before the web and how to read the results.
- **A command**, `hermes zotero`, with `doctor`, `snapshot` and `sync`.

## Requirements

- Hermes Agent 0.23.0 or later.
- Zotero desktop, with its data directory on the same computer. Tested with Zotero 11 on macOS; the Windows and Linux paths are implemented but not yet tested.
- Zotero's full-text indexing on (the default), so that Zotero has extracted the text of your PDFs.

## Install

```bash
hermes plugins install https://github.com/gerdosi/hermes-zotero
hermes plugins enable hermes-zotero
hermes zotero doctor      # finds your Zotero data directory and shows the settings
hermes zotero sync        # builds the index; safe to stop and run again, it resumes
```

If you use the Hermes gateway (the desktop app or a messaging channel), run `hermes gateway restart` afterwards so it loads the plugin.

`doctor` looks for Zotero's data directory in Zotero's own `prefs.js`, then in `~/Zotero`. If it is somewhere else, set `zotero_data_dir` (see Settings).

## Tools

| Tool | What it does |
| --- | --- |
| `zotero_search` | Full-text search over your library, ranked by passage (BM25). Returns short snippets and a `coverage` verdict: `strong`, `thin` or `none`. Filters: `collection`, `tag`, `year_from`, `year_to`, `library`. `doi` checks whether you hold a given paper. |
| `zotero_read` | Reads a bounded part of one paper: at the best match for a query, or at an offset to page on. `mode` = `annotations` returns your own highlights, comments and notes instead. Every result carries a citation line. |
| `zotero_status` | Whether the index is ready, what it holds, when the snapshot was taken, and what to do next. |
| `zotero_sync` | Adds new and changed papers to the index. Each call stops after `budget_seconds` (default 30) and the next call resumes. |

The coverage verdict counts papers that hold every search word in one passage. `strong` means at least 8 such papers, at least 2 of them from the last 5 years; `thin` means fewer; `none` means no paper has them all. The three numbers are settings.

## Keeping the index up to date

New papers reach the index in one of three ways:

- Run `hermes zotero sync` yourself. Re-checking an unchanged library takes a second or two.
- Ask the agent ("bring my Zotero index up to date"); it calls `zotero_sync`.
- Schedule it without the agent, so no model is called. Save this as `zotero-sync.py` in Hermes' `scripts` folder (`~/.hermes/scripts/`):

  ```python
  import contextlib, io, sys

  from hermes_cli.main import main

  log, code = io.StringIO(), 0
  sys.argv = ["hermes", "zotero", "sync"]
  try:
      with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
          main()
  except SystemExit as exit_:
      code = exit_.code
  if code not in (0, None):
      print(f"hermes zotero sync failed ({code}):\n" + log.getvalue()[-2000:])
  ```

  Then run `hermes cron create "17 4 * * *" --no-agent --script zotero-sync.py --name "Zotero index sync"`. Hermes runs it every night at 04:17 while its gateway is running. It prints nothing when the sync works, so you only hear about failures.

## Settings

Set them with `hermes config set plugins.entries.hermes-zotero.settings.<name> <value>`, for example:

```bash
hermes config set plugins.entries.hermes-zotero.settings.libraries '["user", "1234567"]'
```

| Setting | Default | Meaning |
| --- | --- | --- |
| `zotero_data_dir` | empty | Zotero data directory. Empty: found from Zotero's `prefs.js`, then `~/Zotero`. |
| `markdown_path` | empty | Optional folder of your own Markdown conversions (see Text sources). |
| `libraries` | `["user"]` | Libraries to index: `user` (My Library) and group IDs (the number in the group's address on zotero.org). |
| `coverage_strong_min` | 8 | Papers needed for a `strong` verdict. |
| `coverage_recent_min` | 2 | Recent papers needed for `strong`. |
| `coverage_recent_years` | 5 | How many years count as recent. |
| `sync_batch_items` | 200 | Papers indexed per database transaction during a sync. |
| `sync_tool_budget_seconds` | 30 | Time limit of one `zotero_sync` call (5–60). |
| `read_max_chars_default` | 4000 | Characters `zotero_read` returns when the agent does not ask for a size. |
| `read_max_chars_cap` | 12000 | Most characters one `zotero_read` call returns. |

## Text sources

For each paper the index takes the best text it can find, in this order:

1. **Your own Markdown**, if `markdown_path` is set: one file per paper, named `K:<Zotero item key>.md` or `doi_<DOI>.md` (the DOI in lower case, with every character other than letters, digits, dots and hyphens replaced by `_`), directly in that folder or in its `library` subfolder. Files under 200 bytes are skipped. Headings become sections in the results.
2. **Zotero's full-text cache** (`.zotero-ft-cache` next to each stored PDF), the text Zotero extracted itself.
3. **The title and abstract** only.

Results say which source was used and flag papers whose body text is missing: `body_not_read` (no text found), `scanned_or_empty` (a stored PDF with little or no extracted text: a scan without OCR, or a PDF Zotero has not indexed yet) and `truncated` (Zotero indexed only the first pages; raise Zotero's indexing limits to fix it).

## Citations

Every `zotero_read` result has a citation line. When Zotero is running and its local API is on, the citation is Zotero's own APA reference. Otherwise it is an approximate author-year line built from the index and marked `approximate: true`.

Zotero's local API is off by default. To switch it on: Zotero → Settings → Advanced → "Allow other applications on this computer to communicate with Zotero". While it is on, any program on your computer can read your library through it. The plugin works either way.

## Disclosures

What the plugin reads, writes and connects to:

- **Reads outside its own folder:** your Zotero data directory (it copies `zotero.sqlite` and its write-ahead log, and reads the `.zotero-ft-cache` text files in `storage/`), Zotero's profile file `prefs.js` (only to find the data directory), and the `markdown_path` folder if you set one.
- **Writes:** only to its own data folder in your Hermes profile (`plugin-data/hermes-zotero`): the snapshot copy, the index and a lock file. Zotero's own database is only copied, never written to, locked or opened with SQLite.
- **Network:** one kind of request, to Zotero on the same computer (`http://127.0.0.1:23119`), to fetch a formatted citation. It succeeds only when Zotero's local API is switched on. Nothing else goes over the network, and the request bypasses any proxy settings.
- **No telemetry, no credentials, no shell commands, no background processes.** The plugin runs only when the agent calls a tool or you run `hermes zotero`.
- **Privacy:** the index holds the full text of your papers. It stays in the plugin's data folder; to remove it, delete that folder after uninstalling.

## Disk space and speed

The index needs about 180 KB per paper with full text, plus a copy of `zotero.sqlite`. Measured on an Apple-silicon MacBook Air with 19,290 papers: a first sync of about 70 seconds, a 3.5 GB index plus a 163 MB snapshot, a re-check of an unchanged library in under 2 seconds, and searches in under half a second.

## Limitations

- Search is lexical (BM25 with stemming), not semantic: it finds the words you search for, not their synonyms. The skill tells the agent to use scientific names rather than brand names.
- Papers whose PDFs have no text layer are searchable by title and abstract only, unless you supply Markdown for them.
- Annotations are read from the snapshot when asked for; they are not searchable.
- The plugin never changes your Zotero library: no tagging, filing or editing.

## Development

```bash
python -m pytest
```

The tests need only Python 3.11 or later and pytest; they build small Zotero libraries of their own and never touch yours. The plugin was built in reviewed steps: each task in [`tasks/`](tasks/) holds the spec, the acceptance tests and the executor's report, and [`AGENTS.md`](AGENTS.md) has the rules every step followed.

## License

MIT. See [LICENSE](LICENSE).
````

## Acceptance test (copy verbatim, then verify the checksums)

| File | SHA-256 | Who writes it |
| --- | --- | --- |
| `tests/test_10_release.py` | `7b3cf5700f5ad2c94b533627d9f82e3b1ec9dc6796c8e31eae5b9ef9e8e8d3cf` | you (below) |
| `README.md` | `4406c3364aab373517e3723c9c95b31b8fd3888c5b4134790862e0b1193a6bcf` | you (above) |
| `tests/test_09_skill_and_tags.py` | `0f7933df4ffcbe1f95baeea9fa6521634dfec47c4fecd018f7f359ae949f87d5` | the reviewer (on disk) |

The tests check that the README names every tool, command, setting and the skill; that its commands exist; that its settings table matches the real defaults; that the disclosures name every file read and the loopback call; that the nightly script parses and prints only on failure; that local links resolve; that `plugin.yaml` has the real homepage and an honest description; and that no file in the repo trips the two scanner rules that blocked task 09, contains a compiled binary or bytecode (catalog rule 17), or misses from `.gitignore`.

### `tests/test_10_release.py`

````python
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
````

## Commands

```bash
.venv/bin/python -m pytest                          # expect: 145 passed
shasum -a 256 tests/test_10_release.py README.md tests/test_09_skill_and_tags.py
```

Finish with `tasks/10-report.md` (paste the three checksums) and one commit: `task 10: README, disclosures, scanner-safe repo`. Do not push.

## Live check (Gábor, in the same or a new Claude Code session, after the commit)

Do the steps in order. Paste each step's output into the report under `## Live check`, then commit the report.

**1. Validate a clean copy, as the catalog CI does.** A fresh clone leaves out `review/` and other untracked files:

```bash
CLEAN="$(mktemp -d)/hermes-zotero"
git clone -q ~/Developer/hermes-zotero "$CLEAN" && hermes plugins validate "$CLEAN"
```

Expected: every line `✓`, including `security scan — safe` (not `caution`), then `Validation passed.` Leave out `--install-deps` here: the plugin has no dependencies, and on your machine that flag re-syncs Hermes' own Python environment. The reviewer ran it with `--install-deps` in a throwaway Hermes, and the catalog CI runs it too.

**2. Push.** `git push`. Then open https://github.com/gerdosi/hermes-zotero and check that the README shows properly.

**3. Fresh install, as a stranger would do it** (plan: "zero to first answer in under 15 min on a small library"). This uses a throwaway Hermes profile, so your own setup is not touched. Note the clock time at the start and at the end.

```bash
hermes profile create zfresh --clone          # copies config, keys and skills; not plugins or their data
hermes -p zfresh plugins install https://github.com/gerdosi/hermes-zotero
hermes -p zfresh plugins enable hermes-zotero
hermes -p zfresh config set plugins.entries.hermes-zotero.settings.libraries '["4805701"]'
hermes -p zfresh config set plugins.entries.hermes-zotero.settings.markdown_path ""
hermes -p zfresh config set skills.disabled '["local-literature", "zotero"]'
hermes -p zfresh zotero doctor
time hermes -p zfresh zotero sync
time hermes -p zfresh -z "Which papers in my Zotero library discuss insulin resistance? Cite two of them."
```

The settings make it a small library (only the Ancestralize group, 693 items), without your Markdown corpus and without your own Zotero skills, so it is close to what a stranger gets. Report: whether the install printed any scanner warning; the `doctor` output; the sync time and item count; the agent's tool calls (from this profile's `state.db`, under `~/.hermes/profiles/zfresh/`) and whether it loaded `hermes-zotero:zotero-library`; the answer's first lines; and the minutes from the first command to the answer. Expected: install without a block or warning prompt, sync of about 693 items in well under a minute, `zotero_search` then `zotero_read`, total well under 15 minutes. If `insulin resistance` has no hits in the group, any topic the group covers will do; say which.

Then remove the profile and its index: `hermes profile delete zfresh -y`.

**4. Nightly sync without the agent** (plan: "cron sync with 0 LLM calls"), in your normal profile. Save the script from the README's "Keeping the index up to date" section as `~/.hermes/scripts/zotero-sync.py`, exactly as printed there, then:

```bash
hermes cron create "17 4 * * *" --no-agent --script zotero-sync.py --name "Zotero index sync"
hermes cron run <the job id it printed>
hermes cron runs <the job id>
```

Expected: `Ran now: succeeded`, the run listed as completed, nothing delivered (the script is silent on success), and no model call for it in `~/.hermes/logs/agent.log`. Keep the job (it costs about 2 seconds a night) or remove it with `hermes cron remove <id>`; say which in the report.

## Out of scope

The catalog entry and its PR, the demo recording and the hackathon form come next. No code changes in this task.
