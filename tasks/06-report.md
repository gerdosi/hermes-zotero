# Task 06 report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / low
## What changed
- zotcore/index.py: new. FTS5 `Index` (schema, transaction, upsert, delete, state, counts), `SyncReport` and the resumable, incremental `sync`.
- tests/test_06_index.py: copied verbatim from the task file.
- zotcore/cli.py: new `sync` subcommand (snapshot, then incremental index update, with progress and summary lines).
- zotcore/tools.py: `zotero_status` gains an `index` key (None unless index.sqlite already exists; never creates it).
## Test output
```
........................................................................ [ 84%]
.............                                                            [100%]
85 passed in 1.05s
```
## Checksums
```
e3b7ddc519306760586ed7e68f94ede2eeede23be916627a19deb3577d96ceda  tests/test_06_index.py
```
## Deviations from the task
- The session ran at low reasoning effort, not the **high** the task asks for. The tests pass, but the transaction/deletion logic deserves a second look at high effort.
- The live check (real library, `~/.hermes/config.yaml` edit, timings) was not run; the task assigns it to Gábor.
## Open questions
- If a text file disappears between the stat and the read inside `sync`, the `OSError` aborts that batch (it rolls back, so the next run resumes safely). The spec has no per-item error handling, so none was added. Should such items be skipped with a warning?

## Live check
Run on Gábor's real library, 6 Nov 2026 (Zotero data dir `/Users/erdoke/Zotero`), with `.venv` tests at 87 passed (task 06b already committed).

### 1. Settings
Added under `plugins.entries` in `~/.hermes/config.yaml` (there was no `hermes-zotero` entry before; backup at `~/.hermes/config.yaml.bak-pre-task06-live`):
```yaml
    hermes-zotero:
      settings:
        markdown_path: ~/Zotero-Markdown
        libraries: [user, 4805701]
```
`hermes zotero doctor` shows `markdown_path: ~/Zotero-Markdown` and `libraries: ['user', '4805701']`, so the plugin reads them.

### 2. First sync (`time hermes zotero sync`)
```
Snapshot: /Users/erdoke/.hermes/plugin-data/hermes-zotero/snapshot/current/zotero.sqlite (attempts 1)
  2000/19290 items examined
  ...
  19290/19290 items examined
Sync: indexed 19290, deleted 0, examined 19290 in 70.3s
Index: 19290 items, 1067135 passages; text sources {'ft-cache': 484, 'markdown': 18336, 'metadata': 470}; flags {'body_not_read': 470, 'scanned_or_empty': 86}
hermes zotero sync  48.73s user 15.34s system 89% cpu 1:11.98 total
```
Matches the reference run: 19,290 items, 18,336 from Markdown, 1,067,135 passages (reference 1,067,137; a difference of 2), 70.3 s, no warnings. Per library: `user` 18,597 items, `4805701` 693 items.

### 3. Second sync
```
Sync: indexed 0, deleted 0, examined 19290 in 1.4s
Index: 19290 items, 1067135 passages; text sources {'ft-cache': 484, 'markdown': 18336, 'metadata': 470}; flags {'body_not_read': 470, 'scanned_or_empty': 86}
hermes zotero sync 2>&1  1.46s user 0.66s system 62% cpu 3.375 total
```
`indexed 0` in 1.4 s (3.4 s wall including snapshot copy), as expected. Counts unchanged.

### 4. `hermes zotero doctor` and `zotero_status`
`doctor`: data dir `/Users/erdoke/Zotero` (source: Zotero prefs), snapshot `taken_at: 2026-11-06T12:32:24Z`, `stale: False`, no warnings.

`zotero_status` called directly on the committed code with the live plugin data folder (same `data_root` as Hermes):
```json
{"items": 19290, "passages": 1067135, "libraries": {"4805701": 693, "user": 18597}, "by_source": {"ft-cache": 484, "markdown": 18336, "metadata": 470}, "flags": {"body_not_read": 470, "scanned_or_empty": 86}, "last_sync": "2026-11-06T12:32:26Z"}
```
**Through Hermes.** The first two attempts (`hermes -z ...`) returned the old task-01 payload (`stage: scaffold`, with no `data_dir`, `snapshot` or `index` keys). `~/.hermes/logs/gateway.log` showed the prompts arriving as `gateway.run: inbound message: platform=local`, so `-z` goes through the running gateway, which had loaded the plugin at 08:45, before tasks 02-06. After `hermes gateway restart` (launchd service, PID 3868 to 17812) the same prompt returned the current payload:
```json
{"ok": true, "plugin_version": "0.1.0", "stage": "scaffold", "settings": {"zotero_data_dir": "", "markdown_path": "~/Zotero-Markdown", "libraries": ["user", "4805701"], ...}, "warnings": [], "data_dir": {"path": "/Users/erdoke/Zotero", "source": "prefs:...", ...}, "snapshot": {"taken_at": "2026-11-06T12:32:24Z", "stale": false}, "index": {"items": 19290, "passages": 1067135, "libraries": {"4805701": 693, "user": 18597}, "by_source": {"ft-cache": 484, "markdown": 18336, "metadata": 470}, "flags": {"body_not_read": 470, "scanned_or_empty": 86}, "last_sync": "2026-11-06T12:32:26Z"}}
```
The `index` block is identical to the direct handler call. Note: after any plugin code change the gateway must be restarted (`hermes gateway restart`) before Hermes tools reflect it.

### 5. Size and warnings
```
$ du -sh ~/.hermes/plugin-data/hermes-zotero
3.4G	/Users/erdoke/.hermes/plugin-data/hermes-zotero
```
Reference was about 3.5 GB. Warnings: none from either sync or `doctor`.
