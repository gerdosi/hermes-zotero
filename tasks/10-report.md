# Task 10 report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / low
## What changed
- README.md: replaced with the verbatim text from the task.
- plugin.yaml: new `description` (no longer says "No network") and the real `homepage`.
- .gitignore: added `review/`.
- tests/test_10_release.py: created verbatim from the task (12 new tests).
- tasks/10-report.md: this report.
- Committed as they were on disk (reviewer changes): tasks/10-readme-release.md, tasks/09-skill-tags-descriptions.md, tasks/09-report.md, tests/test_09_skill_and_tags.py, AGENTS.md, tasks/README.md.
## Test output
```
........................................................................ [ 49%]
........................................................................ [ 99%]
.                                                                        [100%]
145 passed in 3.48s
```
## Checksums
```
7b3cf5700f5ad2c94b533627d9f82e3b1ec9dc6796c8e31eae5b9ef9e8e8d3cf  tests/test_10_release.py
4406c3364aab373517e3723c9c95b31b8fd3888c5b4134790862e0b1193a6bcf  README.md
0f7933df4ffcbe1f95baeea9fa6521634dfec47c4fecd018f7f359ae949f87d5  tests/test_09_skill_and_tags.py
```
All three match the task's table.
## Deviations from the task
- The task asks for reasoning `medium`; this session ran at a lower effort setting. Output is verbatim and checksum-verified, so the difference should not matter.
- The live check (steps 1-4 of the task) was not run: it is Gábor's, after the commit.
## Open questions
- none

## Live check

Run by Claude Sonnet 5.5 on 2026-11-06, on commit 2fd0599, in Gábor's normal Hermes setup (Hermes' own notice "install out of sync (venv: out of sync with uv.lock)" was already shown before the first step and is left out of the pasted output below).

### Step 1 — validate a clean clone

```
✓ manifest — plugin.yaml parses
✓ manifest fields — name, version, description present
✓ requires_hermes — spec '>=0.23.0' parses
✓ config schema — shape valid
✓ requires_env — all entries UPPER_SNAKE
✓ oauth — not declared
✓ loadable — entry: __init__.py
✓ python dependencies — none declared
✓ capability probe — register() ran in isolation
✓ declared tools — matches registrations
✓ declared hooks — matches registrations
✓ declared middleware — matches registrations
✓ built-in tool collisions — no collisions
✓ security scan — safe
✓ no core override — no runtime rebinds of Hermes core
◆ Isolation — runs in the plugin host (plugins.isolation: host)
  · ctx.register_cli_command() is skipped in the host (`hermes <command>` 
subcommands are wired into the local CLI parser)

Validation passed.
```

Exit code 0, no `--install-deps`.

### Step 2 — push

```
To https://github.com/gerdosi/hermes-zotero.git
   54c9937..2fd0599  main -> main
```

The GitHub page renders the README: 13 sections, 2 tables, 4 code blocks, the install commands and the disclosures visible.

### Step 3 — fresh install in a throwaway profile (`zfresh`)

Clock: first command 20:28:51, answer printed 20:31:07, so **2 min 16 s** in total, including two things the task did not expect (below).

**Two deviations from the task's commands, both caused by `hermes profile create zfresh --clone`:**

1. `--clone` also copied the installed plugins, which the task comment says it does not. That included `hermes-zotero` as a link to `~/Developer/hermes-zotero`, so `hermes plugins install` refused with "Plugin 'hermes-zotero' is already installed outside the catalog". I removed that link (inside `zfresh` only) and the install went on.
2. The second install attempt failed with `Two workspace members are both named hermes-push` (`hermes-push` had been copied into the profile and collided with the default profile's copy). That is a Hermes environment problem, not the plugin's. I moved all ten cloned plugins out of `zfresh/plugins` into a stash folder in the same profile and ran the install again; it worked. So the profile had no other plugins, like a stranger's.

Install (third attempt, 20:29:32), complete output:

```
Warning: custom (unreviewed) source — not from the Hermes catalog.
Cloning https://github.com/gerdosi/hermes-zotero...

╭───────────────────────────── ✓ Installed ─────────────────────────────╮
│ Plugin installed: https://github.com/gerdosi/hermes-zotero            │
│ Location: /Users/erdoke/.hermes/profiles/zfresh/plugins/hermes-zotero │
╰───────────────────────────────────────────────────────────────────────╯

Replacement installed; plugin selection was not changed.
```

No scanner warning and no confirmation prompt; the only notice is the standard "custom (unreviewed) source" line. `plugins enable` said "already enabled" (the cloned config had it enabled).

Config: `libraries = ['4805701']` and `markdown_path = ""` were set. `hermes config set skills.disabled …` printed "'skills.disabled' is not a recognized config key — it was saved anyway, but Hermes may not read it", so the user's own `zotero` and `local-literature` skills may not have been switched off. The agent did not load them (see its calls below).

`hermes -p zfresh zotero doctor`:

```
hermes-zotero 0.1.0
  zotero_data_dir: 
  markdown_path: 
  libraries: ['4805701']
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
Snapshot:
  none yet (run `hermes zotero snapshot`)
```

`time hermes -p zfresh zotero sync` (2.16 s wall clock, of which the sync itself 0.9 s):

```
Snapshot: /Users/erdoke/.hermes/profiles/zfresh/plugin-data/hermes-zotero/snapshot/current/zotero.sqlite (attempts 1)
  200/693 items examined
  400/693 items examined
  600/693 items examined
  693/693 items examined
Sync: indexed 693, deleted 0, examined 693 in 0.9s
Index: 693 items, 14811 passages; text sources {'ft-cache': 460, 'metadata': 233}; flags {'body_not_read': 233, 'scanned_or_empty': 96}
```

`time hermes -p zfresh -z "Which papers in my Zotero library discuss insulin resistance? Cite two of them."`: 1 min 13.5 s (20:29:54 to 20:31:07; model grok-4.7). "insulin resistance" has hits in the group (390 items match both words, coverage `strong`).

Agent's tool calls, from `zfresh/state.db`, in order:

```
skill_view  hermes-zotero:zotero-library
skill_view  research-answer-formatting
tool_describe  zotero_search, zotero_status, zotero_read
tool_call  zotero_search {"query": "insulin resistance", "limit": 10}
tool_call  zotero_status {}
tool_call  zotero_read {"key": "3XGAQJYJ", "max_chars": 2500, "query": "insulin resistance definition mechanism"}
tool_call  zotero_read {"key": "XGRB6QRX", "max_chars": 2500, "query": "insulin resistance metabolic inflammation"}
skill_view  research-answer-formatting (references/citation-lookup.md)
tool_call  zotero_read {"key": "3XGAQJYJ", "max_chars": 1800, "offset": 0}
web_extract  https://api.crossref.org/works/10.1152/physrev.00063.2017 and …/10.1161/circresaha.119.315896
```

It loaded `hermes-zotero:zotero-library` first, then `zotero_search` and `zotero_read` as expected. Two things beyond the expected: it also loaded the cloned `research-answer-formatting` skill, which led it to look up the two references on Crossref over the web (`web_extract`) although `zotero_read` already returns a citation line. That comes from the cloned skills, not from this plugin, but a stranger without that skill would not see it.

First lines of the answer:

```
Executive Summary

The local index matches both words in 390 items, so coverage is strong. Many sit in an Insulin Resistance collection. Two full-text reviews that discuss the topic are cited below.

Petersen and Shulman review insulin action and insulin resistance in muscle, liver, and white fat.[1](https://doi.org/10.1152/physrev.00063.2017) One section treats ectopic lipid, ...
```

Cited: Petersen & Shulman 2018 (Physiological Reviews 98(4)) and Wu & Ballantyne 2020 (Circulation Research 126(11)).

Clean-up: `hermes profile delete zfresh -y` removed the profile, its index and its alias. Before that I unlinked the stash's `conduit_push` link so the delete could not reach the default profile's real plugin; the default profile's plugins are intact (`~/.hermes/plugins/hermes-zotero` still points at the dev checkout).

### Step 4 — nightly sync without the agent (default profile)

`~/.hermes/scripts/zotero-sync.py` was written by extracting the README block (two leading spaces removed), no other change. No file of that name existed before.

```
Created job: 926821cc3b42
  Name: Zotero index sync
  Schedule: 17 4 * * *
  Script: zotero-sync.py
  Mode: no-agent (script stdout delivered directly)
  Next run: 2026-11-07T04:17:00+01:00
```

```
Triggered job: Zotero index sync (926821cc3b42)
  Next run: 2026-11-07T04:17:00+01:00
  Ran now: succeeded.
```

```
deb5cf60a3e94b9eaa1eec43c4368ffb  completed  job=926821cc3b42  source=direct  2026-11-06T20:31:42.741422+01:00
```

`agent.log`:

```
2026-11-06 20:31:45,895 INFO cron.scheduler: Job '926821cc3b42' (no_agent): empty stdout — silent run
2026-11-06 20:31:45,901 INFO cron.scheduler: Job '926821cc3b42': agent returned [SILENT] — skipping delivery
```

Nothing was delivered. Two `agent.codex_runtime` lines (model grok-4.7) appear in the log in the same few seconds, at 20:31:42.436 and .571, both before the run was recorded at 20:31:42.741, so they come from other gateway activity; the job itself is logged as `no_agent`.

**The job is kept** (about 2 seconds a night). To remove it: `hermes cron remove 926821cc3b42`. A different, older job, "Zotero Markdown weekly sync", already existed and was not touched.

### Findings for the next task

- The README's "Install" works for a stranger as written. The two problems above only appear when cloning a profile that already has plugins, and the task's comment under step 3 ("copies config, keys and skills; not plugins or their data") is wrong for Hermes at this version.
- The task's step 3 setting `skills.disabled` is not a recognised key.
