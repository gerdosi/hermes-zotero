# Task 15 report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / low
## What changed
- tests/test_15_symbols.py: added verbatim from the task (7 tests).
- zotcore/textquality.py: new `symbols` damage kind, checked before the 500-word minimum.
- zotcore/index.py: SCHEMA_VERSION 3 to 4.
- zotcore/__init__.py, plugin.yaml, pyproject.toml, skills/zotero-library/SKILL.md: version 0.2.1.
- docs/CORPUS.md: `text_damaged` row names the new kind.
- tests/test_11_tables.py, tests/test_13_text_damage.py, tests/test_14_release.py: the reviewer's one-line changes, applied as given.
## Test output
```
........................................................................ [ 30%]
........................................................................ [ 61%]
........................................................................ [ 91%]
....................                                                     [100%]
236 passed in 3.42s
```
## Checksums
```
92de3a30f7528046d02798bce64f81fc77e71da281b076910f7911a77078c180  tests/test_15_symbols.py
```
Patch (d9a1bf23...) and all post-patch file checksums matched the task table.
## Deviations from the task
- none (the system python3 is too old for `newline=` in write_text, so the extraction script was run with `.venv/bin/python`; output identical)
## Open questions
- none
