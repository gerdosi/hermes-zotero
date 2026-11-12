# hermes-zotero

A Hermes Agent plugin that lets the agent search and read the papers in your Zotero library before it goes to the web. It builds a local, read-only full-text index from a copy of Zotero's database, so it works with Zotero open or closed, needs no API key and installs no Python packages.

Ask Hermes things like:

- "What does my library say about SCD1 and ferroptosis? Cite the papers."
- "Is the retatrutide phase 3 trial in my Zotero library? If not, find it online."
- "What did I highlight in the NEJM paper 'Managing Obesity'?"

The agent searches your library first, sees whether it covers the topic well (`strong`), partly (`thin`) or not at all (`none`), reads the relevant passages, and cites them. It uses the web only for what your library lacks.

## What you get

- **Four tools:** `zotero_search`, `zotero_read`, `zotero_status` and `zotero_sync` (details below).
- **A skill**, `hermes-zotero:zotero-library`, that tells the agent to use your library before the web and how to read the results.
- **A command**, `hermes zotero`, with `doctor`, `snapshot` and `sync`.
- **Tables and provenance flags**, if you supply your own Markdown conversions: tables are searched and read as tables, and papers read by OCR are flagged. See [the corpus guide](docs/CORPUS.md).

## Requirements

- Hermes Agent 0.23.0 or later.
- Zotero desktop, with its data directory on the same computer. Tested with Zotero 11 on macOS; the Windows and Linux paths are implemented but not yet tested.
- Zotero's full-text indexing on (the default), so that Zotero has extracted the text of your PDFs.

## Install

```bash
hermes plugins install https://github.com/gerdosi/hermes-zotero
hermes plugins enable hermes-zotero
hermes zotero doctor      # finds your Zotero data directory and shows the settings
hermes zotero sync        # builds the index; safe to stop and run again, it resumes
```

If you use the Hermes gateway (the desktop app or a messaging channel), run `hermes gateway restart` afterwards so it loads the plugin.

**Updating from 0.1.0:** the index has a new layout, so it is rebuilt once. After the update run `hermes zotero sync` (it takes about as long as the first sync), or let the agent call `zotero_sync` until it reports `done: true`. Until then the tools answer with the error `index_outdated`.

`doctor` looks for Zotero's data directory in Zotero's own `prefs.js`, then in `~/Zotero`. If it is somewhere else, set `zotero_data_dir` (see Settings).

## Tools

| Tool | What it does |
| --- | --- |
| `zotero_search` | Full-text search over your library, ranked by passage (BM25). Returns short snippets and a `coverage` verdict: `strong`, `thin` or `none`. Filters: `collection`, `tag`, `year_from`, `year_to`, `library`. `in_tables` = true searches only inside tables. `doi` checks whether you hold a given paper. |
| `zotero_read` | Reads a bounded part of one paper: at the best match for a query, or at an offset to page on. `mode` = `annotations` returns your own highlights, comments and notes instead. `mode` = `tables` lists the paper's tables, and with `table` = N returns one as rows. Every result carries a citation line. |
| `zotero_status` | Whether the index is ready, what it holds, when the snapshot was taken, and what to do next. |
| `zotero_sync` | Adds new and changed papers to the index. Each call stops after `budget_seconds` (default 30) and the next call resumes. |

The coverage verdict counts papers that hold every search word in one passage. `strong` means at least 8 such papers, at least 2 of them from the last 5 years; `thin` means fewer; `none` means no paper has them all. The three numbers are settings.

## Keeping the index up to date

New papers reach the index in one of three ways:

- Run `hermes zotero sync` yourself. Re-checking an unchanged library takes a second or two.
- Ask the agent ("bring my Zotero index up to date"); it calls `zotero_sync`.
- Schedule it without the agent, so no model is called. Save this as `zotero-sync.py` in Hermes' `scripts` folder (`~/.hermes/scripts/`):

  ```python
  import contextlib, io, sys

  from hermes_cli.main import main

  log, code = io.StringIO(), 0
  sys.argv = ["hermes", "zotero", "sync"]
  try:
      with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
          main()
  except SystemExit as exit_:
      code = exit_.code
  if code not in (0, None):
      print(f"hermes zotero sync failed ({code}):\n" + log.getvalue()[-2000:])
  ```

  Then run `hermes cron create "17 4 * * *" --no-agent --script zotero-sync.py --name "Zotero index sync"`. Hermes runs it every night at 04:17 while its gateway is running. It prints nothing when the sync works, so you only hear about failures.

## Settings

Set them with `hermes config set plugins.entries.hermes-zotero.settings.<name> <value>`, for example:

```bash
hermes config set plugins.entries.hermes-zotero.settings.libraries '["user", "1234567"]'
```

| Setting | Default | Meaning |
| --- | --- | --- |
| `zotero_data_dir` | empty | Zotero data directory. Empty: found from Zotero's `prefs.js`, then `~/Zotero`. |
| `markdown_path` | empty | Optional folder of your own Markdown conversions (see Text sources). |
| `libraries` | `["user"]` | Libraries to index: `user` (My Library) and group IDs (the number in the group's address on zotero.org). |
| `coverage_strong_min` | 8 | Papers needed for a `strong` verdict. |
| `coverage_recent_min` | 2 | Recent papers needed for `strong`. |
| `coverage_recent_years` | 5 | How many years count as recent. |
| `sync_batch_items` | 200 | Papers indexed per database transaction during a sync. |
| `sync_tool_budget_seconds` | 30 | Time limit of one `zotero_sync` call (5–60). |
| `read_max_chars_default` | 4000 | Characters `zotero_read` returns when the agent does not ask for a size. |
| `read_max_chars_cap` | 12000 | Most characters one `zotero_read` call returns. |

## Text sources

For each paper the index takes the best text it can find, in this order:

1. **Your own Markdown**, if `markdown_path` is set: one file per paper, named `K:<Zotero item key>.md` or `doi_<DOI>.md` (the DOI in lower case, with every character other than letters, digits, dots and hyphens replaced by `_`), directly in that folder or in its `library` subfolder. Files under 200 bytes are skipped. Headings become sections in the results. A file can also carry a small header (`ocr: true`) and a section of structured tables; [the corpus guide](docs/CORPUS.md) has the format and advice on producing such files. The plugin itself contains no converter.
2. **Zotero's full-text cache** (`.zotero-ft-cache` next to each stored PDF), the text Zotero extracted itself.
3. **The title and abstract** only.

Results say which source was used and flag papers whose body text is missing: `body_not_read` (no text found), `scanned_or_empty` (a stored PDF with little or no extracted text: a scan without OCR, or a PDF Zotero has not indexed yet) and `truncated` (Zotero indexed only the first pages; raise Zotero's indexing limits to fix it). Two more flags describe the text itself: `ocr` (your Markdown file says the text came from OCR, so digits and symbols may be wrong) and `text_damaged` (the text shows clear conversion damage, such as words run together or missing letters; search can miss such a paper).

## Citations

Every `zotero_read` result has a citation line. When Zotero is running and its local API is on, the citation is Zotero's own APA reference. Otherwise it is an approximate author-year line built from the index and marked `approximate: true`.

Zotero's local API is off by default. To switch it on: Zotero → Settings → Advanced → "Allow other applications on this computer to communicate with Zotero". While it is on, any program on your computer can read your library through it. The plugin works either way.

## Disclosures

What the plugin reads, writes and connects to:

- **Reads outside its own folder:** your Zotero data directory (it copies `zotero.sqlite` and its write-ahead log, and reads the `.zotero-ft-cache` text files in `storage/`), Zotero's profile file `prefs.js` (only to find the data directory), and the `markdown_path` folder if you set one.
- **Writes:** only to its own data folder in your Hermes profile (`plugin-data/hermes-zotero`): the snapshot copy, the index and a lock file. Zotero's own database is only copied, never written to, locked or opened with SQLite.
- **Network:** one kind of request, to Zotero on the same computer (`http://127.0.0.1:23119`), to fetch a formatted citation. It succeeds only when Zotero's local API is switched on. Nothing else goes over the network, and the request bypasses any proxy settings.
- **No telemetry, no credentials, no shell commands, no background processes.** The plugin runs only when the agent calls a tool or you run `hermes zotero`.
- **Privacy:** the index holds the full text of your papers. It stays in the plugin's data folder; to remove it, delete that folder after uninstalling.

## Disk space and speed

The index needs about 180 KB per paper with full text, plus a copy of `zotero.sqlite`. Measured on an Apple-silicon MacBook Air with 19,290 papers: a first sync of about 70 seconds (version 0.1.0; since 0.2.0 each paper's text is also checked for damage, which adds some time), a 3.5 GB index plus a 163 MB snapshot, a re-check of an unchanged library in under 2 seconds, and searches in under half a second.

## Limitations

- Search is lexical (BM25 with stemming), not semantic: it finds the words you search for, not their synonyms. The skill tells the agent to use scientific names rather than brand names.
- Papers whose PDFs have no text layer are searchable by title and abstract only, unless you supply Markdown for them.
- Annotations are read from the snapshot when asked for; they are not searchable.
- Tables are recognised only in the structured-tables section of your own Markdown files. Tables in Zotero's extracted text, and pipe tables in the body of a Markdown file, are plain text.
- The `text_damaged` flag is one-sided: a paper without it can still have flaws in its text.
- The plugin never changes your Zotero library: no tagging, filing or editing.

## Development

```bash
python -m pytest
```

The tests need only Python 3.11 or later and pytest; they build small Zotero libraries of their own and never touch yours. The plugin was built in reviewed steps: each task in [`tasks/`](tasks/) holds the spec, the acceptance tests and the executor's report, and [`AGENTS.md`](AGENTS.md) has the rules every step followed.

## License

MIT. See [LICENSE](LICENSE).
