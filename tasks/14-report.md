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

## Live check

Run by Gábor on 12 Nov 2026; recorded by the review session (Opus 5.5).

1. Clean clone validated on macOS: all checks passed, `security scan — safe`, `Validation passed.` Pushed: `159886063c9e51e6ae09d76c4ef58d007d0c6fd7`. The review session also validated a fresh GitHub clone of that commit in the container (`--install-deps`, hermes-agent main 67664e23): safe. Catalog entry for 0.2.0 passes `scripts/validate_plugin_catalog.py` and the catalog CI tests.
2. `zdemo` profile (user library only, no Markdown folder): `hermes -p zdemo plugins update hermes-zotero` fast-forwarded f25a01e..1598860; `doctor` reports 0.2.0. `time hermes -p zdemo zotero sync`: one "rebuilt from scratch" warning; indexed 18,605 items in 126.3 s (2:07 total); 730,835 passages, 0 tables (no Markdown corpus, as expected); flags: body_not_read 282, text_damaged 76, truncated 72, scanned_or_empty 14.
3. `hermes -p zdemo -z "...ketogenic diets and insulin resistance..."`: answered from the library with Newman & Verdin (2014), Trends Endocrinol Metab, doi 10.1016/j.tem.2013.09.002, one quoted sentence, and a second on-topic paper (Yuan et al. 2020, doi 10.1038/s41387-020-00142-z).

Open: the 76 `text_damaged` papers in zdemo come from Zotero's ft-cache text; the detector was calibrated on the Markdown corpus only. Sample them in a later review.
