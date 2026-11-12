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

## Live check

Run 12 Nov 2026 by the review session (Opus 5.5) after Gábor's full `hermes zotero sync` (index at schema 3, so this covers tasks 11 and 13 together). Code at 2525513, run read-only against ~/.hermes/plugin-data/hermes-zotero.

```
schema 3 | items 19298 | flags {'text_damaged': 426, 'body_not_read': 471, 'scanned_or_empty': 87}
10.1001/jamanetworkopen.2021.14741 | held: True | flags: [['text_damaged']]
10.5772/intechopen.76375 | held: True | flags: [['text_damaged']]
10.1194/jlr.tr119000391 | held: True | flags: [['text_damaged']]
10.1016/j.cmet.2019.05.003 | held: True | flags: [[]]
```

Verdict: as expected. `text_damaged` 426 (calibration predicted about 412 from the Markdown corpus; the extra 14 are probably group-library copies or papers read from the text cache; not checked). The three damaged DOIs are flagged; the clean DNA-sequence paper is not.
