# Task 01 report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / low
## What changed
- plugin.yaml: manifest; requires_hermes set to >=0.23.0 (from `hermes --version`: v0.23.0+209...)
- pyproject.toml, LICENSE, README.md, .gitignore: as specified
- __init__.py: Hermes glue (register)
- zotcore/__init__.py, settings.py, jsonout.py, tools.py, cli.py: scaffold logic
- tests/conftest.py, tests/test_01_*.py: copied verbatim from the task
## Test output
```
.......................                                                  [100%]
23 passed in 0.03s
```
## Checksums
```
2f3c8090988e03d2ddc00ce0dcf6a255654688b1f5ed8d8b88ed861dbde30f23  tests/conftest.py
f073b1a55bcd9c7828b5911686c522241ad5cdb116e1982d7d372c9e8a2349f0  tests/test_01_manifest.py
6607ff97a3bbf1d03dafaa657610ca28efd92e6ecf1cd3b7fd83a5be62024f24  tests/test_01_register.py
00bd02767cea6f6d573d07b88d680d45f54ec30e82360d9db0cf2a708f63b6de  tests/test_01_settings.py
7eae6e382bc128cead30a07912c39963d5248707502564f5e8853a2877e29bfc  tests/test_01_tools.py
```
All five match the table in the task.
## Deviations from the task
- Resolved in task 01b: root __init__.py now guarded with "if __package__:"; 23 passed on pytest 9.2.0.
## Open questions
- none

## Live check
Run on the Mac; the in-chat "Call zotero_status" step was not run.

```
$ ln -s ~/Developer/hermes-zotero ~/.hermes/plugins/hermes-zotero
(exit 0, no output)

$ hermes plugins enable hermes-zotero
✓ Plugin hermes-zotero enabled.
Gateway reloaded plugins — deferred: tools (next session).

$ hermes plugins validate ~/Developer/hermes-zotero --install-deps
✓ manifest — plugin.yaml parses
✓ manifest fields — name, version, description present
✓ requires_hermes — spec '>=0.23.0' parses
✓ config schema — shape valid
✓ requires_env — all entries UPPER_SNAKE
✓ oauth — not declared
✓ loadable — entry: __init__.py
✓ python dependencies — none declared
✓ capability probe — register() ran in isolation
✓ declared tools — matches registrations
✓ declared hooks — matches registrations
✓ declared middleware — matches registrations
✓ built-in tool collisions — no collisions
✓ security scan — safe
✓ no core override — no runtime rebinds of Hermes core
◆ Isolation — runs in the plugin host (plugins.isolation: host)
  · ctx.register_cli_command() is skipped in the host (`hermes <command>`
subcommands are wired into the local CLI parser)

Validation passed.

$ hermes plugins doctor ~/Developer/hermes-zotero
Plugin Doctor: /Users/erdoke/Developer/hermes-zotero
  manifest: hermes-zotero 0.1.0 (standalone)
  OK: runtime discovery, manifest parsing, import, and registration passed
  registrations: 1 tool(s), 0 hook(s)

$ hermes zotero doctor
hermes-zotero 0.1.0
  zotero_data_dir: 
  markdown_path: 
  libraries: ['user']
  coverage_strong_min: 8
  coverage_recent_min: 2
  coverage_recent_years: 5
  sync_batch_items: 200
  sync_tool_budget_seconds: 30
  read_max_chars_default: 4000
  read_max_chars_cap: 12000
```

Notes: all four exited 0 with no failures or warnings. `plugins doctor` reports 1 tool and does not list the CLI command "zotero" (expected by the task), but `hermes zotero doctor` runs, so the CLI command is registered.
