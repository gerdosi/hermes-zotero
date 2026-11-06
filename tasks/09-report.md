# Task 09 report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / low
## What changed
- skills/zotero-library/SKILL.md: bundled skill, copied verbatim from the task
- zotcore/skill.py: SKILL_NAME, SKILL_DESCRIPTION, skill_path()
- __init__.py: registers the skill via ctx.register_skill when available and the file exists
- zotcore/search.py: `tag` filter (whole tag, case-insensitive) in _build_scope and search
- zotcore/tools.py: new tool descriptions, `tag` argument, zotero_status reports `ready` and `hint` (no `stage`)
- tests/test_09_skill_and_tags.py: acceptance tests, copied verbatim
- tasks/09-skill-tags-descriptions.md, tasks/README.md, AGENTS.md: committed as added or updated by the reviewer
## Test output
```
........................................................................ [ 54%]
.............................................................            [100%]
133 passed in 3.30s
```
## Checksums
```
af68739225d3c42a0d25f6c11e38d88898cda0b921a30cc17f08bfe403a836b8  tests/test_09_skill_and_tags.py
b4bfdc9a601643fa36a91c31ba0d5a07ea9a9bcc4b5102f9bd6b5f18faaee723  skills/zotero-library/SKILL.md
```
## Deviations from the task
- The untracked `review/` folder was not committed (not listed in the task). Live check part 1 was run afterwards (see below); parts 2 and 3 were not.
## Open questions
- none

## Live check
Run on the real index (19,290 items) after the commit, Zotero state as found. All values match the task's expected table; every search took under 0.2 s.

```
{'query': 'ferroptosis', 'tag': 'Review'} 0.04s hits=10 all=24 recent=1 verdict=thin first=SV9N8VKT warnings=[]
{'query': 'ferroptosis', 'tag': 'REVIEW'} 0.03s hits=10 all=24 recent=1 verdict=thin first=SV9N8VKT warnings=[]
{'query': 'insulin resistance', 'tag': 'Obesity'} 0.19s hits=10 all=527 recent=219 verdict=strong first=XGRB6QRX warnings=[]
{'query': 'insulin resistance', 'tag': 'obesity', 'library': 'user', 'year_from': 2020} 0.13s hits=10 all=288 recent=215 verdict=strong first=AHESV4J8 warnings=[]
{'query': 'microbiota', 'tag': 'Important'} 0.08s hits=10 all=64 recent=0 verdict=thin first=XIV26IVT warnings=[]
{'query': 'ketone', 'tag': 'Favorite'} 0.03s hits=9 all=9 recent=0 verdict=thin first=AG84CCAU warnings=[]
{'query': 'ferroptosis', 'tag': 'NoSuchTagAnywhere'} 0.02s hits=0 all=0 recent=0 verdict=none first=None warnings=['no indexed items match the filters']
status: ready = True | hint = Zotero has changed since the last sync: call zotero_sync to add the changes. | items = 19290 | has stage: False
zotero_status: 77 chars: Zotero index status: whether the local library index is ready and up to date.
zotero_search: 79 chars: Zotero library search: find papers the user already owns, before using the web.
zotero_read: 76 chars: Zotero paper reader: read part of one paper, or the user's highlights on it.
zotero_sync: 79 chars: Zotero index update: add new and changed papers from Zotero to the local index.
skill: 3129 bytes
```

Status hint is the "Zotero has changed since the last sync" variant: Zotero wrote to its database since the last sync (allowed by the table).

### Calibration (to be marked by Gábor)
| Query | all | any | recent | verdict | agree / disagree |
| --- | --- | --- | --- | --- | --- |
| ferroptosis adipocytes | 27 | 6580 | 17 | strong || agree |
| time-restricted eating | 323 | 17421 | 90 | strong || agree |
| SCD1 ferroptosis | 7 | 649 | 7 | thin || agree |
| menaquinone | 88 | 88 | 16 | strong || agree |
| ketogenic diet epilepsy | 201 | 12855 | 43 | strong || agree |
| brown adipose cold exposure | 624 | 15988 | 115 | strong || agree |
| trimethylamine atherosclerosis | 249 | 6023 | 49 | strong || agree |
| tirzepatide | 111 | 111 | 87 | strong || agree |
| retatrutide | 12 | 12 | 12 | strong || agree |
| intermittent fasting autophagy | 73 | 12712 | 26 | strong || agree |
| fructose hepatic lipogenesis | 376 | 10339 | 53 | strong || agree |
| NAD precursors aging | 87 | 16570 | 24 | strong || agree |
| sarcopenic obesity resistance training | 17 | 16288 | 8 | strong || agree |
| ultra-processed food | 203 | 16602 | 84 | strong || agree |
| Akkermansia muciniphila | 793 | 996 | 238 | strong || agree |
| creatine supplementation | 107 | 9617 | 23 | strong || agree |
| semaglutide alcohol use disorder | 5 | 18534 | 5 | thin || agree |
| PCSK9 base editing | 5 | 16536 | 5 | thin || agree |
| circadian clock liver | 315 | 12813 | 68 | strong || agree |
| mounjaro | 2 | 2 | 2 | thin || agree |

Disagreements: none. Gábor agrees with all 20 verdicts (6 Nov), so the default thresholds stay (strong = at least 8 papers with every word in one passage, at least 2 of them from the last 5 years).

### Part 2 — through Hermes, own skills enabled
`hermes gateway restart`, then `hermes -z "Which papers tagged Review in my Zotero library discuss ferroptosis? List three with their citations."` Wall time 108.8 s (session span 102.1 s). Tool calls (arguments from `state.db`; Hermes wraps plugin tools in `tool_call` / `tool_describe`; offsets in seconds from the first message):
```
+ 6.4s skill_view      hermes-zotero:zotero-library
+ 6.4s tool_describe   zotero_search, zotero_read, zotero_status
+ 9.7s zotero_search   {"query": "ferroptosis review", "tag": "Review", "limit": 10}
+ 9.7s zotero_status   {}
+16.5s tool_describe   zotero_sync
+18.6s zotero_sync     {"budget_seconds": 30}
+21.8s zotero_search   {"query": "ferroptosis", "tag": "Review", "limit": 15}
+41.6s zotero_read x5  SV9N8VKT, KAB4JSFW, UI9F3KCF (query "ferroptosis"), JDRW8JDD ("ferroptosis GPX4"), D7QN72EX; max_chars 1800-2000
+41.6s zotero_search   {"query": "ferroptosis GPX4 lipid peroxidation", "tag": "Review", "limit": 25}
+50.3s zotero_read x3  Q5RZKA3P, 7W63U8VQ, 3RQXVPPG (query "ferroptosis" / "ferroptosis GPX4")
+72.8s zotero_read     {"key": "Q5RZKA3P", "max_chars": 1200, "offset": 55500}
+75.2s zotero_read     {"key": "Q5RZKA3P", "max_chars": 900, "offset": 56700}
```
The agent loaded the plugin skill first, searched with `tag` = `Review` (the first call), then read. No web, terminal, sqlite or curl call. Note: it called `zotero_sync` after `zotero_status` returned the "Zotero has changed" hint (1.24 s), so the index was updated during this run. Log lines (`~/.hermes/logs/agent.log`, local time = UTC+1):
```
17:26:35,023 tool tool_describe completed (0.03s, 2437 chars)
17:26:35,048 tool skill_view completed (0.06s, 3527 chars)
17:26:39,651 tool zotero_search completed (1.31s, 7334 chars)
17:26:39,716 tool zotero_status completed (0.06s, 1178 chars)
17:26:45,021 tool tool_describe completed (0.01s, 528 chars)
17:26:48,449 tool zotero_sync completed (1.24s, 282 chars)
17:26:50,432 tool zotero_search completed (0.06s, 8067 chars)
17:27:10,386 tool zotero_read completed (0.24s, 2804 chars)
17:27:10,416 tool zotero_read completed (0.02s, 2815 chars)
17:27:10,437 tool zotero_read completed (0.02s, 2785 chars)
17:27:10,464 tool zotero_read completed (0.02s, 2673 chars)
17:27:10,486 tool zotero_read completed (0.02s, 2528 chars)
17:27:10,925 tool zotero_search completed (0.43s, 11660 chars)
17:27:18,889 tool zotero_read completed (0.03s, 2387 chars)
17:27:18,928 tool zotero_read completed (0.03s, 2476 chars)
17:27:18,951 tool zotero_read completed (0.02s, 2179 chars)
17:27:41,729 tool zotero_read completed (0.42s, 1978 chars)
17:27:43,748 tool zotero_read completed (0.03s, 1682 chars)
```

### Part 3 — as a stranger (`local-literature` and `zotero` switched off)
Backup `config.yaml.task09-backup`; added `disabled: [local-literature, zotero]` under `skills:` (diff: three added lines, nothing else); `hermes gateway restart`; `hermes skills list` showed both as `disabled` (the other Zotero-related skills `zotero-doi-reco…` and `literature-stre…` stay enabled, as the task only names two). Three separate `hermes -z` calls, each a fresh session.

**Prompt 1: SCD1 and ferroptosis.** Wall 394 s (span 388.6 s).
```
+ 9.5s skill_view x4   research-answer-formatting, hermes-zotero:zotero-library, scholar-broad-literature-search, grounded-citations
+13.2s tool_describe   zotero_search, zotero_read, zotero_status
+14.8s zotero_status   {}
+14.8s zotero_search   {"query": "SCD1 ferroptosis", "limit": 15}      -> coverage thin, 7 papers (all 7, recent 7)
+27.7s zotero_read x4  Q3Y95CGB (3500), ZIYQHNNR, 6DHUHZR3, TK94ZKBR (3000), query "SCD1 ferroptosis [MUFA]"
+27.7s zotero_search   {"query": "stearoyl desaturase ferroptosis", "limit": 10}   -> thin, 6
+27.7s zotero_search x3 doi = 10.1158/0008-5472.CAN-19-0369, 10.1016/j.chembiol.2018.11.016, 10.1073/pnas.2017152117
+45.5s zotero_read x3  6DHUHZR3 (offset 49000), WFJCQQAI, Q3Y95CGB (offset 44000)
+45.5s execute_code    Python urllib: Europe PMC / Crossref / OpenAlex (first web call, after 8 zotero calls)
+50.7s zotero_read     6DHUHZR3 "Magtanong exogenous monounsaturated"
+50.7s zotero_search   {"query": "Wohlhieter SCD1 KEAP1 ferroptosis", "limit": 8}   -> thin, 2
+50.7s execute_code, then 6 more execute_code calls (75 s ... 261 s): DOI / title lookups at api.crossref.org, api.openalex.org, www.ebi.ac.uk
```
Skill loaded: yes, the plugin skill was the second `skill_view`, before any Zotero tool call; three other, non-Zotero skills were loaded too. First `zotero_search` came before any web call. No sqlite/curl/terminal; no access to `zotero.sqlite` or either `index.sqlite` (checked by searching all tool-call arguments for `sqlite`, `curl`, `terminal`, `Zotero-Markdown`). The agent read 7 papers, then used the web for eight `execute_code` rounds (about 5 minutes) to verify and extend the list; the answer cites 17 papers. Log lines:
```
17:28:53,545 tool skill_view completed (0.14s, 3527 chars)
17:28:53,582 tool skill_view completed (0.18s, 22420 chars)
17:28:53,585 tool skill_view completed (0.18s, 14076 chars)
17:28:53,605 tool skill_view completed (0.20s, 16659 chars)
17:28:57,094 tool tool_describe completed (0.02s, 2437 chars)
17:28:58,975 tool zotero_status completed (0.21s, 1105 chars)
17:28:59,106 tool zotero_search completed (0.12s, 8239 chars)
17:29:11,879 tool zotero_read completed (0.24s, 4365 chars)
17:29:11,912 tool zotero_read completed (0.03s, 3710 chars)
17:29:11,939 tool zotero_read completed (0.02s, 3772 chars)
17:29:11,969 tool zotero_read completed (0.03s, 3892 chars)
17:29:12,064 tool zotero_search completed (0.09s, 7716 chars)
17:29:12,081 tool zotero_search completed (0.00s, 212 chars)
17:29:12,092 tool zotero_search completed (0.00s, 213 chars)
17:29:12,098 tool zotero_search completed (0.00s, 206 chars)
17:29:29,615 tool zotero_read completed (0.20s, 4865 chars)
17:29:29,679 tool zotero_read completed (0.05s, 5107 chars)
17:29:29,698 tool zotero_read completed (0.02s, 3927 chars)
17:29:36,090 tool execute_code completed (1.49s, 11921 chars)
17:29:36,160 tool zotero_read completed (0.05s, 3293 chars)
17:29:36,239 tool zotero_search completed (0.07s, 5930 chars)
17:30:01,157 tool execute_code completed (2.19s, 4334 chars)
17:30:11,814 tool execute_code completed (2.88s, 23587 chars)
17:31:13,256 tool execute_code completed (13.04s, 8432 chars)
17:31:58,552 tool execute_code completed (2.63s, 9005 chars)
17:32:11,838 tool execute_code completed (2.42s, 5980 chars)
17:33:10,679 tool execute_code completed (5.82s, 3497 chars)
```

**Prompt 2: retatrutide phase 3.** Wall 91 s (span 89.4 s).
```
+ 3.7s tool_describe   zotero_search, zotero_status, zotero_read
+ 3.7s skill_view      hermes-zotero:zotero-library
+ 6.0s zotero_search   {"query": "retatrutide phase 3", "limit": 15}   -> strong, 9
+ 6.0s zotero_search   {"query": "retatrutide TRIUMPH", "limit": 10}   -> none
+ 6.0s zotero_status   {}
+14.0s zotero_search x2 {"query": "retatrutide", "year_from": 2025} (thin, 4); {"query": "\"phase 3\" retatrutide trial results", "year_from": 2024} (thin, 1)
+14.0s hermes_web_search (via tool_call) "retatrutide phase 3 trial results TRIUMPH 2025 2026"
+21.1s web_search x2, zotero_search {"doi": "10.1056/NEJMoa2301972", "query": "Jastreboff retatrutide"} (strong, 10)
+30.2s zotero_search x3 doi 10.1056/NEJMoa2604169, 10.1056/NEJMoa2611477, query "TRIUMPH-1 retatrutide" (none); web_extract x2 (nejm.org, pubmed, retatrutide.med)
+49.3s web_extract x2, web_search x2
+61.1s zotero_search x3 doi 10.1016/S0140-6736(26)01861-1, 10.1016/S0140-6736(26)00967-0, 10.1056/NEJMoa2301972
```
Skill loaded: yes (first message). Library first: five `zotero_search` calls before the first web call (`hermes_web_search` at +14.0 s). The agent concluded the phase 3 papers (NEJM TRIUMPH-1, Lancet TRIUMPH-2 and TRANSCEND-T2D-1, the NEJM sleep apnea paper) are not held, and gave their DOIs. No sqlite, curl or terminal. Log lines:
```
17:35:25,482 tool tool_describe completed (0.25s, 2437 chars)
17:35:25,488 tool skill_view completed (0.25s, 3527 chars)
17:35:28,253 tool zotero_search completed (0.63s, 8599 chars)
17:35:28,279 tool zotero_search completed (0.02s, 6523 chars)
17:35:28,304 tool zotero_status completed (0.02s, 1105 chars)
17:35:35,775 tool zotero_search completed (0.20s, 2599 chars)
17:35:36,117 tool zotero_search completed (0.33s, 7384 chars)
17:35:43,616 tool web_search completed (0.95s, 7172 chars)
17:35:43,704 tool web_search completed (1.04s, 10123 chars)
17:35:43,726 tool zotero_search completed (0.01s, 3407 chars)
17:35:51,934 tool zotero_search completed (0.18s, 204 chars)
17:35:51,945 tool zotero_search completed (0.00s, 204 chars)
17:35:52,300 tool zotero_search completed (0.35s, 3687 chars)
17:35:53,866 tool web_extract completed (1.56s, 5503 chars)
17:35:57,538 tool web_extract completed (5.24s, 16606 chars)
17:36:11,459 tool web_search completed (0.63s, 4311 chars)
17:36:11,904 tool web_search completed (1.08s, 3232 chars)
17:36:17,617 tool web_extract completed (6.79s, 16715 chars)
17:36:22,842 tool zotero_search completed (0.18s, 212 chars)
17:36:22,852 tool zotero_search completed (0.00s, 212 chars)
17:36:22,858 tool zotero_search completed (0.00s, 204 chars)
```

**Prompt 3: highlights in "Managing Obesity".** Wall 26 s (span 24.8 s).
```
+ 5.2s skill_view      hermes-zotero:zotero-library
+ 5.2s tool_describe   zotero_search, zotero_read, zotero_status
+ 7.3s zotero_search   {"query": "Managing Obesity NEJM", "limit": 10}
+10.2s zotero_read     {"key": "Q3K5IWZH", "mode": "annotations", "max_chars": 8000}
```
Skill loaded: yes. `zotero_read` with `mode: annotations` on Q3K5IWZH, as expected; the answer quotes 19 highlights (6 on p. 719, 11 on p. 720, 2 on p. 721). No web call, no sqlite. Log lines:
```
17:37:02,052 tool tool_describe completed (0.02s, 2437 chars)
17:37:02,057 tool skill_view completed (0.02s, 3527 chars)
17:37:04,302 tool zotero_search completed (0.25s, 6783 chars)
17:37:07,206 tool zotero_read completed (0.21s, 4537 chars)
```

**Pass criteria.** All three sessions called `zotero_search` before any web tool, and none opened `zotero.sqlite`, the plugin's `index.sqlite` or `~/Zotero-Markdown/index.sqlite` through terminal, sqlite or Python. Notes: (a) prompt 1 matches the expected thin / 7 papers but went to the web for eight rounds rather than "only for the gap if at all"; (b) the `retatrutide` unfiltered count (12) was not seen in a session, since the agent searched `retatrutide phase 3` (9) and with `year_from`; (c) log timestamps are local time (UTC+1), the shell `date -u` stamps are UTC.

**Restore.** `cp config.yaml.task09-backup config.yaml`, `cmp` printed nothing (identical), `hermes gateway restart` run again, `hermes skills list` shows `zotero` and `local-literature` enabled. The backup file `~/.hermes/config.yaml.task09-backup` is left in place.
