# Task 08 report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / medium
## What changed
- zotcore/annotations.py: new; reads annotations and child notes from the current snapshot, with author rules, note_text and page_entries.
- zotcore/citation.py: new; Zotero local-API citation (no proxy, 2 s timeout) with approximate author-year fallback.
- zotcore/synctool.py: new; sync_lock (OS file lock) and the time-boxed sync_step.
- zotcore/index.py: SyncReport.read_errors; read-error summary line now also in the early budget return.
- zotcore/search.py: item_info added; read_item uses it, output unchanged.
- zotcore/tools.py: zotero_read gains mode, annotations_count, citation; new zotero_sync; tool_specs takes citation_api.
- zotcore/cli.py: sync and snapshot hold the sync lock; busy message and return code 1.
- __init__.py: passes citation_api=ZOTERO_LOCAL_API.
- plugin.yaml: provides_tools gains zotero_sync.
- tests/test_08_annotations_citation_sync.py: verbatim from the task.
- tasks/08-annotations-citation-sync.md, tasks/README.md, AGENTS.md: committed as supplied by the reviewer.
## Test output
```
........................................................................ [ 59%]
..................................................                       [100%]
122 passed in 3.32s
```
## Checksums
```
5d6940a227d2ba8ce33cf54efca3c8df3c125361adcf2ab77459024554c78d09  tests/test_08_annotations_citation_sync.py
```
## Deviations from the task
- none
## Open questions
- none (the live check in the task is left for Gábor; it was not run)

## Live check
Run 6 Nov 2026 (afternoon CET) on Gábor's real library and index, by Claude Sonnet 5.5 in Claude Code.

### 1. Direct check, Zotero closed
Result: **matches every row of the expected table.** Annotation counts, authors (group annotations show the member's Zotero user name `HegliK`, not `user`), `empty_omitted` values, paging (31 + 10), `annotations_count` and all three approximate citations are as expected; every read took ≤ 0.01 s. The only difference is in the sync steps: with the 1 s / 2 s budgets, step 1 examined 500 of 693 (not about 50) because a batch of 50 items takes only a few milliseconds on this Mac; the sync finished in 2 steps instead of several. Step 1 `reused=False`, step 2 `reused=True`, `done=True`, no warnings.

```
zotero_read {'key': 'Q3K5IWZH', 'mode': 'annotations'}  0.01s  4468 chars
{'mode': 'annotations', 'total_annotations': 19, 'empty_omitted': 0, 'next_offset': None}
on this page: 19 by author: {'user': 19}
first: [{"type": "highlight", "page": "719", "text": "Managing Obesity", "color": "#ff6666", "author": "user"}]
citation: {'text': 'Kotanidis et al. (2025). Managing Obesity. New England Journal of Medicine. https://doi.org/10.1056/nejmclde2413003', 'source': 'index', 'approximate': True}

zotero_read {'key': 'J2CWD6IV', 'mode': 'annotations'}  0.00s  7602 chars
{'mode': 'annotations', 'total_annotations': 41, 'empty_omitted': 7, 'next_offset': 31}
on this page: 31 by author: {'HegliK': 31}
first: [{"type": "highlight", "page": "53", "text": "Biomarkers of Morbid Obesity and Prediabetes by Metabolomic Profiling of Human Discordant Phenotypes", "color": "#ffd400", "author": "HegliK"}]
citation: {'text': 'Tulipani et al. (2016). Biomarkers of Morbid Obesity and Prediabetes by Metabolomic Profiling of Human Discordant Phenotypes. Clinica Chimica Acta. https://doi.org/10.1016/j.cca.2016.10.005', 'source': 'index', 'approximate': True}

zotero_read {'key': 'J2CWD6IV', 'mode': 'annotations', 'offset': 31}  0.00s  3120 chars
{'mode': 'annotations', 'total_annotations': 41, 'empty_omitted': 7, 'next_offset': None}
on this page: 10 by author: {'HegliK': 10}
first: [{"type": "highlight", "page": "57", "text": "might suppress the production of pro-inflammatory cytokines (i.e. TNF-α and IL-6), increase adiponectin secretion through the activation of PPAR-γ, and prevent insulin resistance and associated inflammatory diseases [32].", "color": "#ffd400", "author": 
citation: {'text': 'Tulipani et al. (2016). Biomarkers of Morbid Obesity and Prediabetes by Metabolomic Profiling of Human Discordant Phenotypes. Clinica Chimica Acta. https://doi.org/10.1016/j.cca.2016.10.005', 'source': 'index', 'approximate': True}

zotero_read {'key': 'GZ66NGZE', 'mode': 'annotations'}  0.00s  728 chars
{'mode': 'annotations', 'total_annotations': 0, 'empty_omitted': 11, 'next_offset': None}
on this page: 0 by author: {}
first: []
citation: {'text': 'Stenvers et al. (2019). Circadian clocks and insulin resistance. Nature Reviews. Endocrinology. https://doi.org/10.1038/s41574-018-0122-1', 'source': 'index', 'approximate': True}

zotero_read {'key': 'Q3K5IWZH', 'max_chars': 500}  0.00s  1164 chars
{'mode': 'text', 'annotations_count': 19, 'next_offset': 500}
citation: {'text': 'Kotanidis et al. (2025). Managing Obesity. New England Journal of Medicine. https://doi.org/10.1056/nejmclde2413003', 'source': 'index', 'approximate': True}

zotero_read {'key': 'RMRFLJX6', 'query': 'ferroptosis', 'max_chars': 500}  0.01s  1199 chars
{'mode': 'text', 'annotations_count': 0, 'next_offset': 25633}
citation: {'text': 'Bell et al. (2024). Ironing out the role of ferroptosis in immunity. Immunity. https://doi.org/10.1016/j.immuni.2024.03.019', 'source': 'index', 'approximate': True}
sync step 1: done=False examined=500/693 indexed=500 eta=0 reused=False 1.1s warnings=[]
sync step 2: done=True examined=693/693 indexed=193 eta=None reused=True 0.4s warnings=[]
```

### 2. Direct check, Zotero open, local API switched on
The local API answered 200 on `127.0.0.1:23119`. All six reads now return `"source": "zotero", "style": "apa", "approximate": false` with Zotero's own APA reference (e.g. Q3K5IWZH: "Kotanidis, C. P., Lincoff, A. M., & Shikora, S. A. (2025). Managing Obesity. New England Journal of Medicine, 393(7), 719–721. https://doi.org/10.1056/NEJMclde2413003"). Annotation results are identical to check 1; reads took ≤ 0.02 s. No `curl` diagnosis was needed.

```
zotero_read {'key': 'Q3K5IWZH', 'mode': 'annotations'}  0.02s  4537 chars
{'mode': 'annotations', 'total_annotations': 19, 'empty_omitted': 0, 'next_offset': None}
on this page: 19 by author: {'user': 19}
first: [{"type": "highlight", "page": "719", "text": "Managing Obesity", "color": "#ff6666", "author": "user"}]
citation: {'text': 'Kotanidis, C. P., Lincoff, A. M., & Shikora, S. A. (2025). Managing Obesity. New England Journal of Medicine, 393(7), 719–721. https://doi.org/10.1056/NEJMclde2413003', 'source': 'zotero', 'style': 'apa', 'approximate': False}

zotero_read {'key': 'J2CWD6IV', 'mode': 'annotations'}  0.02s  7806 chars
{'mode': 'annotations', 'total_annotations': 41, 'empty_omitted': 7, 'next_offset': 31}
on this page: 31 by author: {'HegliK': 31}
first: [{"type": "highlight", "page": "53", "text": "Biomarkers of Morbid Obesity and Prediabetes by Metabolomic Profiling of Human Discordant Phenotypes", "color": "#ffd400", "author": "HegliK"}]
citation: {'text': 'Tulipani, S., Palau-Rodriguez, M., Miñarro Alonso, A., Cardona, F., Marco-Ramell, A., Zonja, B., Lopez de Alda, M., Muñoz-Garach, A., Sanchez-Pla, A., Tinahones, F. J., & Andres-Lacueva, C. (2016). Biomarkers of Morbid Obesity and Prediabetes by Metabolomic Profiling of Human Discordant Phenotypes. Clinica Chimica Acta, 463, 53–61. https://doi.org/10.1016/j.cca.2016.10.005', 'source': 'zotero', 'style': 'apa', 'approximate': False}

zotero_read {'key': 'J2CWD6IV', 'mode': 'annotations', 'offset': 31}  0.01s  3324 chars
{'mode': 'annotations', 'total_annotations': 41, 'empty_omitted': 7, 'next_offset': None}
on this page: 10 by author: {'HegliK': 10}
first: [{"type": "highlight", "page": "57", "text": "might suppress the production of pro-inflammatory cytokines (i.e. TNF-α and IL-6), increase adiponectin secretion through the activation of PPAR-γ, and prevent insulin resistance and associated inflammatory diseases [32].", "color": "#ffd400", "author": 
citation: {'text': 'Tulipani, S., Palau-Rodriguez, M., Miñarro Alonso, A., Cardona, F., Marco-Ramell, A., Zonja, B., Lopez de Alda, M., Muñoz-Garach, A., Sanchez-Pla, A., Tinahones, F. J., & Andres-Lacueva, C. (2016). Biomarkers of Morbid Obesity and Prediabetes by Metabolomic Profiling of Human Discordant Phenotypes. Clinica Chimica Acta, 463, 53–61. https://doi.org/10.1016/j.cca.2016.10.005', 'source': 'zotero', 'style': 'apa', 'approximate': False}

zotero_read {'key': 'GZ66NGZE', 'mode': 'annotations'}  0.01s  829 chars
{'mode': 'annotations', 'total_annotations': 0, 'empty_omitted': 11, 'next_offset': None}
on this page: 0 by author: {}
first: []
citation: {'text': 'Stenvers, D. J., Scheer, F. A. J. L., Schrauwen, P., la Fleur, S. E., & Kalsbeek, A. (2019). Circadian clocks and insulin resistance. Nature Reviews. Endocrinology, 15(2), 75–89. https://doi.org/10.1038/s41574-018-0122-1', 'source': 'zotero', 'style': 'apa', 'approximate': False}

zotero_read {'key': 'Q3K5IWZH', 'max_chars': 500}  0.01s  1233 chars
{'mode': 'text', 'annotations_count': 19, 'next_offset': 500}
citation: {'text': 'Kotanidis, C. P., Lincoff, A. M., & Shikora, S. A. (2025). Managing Obesity. New England Journal of Medicine, 393(7), 719–721. https://doi.org/10.1056/NEJMclde2413003', 'source': 'zotero', 'style': 'apa', 'approximate': False}

zotero_read {'key': 'RMRFLJX6', 'query': 'ferroptosis', 'max_chars': 500}  0.02s  1262 chars
{'mode': 'text', 'annotations_count': 0, 'next_offset': 25633}
citation: {'text': 'Bell, H. N., Stockwell, B. R., & Zou, W. (2024). Ironing out the role of ferroptosis in immunity. Immunity, 57(5), 941–956. https://doi.org/10.1016/j.immuni.2024.03.019', 'source': 'zotero', 'style': 'apa', 'approximate': False}
```

### 3. Through Hermes
`hermes gateway restart` was run first (new gateway PID 20517). Tool calls are from `~/.hermes/state.db`, `tool … completed` lines from `~/.hermes/logs/agent.log`.

**Prompt 1 ("What did I highlight in the NEJM paper 'Managing Obesity'…") — the expected tool path was NOT taken.** The agent never called `zotero_search` or `zotero_read`. Its only plugin-related call was `tool_describe` for `zotero_search`, `zotero_read` and `zotero_status`. It then followed the user's existing `zotero` and `local-literature` skills: a `sqlite3` query on `~/Zotero-Markdown/index.sqlite`, `curl` calls to Zotero's local API, a copy of `zotero.sqlite` to `/tmp/zc_hl.sqlite` and a read of it, and a pypdf look at the PDF (10 `terminal`, 3 `skill_view`, 1 `read_file`). It still answered correctly (19 highlights with page numbers, citation Kotanidis et al.), in 2 min 18 s. No `zotero_*` line appears in `agent.log` for that session. Cause (hypothesis): the two older skills win over the plugin's tools; this is the skill and tool-description tuning in task 09.

**Prompt 2 ("Bring my Zotero index up to date.") — `zotero_sync` works as specified, but the agent also did other work.** Calls in order: `tool_describe` (`zotero_status`, `zotero_sync`), `zotero_status`, `zotero_sync {"budget_seconds": 60}`, then many `terminal` / `read_file` calls, and a second `zotero_sync {"budget_seconds": 60}`.

```
15:23:14 tool zotero_status completed (0.52s, 1096 chars)
15:23:39 tool zotero_sync completed (1.24s, 282 chars)
15:26:54 tool zotero_sync completed (1.55s, 282 chars)
```
- First `zotero_sync`: `done: true`, examined 19290 / 19290, indexed 0, 1.0 s, `snapshot.reused: false`, no warnings.
- Second `zotero_sync` (after the agent's own work below): `done: true`, indexed 14, 1.5 s, `snapshot.reused: true`, no warnings.
- Whole run took 4 min 22 s, not about 10 s, because of what the agent did next.

**Side effect to be aware of:** following the `local-literature` skill, the agent ran `~/.hermes/skills/research/local-literature/scripts/incremental_sync.py` for real (after a `--dry-run`) with `notify`/`background`, which wrote to `~/Zotero-Markdown`: 14 new papers converted and added to `~/Zotero-Markdown/index.sqlite` (now 18,328 rows), 3 Cell papers repaired from Zotero's text cache and the ingest manifest edited. This came from the skill, not from this plugin, and the plugin's own code only wrote to its own index. The prompt in this check is what triggered it; the plugin index also picked up the same 14 papers (19,290 items, nothing remaining).

### 4. Through Hermes after the skill update
`hermes gateway restart` was run first (launchd-supervised, new gateway PID 21743), then `hermes -z "What did I highlight in the NEJM paper 'Managing Obesity'? Give the citation too."`. Session `local-ff8859a3…` (oneshot, model grok-4.7). Tool calls are from `~/.hermes/state.db`, `tool … completed` lines from `~/.hermes/logs/agent.log`. No files were changed for this check apart from this report.

**This time the plugin path was taken.** Compared with prompt 1 in section 3, there was no `terminal`, `curl`, sqlite or PDF fallback: 5 tool calls, 4 model API calls.

Tool calls in order (`state.db`):
1. `tool_describe {"names":["zotero_search","zotero_read","zotero_status"]}`
2. `skill_view {"name":"local-literature"}`
3. `skill_view {"name":"research-answer-formatting"}`
4. `tool_call {"calls":[{"name":"zotero_search","arguments":{"query":"Managing Obesity NEJM","limit":10}}]}`
5. `tool_call {"calls":[{"name":"zotero_read","arguments":{"key":"Q3K5IWZH","mode":"annotations"}}]}`

`tool … completed` lines (`agent.log`):
```
15:56:15,573 tool tool_describe completed (0.02s, 2247 chars)
15:56:15,696 tool skill_view completed (0.15s, 22420 chars)
15:56:15,704 tool skill_view completed (0.16s, 25190 chars)
15:56:18,745 tool zotero_search completed (0.66s, 6783 chars)
15:56:20,718 tool zotero_read completed (0.07s, 4537 chars)
```
The two `zotero_*` calls took 0.73 s together. The `zotero_read` call used `mode: "annotations"` directly on key `Q3K5IWZH`, the same item as in section 1.

**Total time:** 65 s wall clock for `hermes -z` (exit 0), against 2 min 18 s for the same prompt in section 3. Nearly all of it is model time between tool calls.

**Answer (excerpt):** it reported 19 highlights, grouped by colour with page numbers, e.g. "Red (p. 719): Managing Obesity / Treatment Options / 1. Initiate therapy with semaglutide. 2. Recommend metabolic and bariatric surgery." then purple (framing), orange for the case and for the semaglutide and surgery arguments (pp. 720–721). Citation given: Kotanidis, Christos P., A. Michael Lincoff, and Scott A. Shikora. 2025. "Managing Obesity." New England Journal of Medicine 393(7): 719–721. https://doi.org/10.1056/NEJMclde2413003 (matches section 1).

Not checked here: whether each highlight's text and page in the answer matches the Zotero annotations one by one.

### Left as it is
Zotero is open with the local API switched on (Gábor's choice; the plugin works either way).
