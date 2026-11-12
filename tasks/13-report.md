# Task 13 report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / low
## What changed
- zotcore/textquality.py: new detector `damage(text)` (verbatim from task)
- tests/test_13_text_damage.py: new acceptance tests (verbatim)
- skills/zotero-library/SKILL.md: replaced with the reviewer's version (adds `text_damaged` bullet)
- zotcore/textsource.py: `choose_text` adds `text_damaged` flag for Markdown and Zotero text cache (patch)
- zotcore/index.py: SCHEMA_VERSION 2 -> 3 (patch)
## Test output
```
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 96%]
........                                                                 [100%]
224 passed in 3.87s
```
## Checksums
9b6e3aa2fc742d69a4a380a4f6908b91e6b8daafe2e48fac1e20be1aebb81f13  tests/test_13_text_damage.py
## Deviations from the task
- none (the task's script was run with .venv/bin/python because the system python3 is too old for `newline=` in `write_text`)
## Open questions
- none
