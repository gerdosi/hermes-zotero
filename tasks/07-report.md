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
