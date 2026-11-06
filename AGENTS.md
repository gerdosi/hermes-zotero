# AGENTS.md — hermes-zotero

Hermes loads this file automatically. It applies to every task in `tasks/`.

## What this project is

`hermes-zotero` is a Hermes Agent plugin that builds a **read-only, local index** of the user's Zotero library and exposes a few search/read tools. No network, no writes to Zotero, no third-party Python packages.

## Layout

```
plugin.yaml          Hermes manifest
pyproject.toml       version, pytest config (no dependencies)
__init__.py          Hermes glue ONLY: register(ctx). The only file that may import Hermes modules, and only inside functions.
zotcore/             all logic; pure standard-library Python >= 3.11; no Hermes imports
tests/               pytest; test_NN_*.py are acceptance tests from tasks/NN-*.md
tasks/               task files (instructions) and NN-report.md (your reports)
```

## Hard rules

1. **Never modify the Zotero data directory.** Do not open `zotero.sqlite` there with sqlite3, do not create files there, do not lock it. Reading file bytes (copying) is the only allowed access.
2. **`zotcore/` stays standard-library only** and never imports Hermes (`plugins.*`, `hermes_cli.*`, `tools.*`). Hermes things are passed in from `__init__.py` as callables.
3. **Tool handlers** have the signature `handler(args: dict | None, **kwargs) -> str`, return a JSON string, and never raise. Wrap them with `zotcore.jsonout.safe`.
4. **Acceptance tests are read-only.** Copy `tests/test_NN_*.py` (and, in task 01, `tests/conftest.py`) from the task file byte-for-byte, then check the SHA-256 listed in the task. Never edit, delete, skip, `xfail` or weaken them, and add no pytest hooks or plugins that change their behaviour. `tests/conftest.py` may only gain new fixtures. If you think a test is wrong, stop and explain why in the report.
5. **Touch only the files listed** under "Files" in the task.
6. **No network access** in code or tests.
7. Before finishing, run `python -m pytest`. **All** tests, old and new, must pass.
8. **Stop rule:** if the same failure survives two fix attempts, stop and write the report with status `BLOCKED`. Include the failing output and your best hypothesis.
9. **Finish** by writing `tasks/NN-report.md` (template below) and making one commit: `task NN: <title>`.

## Report template (`tasks/NN-report.md`)

```markdown
# Task NN report
Status: DONE | BLOCKED
Model / reasoning: <model id> / <low|medium|high|max>
## What changed
- <file>: <one line>
## Test output
<paste the last 15 lines of `python -m pytest`>
## Checksums
<paste `shasum -a 256 tests/test_NN_*.py` (and tests/conftest.py in task 01)>
## Deviations from the task
- none | <what and why>
## Open questions
- none | <question>
```

## Style

Type hints on public functions; short docstrings; no `print` outside `zotcore/cli.py`; UTF-8 everywhere (`encoding="utf-8"` on every text read or write).
