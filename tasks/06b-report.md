# Task 06b report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / low
## What changed
- zotcore/index.py: an `OSError` from `choose_text` now indexes the item's title and abstract (flags `body_not_read`, `read_error`, unchanged signature) and adds a warning, capped at `MAX_ITEM_WARNINGS = 20` with a summary line. The batch no longer rolls back.
- tests/test_06b_read_errors.py: copied verbatim from the task file.
- Also committed as instructed: AGENTS.md, tasks/README.md, tasks/04-read-items.md, tasks/05-text-and-passages.md, tasks/06-index-and-sync.md, tasks/06b-read-errors.md.
## Test output
```
........................................................................ [ 82%]
...............                                                          [100%]
87 passed in 0.85s
```
## Checksums
```
136ca8f3f184ba47828d361a8af55b890ce59448acc1f1ea589ecca052f31655  tests/test_06b_read_errors.py
```
## Deviations from the task
- `.claude/settings.json` is listed to be committed but does not exist in the repo, so it was not committed.
## Open questions
- none
