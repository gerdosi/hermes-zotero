# Task 03b report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / low
## What changed
- zotcore/snapshot.py: added `_wal_header`; consistency rule now also requires the WAL header to be identical before, after and in the copy (WAL restart rewrites it).
- tests/test_03b_wal_restart.py: added verbatim from the task.
- tasks/03b-report.md: this report.
## Test output
```
....................................................                     [100%]
52 passed in 0.12s
```
## Checksums
```
ac7cbd1205c3a4a505f236e69a0cac5c13e88b5227b7e4cdf36eeeb768ba5426  tests/test_03b_wal_restart.py
```
## Deviations from the task
- none
## Open questions
- none
