# Task 02 report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / low
## What changed
- zotcore/datadir.py: new; parse_prefs, profile_roots, check_data_dir, resolve_data_dir.
- tests/test_02_datadir.py: verbatim acceptance tests.
- zotcore/tools.py: zotero_status gains a data_dir block.
- zotcore/cli.py: doctor prints the data directory, candidates and a hint.
## Test output
```
.....................................                                    [100%]
37 passed in 0.05s
```
## Checksums
c2fc38ac192dcb590bbd8aedf0c622c4a9469bd6445d7728110236e79d9798e2  tests/test_02_datadir.py
## Deviations from the task
- none. The live check (`hermes zotero doctor` vs Zotero settings) was not run.
## Open questions
- none
