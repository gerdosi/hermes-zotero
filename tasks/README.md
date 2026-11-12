# How to run a task (for Gábor)

Each task file says which **model** and **reasoning level** to use. Default executor: **Claude Sonnet 5.5 in Claude Code** (prepaid in your Team plan): `/model`, pick Sonnet, set effort with the arrow keys. Set the effort in the app's model picker before each task: the repo has no `.claude/settings.json`, so nothing sets it for you. DeepSeek V4.1 Flash 1017 in Hermes also works.

## Run one task

```bash
cd ~/Developer/hermes-zotero        # the repo; AGENTS.md is picked up automatically
hermes
```

Then, inside the session:

```
/model <DeepSeek V4.1 Flash 1017 id as listed by `hermes model`>
/reasoning low        # or: /reasoning max, as the task header says
Execute tasks/01-scaffold.md exactly as written. Follow AGENTS.md. Stop when the task's acceptance tests pass and the report is committed.
```

Use a **fresh session per task**: it keeps the context small and cheap.

## Off-peak (half price)

DeepSeek peak hours: Mon–Fri 01:00–04:00 and 06:00–10:00 UTC, i.e. **02:00–05:00 and 07:00–11:00 CET** (CEST from late March shifts this one hour later). Evenings, afternoons after 11:00 and weekends are off-peak.

## After each task

1. Read `tasks/NN-report.md`. If `BLOCKED`, rerun once at the next reasoning level up (low → medium → high → max). If it is still blocked, bring it to review.
2. Do the task's **Live check** on your Mac (it needs Zotero), and add the results to the report under `## Live check`.
3. `git push`, then start a fresh Claude session: "Review task NN in <repo URL>. Plan doc: <doc link>."

## Task list

| Task | Title | Reasoning | Needs Zotero for live check |
| --- | --- | --- | --- |
| 01 | Scaffold: manifest, settings, status tool, CLI | low | no (Hermes only) |
| 01b | Make the tests run on current pytest | low | no |
| 02 | Find the Zotero data directory | low | yes |
| 03 | Consistent snapshot of zotero.sqlite + WAL | Sonnet **high** / DeepSeek **max** | yes |
| 03b | Retry when Zotero restarts its WAL during the copy | low | no (live check of 03 after this) |
| 04 | Read items from the snapshot | medium | no |
| 05 | Pick each item's text and split it into passages | low | no |
| 06 | The search index and `hermes zotero sync` | **high** | yes (full sync, ~3.5 GB index; run after 06b) |
| 06b | One unreadable file must not block the sync | low | no |
| 07 | `zotero_search` (coverage, DOI check) and `zotero_read` | medium | yes (queries on the real index; `hermes gateway restart` first) |
| 08 | Annotations, citation line, `zotero_sync` tool | medium | yes (annotations and citations with Zotero closed and open; `hermes gateway restart` first) |
| 09 | Bundled skill, `tag` filter, Tool Search descriptions | medium | yes (tag searches, verdict calibration; Hermes runs with your two Zotero skills briefly switched off) |
| 10 | README, disclosures, scanner-safe repo | medium | yes (validate a clean clone, push, fresh install in a throwaway profile, nightly sync job) |
| 11 | Table-aware passages, `in_tables` search, `mode=tables` (0.2.0) | medium | yes (one full re-sync, table searches on the real index; `hermes gateway restart`) |
| 12 | Front matter of corpus files, flag `ocr` | low | no (checked in the local tasks, once files carry front matter) |
| 13 | Damaged-text flag `text_damaged` | low | yes (one full re-sync; the flagged count on the real index) |
| 14 | Corpus guide, README, version 0.2.0 | low | yes (validate a clean clone, push, fresh install; then the catalog pin) |
