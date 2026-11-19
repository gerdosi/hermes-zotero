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

## Live check
Run by Gábor on the Mac, 19 Nov 2026; checked by the review session.
```
warning: the index was built by another plugin version and is being rebuilt from scratch
Sync: indexed 19308, deleted 0, examined 19308 in 174.0s
Index: 19308 items, 1078175 passages, 10731 tables; text sources {'ft-cache': 438, 'markdown': 18437, 'metadata': 433}; flags {'text_damaged': 429, 'body_not_read': 433, 'ocr': 358, 'scanned_or_empty': 86}
hermes zotero sync  127.55s user 19.94s system 83% cpu 2:56.09 total
schema 4 | items 19308 | flags {'text_damaged': 429, 'body_not_read': 433, 'ocr': 358, 'scanned_or_empty': 86}
10.1194/jlr.ra119000423 | held: True | flags: [['text_damaged']]
10.1161/01.atv.15.3.320 | held: True | flags: [['ocr', 'text_damaged']]
10.1007/s001250051540 | held: True | flags: [[]]
10.1016/j.cmet.2019.05.003 | held: True | flags: [[]]
```
- Schema 4, `ocr` 358 and the four DOIs as expected.
- `text_damaged` 429 (estimate was about 432). The review session re-scanned all 18,408 corpus files with this commit: 416 are flagged, and the plugin flags exactly those it indexes (412 user files, plus 1 group copy and 16 ft-cache texts = 429). The other 4 are `K:` files that are not plugin items (2 standalone attachments, 2 deleted items), one of them a symbols file (KBP8VDGN). The estimate also took 433 as the starting point, while 79 corpus files had changed since the previous sync (table merges).
