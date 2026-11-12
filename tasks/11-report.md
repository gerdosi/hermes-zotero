# Task 11 report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / medium
## What changed
- zotcore/tables.py: new, verbatim from the task (table parsing, pipe rows, row-end cutting).
- tests/test_11_tables.py: new, verbatim from the task.
- skills/zotero-library/SKILL.md: replaced verbatim (0.2.0).
- zotcore/textsource.py: Passage kind/table; build_passages.
- zotcore/index.py: schema version 2, item_tables, reset on old layout.
- zotcore/search.py: index_outdated, in_tables, list_tables, read_table, tables_count.
- zotcore/tools.py: in_tables and table arguments, mode=tables, status hints.
- zotcore/cli.py: sync summary prints the table count.
- tests/test_08_annotations_citation_sync.py: the one allowed line (mode enum lists "tables").
## Test output
```
........................................................................ [ 39%]
........................................................................ [ 78%]
........................................                                 [100%]
184 passed in 3.35s
```
## Checksums
```
19502931b876655228a88723a39207f73af1af9f1461dc1f759bf3d94b888f63  tests/test_11_tables.py
```
Verbatim files, the patch and all six patched files matched the task's tables.
## Deviations from the task
- none
## Open questions
- none

## Live check

Run 12 Nov 2026 by the review session (Opus 5.5) after Gábor's full `hermes zotero sync` (index at schema 3, so this covers tasks 11 and 13 together). Code at 2525513, run read-only against ~/.hermes/plugin-data/hermes-zotero.

```
status: True | hint: None | schema 3 | items 19298 | passages 1060810 | tables 10369 | last_sync 2026-11-12T11:49:44Z
LDL cholesterol baseline | in_tables=False | all 888 | any 11486 | strong | table passages 3/9 | 0.63 s
LDL cholesterol baseline | in_tables=True | all 70 | any 1082 | strong | table passages 8/8 | 0.37 s
HbA1c | in_tables=False | all 2102 | any 2102 | strong | table passages 2/9 | 0.39 s
HbA1c | in_tables=True | all 360 | any 360 | strong | table passages 8/8 | 0.19 s
visceral adipose tissue women men | in_tables=False | all 727 | any 17367 | strong | table passages 0/9 | 0.58 s
visceral adipose tissue women men | in_tables=True | all 11 | any 1137 | thin | table passages 9/9 | 0.42 s
hazard ratio | in_tables=False | all 805 | any 11551 | strong | table passages 6/10 | 0.48 s
hazard ratio | in_tables=True | all 41 | any 547 | strong | table passages 9/9 | 0.35 s
td tr | in_tables=False | all 84 | any 3954 | strong | table passages 0/7 | 0.20 s
td tr | in_tables=True | all 0 | any 29 | none | table passages 8/8 | 0.19 s
first hit: C79A2UFR | The Effect of a Ketogenic Diet versus Mediterranean Diet on Clinical a | table 3
tables in it: 3 [{'table': 1, 'caption': None, 'rows': 14, 'cols': 9, 'chars': 30276}, {'table': 2, 'caption': None, 'rows': 4, 'cols': 8, 'chars': 484}, {'table': 3, 'caption': None, 'rows': 9, 'cols': 9, 'chars': 7601}]
next_offset: 108471 | warnings: [] | citation: Lambadiari et al. (2024). The Effect of a Ketogenic Diet versus Mediterranean Di
### Table 3
| Int. J. Mol. Sci. 2024, 25, 2475 | Int. J. Mol. Sci. 2024, 25, 2475 | Int. J. Mol. Sci. 2024, 25, 2475 | 4 of 12 Data are presented as mean ± SD. Δ% indicates percentage change from baseline.MD: Mediterra- | 4 of 12 Data are presented as mean ± SD. Δ% indicates percentage change from baseline.MD: Mediterra- | 4 of 12 Data are presented as mean ± SD. Δ% indicates percentage change from baseline.MD: Mediterra- | 4 of 12 Data are presented as mean ± SD. Δ% indicates percentage change from baseline.MD: Mediterra- | 4 of 12 Data are presented as mean ± SD. Δ% indicates percentage change from baseline.MD: Mediterra- | 4 of 12 Data are presented as mean ± SD. Δ% indicates percentage change from baseline.MD: Mediterra- |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 14.01 ± 7.84 | -25.94 | 0.283 | nean diet; KD: Ketogenic diet; BMI: Body mass index; WC: Waist circumference; Glu: Glucose; TGs: Triglycerides; TChol: Total cholesterol; HDL: High-density lipoprotein cholesterol; LDL: Low-den- 0.032 0.905 | nean diet; KD: Ketogenic diet; BMI: Body mass index; WC: Waist circumference; Glu: Glucose; TGs: Triglycerides; TChol: Total cholesterol; HDL: High-density lipoprot
```

Verdict: all expectations met (schema 3, 19,298 items, 1,060,810 passages, 10,369 tables; in_tables returns only table passages; `td tr` no longer matches markup; every search under 0.7 s; table read is pipe rows with a citation). Note: in the first hit (C79A2UFR, table 3) the converter put the journal's page header and a footnote into the header cells; the plugin reproduces them as given. That is corpus quality, not a plugin bug.

Part 2 (through Hermes): see below.
