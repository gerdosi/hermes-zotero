# Task 14 report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / low
## What changed
- docs/CORPUS.md: corpus guide, verbatim from the task
- tests/test_14_release.py: acceptance tests, verbatim from the task
- README.md: new search and read options, new flags, index rebuild note, guide link
- plugin.yaml, pyproject.toml, zotcore/__init__.py: version 0.2.0
## Test output
```
........................................................................ [ 94%]
.............                                                            [100%]
229 passed in 3.36s
```
## Checksums
5e31461d97268152ff8ff25e84de356b543581f4d53ffdaf9cba9f25da74b837  tests/test_14_release.py
All checksums in the task table matched (guide, tests, patch, and the four patched files).
## Deviations from the task
- The extraction snippet's `write_text(..., newline=...)` failed on the system python3 (older than 3.10), so I wrote the same bytes with `write_bytes`. Checksums match.
## Open questions
- none
