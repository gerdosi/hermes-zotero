# Task 07 report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / not shown to me (task asks for medium)
## What changed
- zotcore/search.py: new; read-only index access, query terms, scope filters, hits, coverage, DOI check, best_offset, read_window, read_item.
- zotcore/tools.py: added zotero_search and zotero_read (argument parsing, size cap); zotero_status unchanged.
- plugin.yaml: provides_tools gains zotero_search and zotero_read.
- tests/test_07_search_read.py: copied verbatim from the task.
## Test output
```
........................................................................ [ 67%]
..................................                                       [100%]
106 passed in 0.92s
```
## Checksums
```
fc19bc066caf1128cd1e83fab7917406d3d61cb08e8a862b480fd47073a541f2  tests/test_07_search_read.py
```
## Deviations from the task
- none (the "any" pass is skipped for a single term, where it would repeat the "all" pass)
## Open questions
- none

## Live check
Step 1 (direct, real index: libraries user + 4805701). All values match the expected table; every call took 1.4 s or less (the 1.40 s one is the N4AKAC5N read at a query match).

| Call | Result | Time |
| --- | --- | --- |
| `ferroptosis` | matches_all 200, recent 134, newest 2026, strong; top RMRFLJX6, ZIYQHNNR, 8EA5FWG5 | 0.02 s |
| `glucagon … zebrafish` | matches_all 0 (matches_any 17458), none, hint present; top FN5SJ8UL, R25SXVJA, RG7EKS42 | 0.23 s |
| `glucagon receptor antagonist` | matches_all 444, recent 67, strong; top FE52PFQC, GPGPTMCE, I5VK696F | 0.04 s |
| `brown adipose tissue thermogenesis`, collection Obesity | matches_all 50, recent 23, strong; top JHMERHPJ | 0.09 s |
| `ketogenic diet`, library 4805701 | matches_all 42, recent 10, newest 2022, strong | 0.03 s |
| `insulin resistance`, limit 25 | 11,504 chars (under 12,000), hits_dropped_for_size 4; matches_all 10469, strong | 0.17 s |
| doi `10.1016/j.immuni.2024.03.019` | held true, RMRFLJX6 | 0.00 s |
| doi `10.1002/alz.12362` | held true, ZFFUB9WK and RB659BDL | 0.00 s |
| doi `10.1234/not.held.2026` + `ferroptosis` | held false; coverage strong (200 / 134) | 0.01 s |
| read RMRFLJX6, query | offset 17933, next 21933, total 109797 | 0.01 s |
| read N4AKAC5N, query | offset 18472198, section "Assessment of Vitamin K Status", total 20125419 | 1.40 s |
| read N4AKAC5N, offset 10,000,000 | next_offset 10004000, total_chars 20125419 | 0.01 s |

Step 2 (through Hermes: `hermes gateway restart`, then the ferroptosis prompt): not run here; it needs the gateway restart and a Hermes session.
