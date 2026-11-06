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

## Live check
Command: `hermes zotero doctor`

```
hermes-zotero 0.1.0
  zotero_data_dir: 
  markdown_path: 
  libraries: ['user']
  coverage_strong_min: 8
  coverage_recent_min: 2
  coverage_recent_years: 5
  sync_batch_items: 200
  sync_tool_budget_seconds: 30
  read_max_chars_default: 4000
  read_max_chars_cap: 12000
Zotero data directory:
  /Users/erdoke/Zotero (source: prefs:/Users/erdoke/Library/Application Support/Zotero/Profiles/duqsnxd7.default)
  [ok] prefs:/Users/erdoke/Library/Application Support/Zotero/Profiles/duqsnxd7.default: /Users/erdoke/Zotero (ok)
  [ok] default: /Users/erdoke/Zotero (ok)
```

Where to compare: in Zotero, open Zotero > Settings (Cmd+,) > Advanced > Files and Folders, and read "Data Directory Location". It should show `/Users/erdoke/Zotero`. The comparison itself is for Gábor to do; it was not done here.
