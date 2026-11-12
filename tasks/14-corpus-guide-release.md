# Task 14 — Corpus guide, README and version 0.2.0

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code |
| Reasoning | **low** (two verbatim files and a patch). Set it in the app's model picker before pasting the prompt. |
| Budget | ≤ 20 tool calls |
| Depends on | task 13 committed (224 tests pass) |
| Done when | `.venv/bin/python -m pytest` shows **229 passed** (224 old + 5 new), the checksums match, report committed |

## Goal

Finish release 0.2.0:

1. **`docs/CORPUS.md`**, the corpus guide: the Markdown corpus spec v1 (file names, optional front matter, the structured-tables section), how the plugin picks a paper's text, the flags, how to produce a corpus safely, and tool recommendations. Recommendations only: the plugin ships no converter, OCR engine or model.
2. **README**: the new search and read options, the two new flags, the one-time index rebuild after updating, and a link to the guide.
3. **Version 0.2.0** in `plugin.yaml`, `pyproject.toml` and `zotcore/__init__.py` (the bundled skill already says 0.2.0).

## Facts

- Hermes' install scanner reads every file in the repository, documentation included. The guide therefore has prose, tables and Markdown examples only: nothing to run, no shell commands. A test checks that, and that the guide's two examples (a front-matter header and a tables section) go through the plugin's own parser with the results the guide describes.
- The reviewer ran `hermes plugins validate --install-deps` (Hermes main of 12 Nov 2026) on a clean copy of the repository as it is after this task: validation passed, scan verdict `safe`.
- Docling's licence (MIT) and repository address were checked on 12 Nov 2026 against its PyPI page. The statements about its behaviour are Gábor's own experience and are worded as such.
- The README keeps the 0.1.0 timing for the first sync and says that 0.2.0 takes somewhat longer; the measured number goes in after the live check of task 13.

## Files

```
create  docs/CORPUS.md                            (verbatim, below)
create  tests/test_14_release.py                  (verbatim, below)
modify  README.md, plugin.yaml, pyproject.toml, zotcore/__init__.py   (the patch below)
create  tasks/14-report.md
commit  tasks/14-corpus-guide-release.md, tasks/README.md   (added or updated by the reviewer; commit them as they are)
```

Do not touch any other file.

## Steps

1. Run `.venv/bin/python -m pytest` first: 224 passed.
2. From the repo root, run this. It writes the two verbatim files and puts the patch into the system's temporary folder, and prints a SHA-256 for each:

```python
import hashlib, pathlib, re, tempfile
md = pathlib.Path("tasks/14-corpus-guide-release.md").read_text(encoding="utf-8")
for name, _, body in re.findall(r"<!-- file: (\S+) -->\n(`{3,4})\w*\n(.*?)\n\2\n<!-- /file -->", md, re.S):
    out = pathlib.Path(tempfile.gettempdir()) / "task14.patch" if name == "PATCH" else pathlib.Path(name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body + "\n", encoding="utf-8", newline="\n")
    print(hashlib.sha256(out.read_bytes()).hexdigest(), out)
```

3. Compare the printed checksums with the table below. A mismatch means the copy went wrong: stop and fix it, do not edit the files.
4. Apply the patch from the repo root: `git apply --check <path printed for the patch>`, then `git apply <the same path>`. If a hunk does not apply, make the same change by hand; the tests decide.
5. Run `.venv/bin/python -m pytest`: 229 passed.
6. Fill in the report `tasks/14-report.md` (the template is in the project rules file) and make one commit: `task 14: corpus guide, README, version 0.2.0`.

### Checksums

| File | SHA-256 |
| --- | --- |
| `docs/CORPUS.md` | `770dab69556f3f178b1fb93487a00bd9195bbd4cacc507010e087e871d3a2860` |
| `tests/test_14_release.py` | `5e31461d97268152ff8ff25e84de356b543581f4d53ffdaf9cba9f25da74b837` |
| the patch file | `a1a0fac7ea230062afc126a70489e9da87dad20cbab96b356d41c8d78451a436` |
| `README.md` after the patch | `33c255437b283d8073cde5028ddbd56527f6407c192e09e484ac1522a5f0e13a` |
| `plugin.yaml` after the patch | `022f9b5426f790cc257939829410fe2b7689e476cc6c1e1c537f429a75712571` |
| `pyproject.toml` after the patch | `a80127b2731fae56b8d985442277d7996f3eb323abb82da4f83e43d0d0653e55` |
| `zotcore/__init__.py` after the patch | `bedc3e4c373b6e40a9373801e4c22f436cb766862e189c586887b42148c44d20` |

## Spec — `docs/CORPUS.md`

Reviewer-written; copy it byte for byte. (It is fenced with four backticks here because it contains code fences of its own.)

<!-- file: docs/CORPUS.md -->
````markdown
# The Markdown corpus (spec v1)

hermes-zotero works without any of this: by default it indexes the text Zotero itself extracted from your PDFs. This guide is for people who convert their papers to Markdown with a tool of their own choice and want the plugin to use that text instead. Better conversions give better search, structured tables and provenance flags, through the same four tools.

The plugin contains no converter, no OCR engine and no model, and it will never start one. The Markdown folder is the whole interface: a converter writes files into it, the plugin reads them. Point the plugin at the folder with the `markdown_path` setting.

## How the plugin picks a paper's text

For each Zotero item, in this order:

1. **A Markdown file** in the corpus folder that belongs to the item (matched by DOI, then by the item's key, then by the keys of its attachments).
2. **Zotero's full-text cache** (`.zotero-ft-cache` next to each stored attachment).
3. **Title and abstract** only.

Search hits and reads name the source (`markdown`, `ft-cache` or `metadata`).

## The spec

### Files

- One paper per file, UTF-8, directly in the folder or in its `library` subfolder.
- File name, either form:
  - `doi_<slug>.md`, where the slug is the DOI in lower case with every run of characters other than letters, digits, dots and hyphens replaced by one `_`. `10.1016/j.cmet.2019.05.003` becomes `doi_10.1016_j.cmet.2019.05.003.md`.
  - `K:<key>.md`, where the key is the eight-character Zotero key of the item or of one of its attachments, for papers without a DOI.
- Files smaller than 200 bytes are ignored.
- The plugin notices a changed file by its name, size and modification time, and re-indexes that paper on the next sync.

### Front matter (optional)

A file may start with a small header. Everything in it is optional, and a file without it is a valid v1 file.

```markdown
---
spec: 1
ocr: true
text_tool: docling 2.94
tables: structured
---
# Title of the paper
```

| Key | Value | Meaning |
| --- | --- | --- |
| `spec` | `1` | The version of this spec the file follows. |
| `ocr` | `true` or `false` | The body text came from OCR. The plugin puts the flag `ocr` on the paper. |
| `text_tool` | free text | The tool and version that produced the text. For your own records. |
| `tables` | `structured` | The file has a structured-tables section (below). For other tools; the plugin looks for the section itself. |

Rules:

- The opening `---` is the first line of the file, the next line is a `key: value` pair starting in the first column, and the closing `---` follows within 100 lines. A `---` anywhere else is an ordinary Markdown rule.
- Only top-level `key: value` lines are read. Indented lines, list items and comments are skipped; unknown keys are ignored. Values may be quoted.
- The header is not indexed and never appears in the text the tools return.

### Body

Plain Markdown. Headings (`#` to `######`) become the section names shown in search hits. A common layout is a title line, a few lines of metadata, the abstract, then the text of the paper. Text from further attachments of the same item can follow under a heading of its own.

### Structured tables (optional)

Tables can go into one section at the end of the file:

```markdown
## Tables (structured)

A note from the converter may stand here. It is not indexed.

### Table 1
Table 1. Baseline characteristics

<table>
<tr><th></th><th>Women</th><th>Men</th></tr>
<tr><td>Age (yr)</td><td>59 ± 11</td><td>58 ± 11</td></tr>
<tr><td>BMI (kg/m2)</td><td>27.1 ± 4.9</td><td>27.9 ± 4.1</td></tr>
</table>

### Table 2

| Marker | Level |
| --- | --- |
| Leptin | high |
```

- The marker line is exactly `## Tables (structured)`. Each table has a heading `### Table N`, optionally a caption on the lines after it, and then one table: HTML (`<table>`, `<tr>`, `<th>`, `<td>`) or a Markdown pipe table.
- Header rows are the leading rows made only of `<th>` cells (in a pipe table: the rows above the `| --- |` line).
- Keep the section last. Removing everything from the marker to the end of the file must give back the text without tables.

What the plugin does with it: every table is indexed and returned as pipe rows (`| a | b |`), with entities decoded and markup removed. A table is one search passage; a long one is cut at row ends, and every piece repeats the table's label and header rows. `zotero_search` with `in_tables` searches only these passages, and `zotero_read` with `mode` = `tables` lists a paper's tables or returns one.

Pipe tables in the body of a paper stay ordinary text. Converters often lay out multi-column prose and figures as pipe tables, so only the structured section is trusted.

### What does not belong in the corpus

Credentials, anything that writes back to Zotero, and anything that is not derived from your own attachments.

## Flags the plugin sets

| Flag | Set when | What it tells the agent |
| --- | --- | --- |
| `ocr` | the front matter says `ocr: true` | Digits and symbols may be wrong; say so when quoting numbers. |
| `text_damaged` | the text shows clear conversion damage: words run together, letters or ligatures missing, an unreadable font encoding | Rely on title and abstract; searches can miss the paper. |
| `truncated` | Zotero's text cache holds only the first pages | Results further on were not read. |
| `body_not_read`, `scanned_or_empty` | no text was found for the item | Only title and abstract are in the index. |

`text_damaged` is one-sided: set means damage was found; not set means no sign was found, not that the text is perfect. A paper with this flag is a good candidate for converting again with another tool.

## Producing a corpus

Any converter that writes the files above will do. A few rules keep it safe:

- **Never write to Zotero's data directory,** and do not open `zotero.sqlite` there while Zotero may be running. Work from a copy of the database. Stored attachments are at `storage/<attachment key>/` in the data directory.
- **Convert in an environment of its own,** not inside Hermes' Python environment: converters bring large dependencies and their own version constraints.
- **Keep what the converter produced** (its intermediate output) next to the corpus, so that a bad merge can be undone without converting again.
- **Long batch jobs:** a scheduled Hermes script that runs without the agent has a time limit of one hour. Split a large backlog into runs that stop on their own and continue next time.
- After new files are written, the next `hermes zotero sync` (or the agent's `zotero_sync`) picks them up.

## Tool recommendations

These are recommendations from the author's own use on a library of about 18,000 papers, not a benchmark. Use whatever serves your library.

- [Docling](https://github.com/docling-project/docling) (MIT licence) for text, OCR of scanned PDFs and tables. In the author's own trials on his papers it gave the best results of the tools he tried, at no cost. He set vendors' published comparisons aside, because each favoured its own product. Your papers may behave differently: try a sample of your own first.
- For batches, call Docling from Python rather than through its command line. In the author's runs the command line crashed on a small number of PDFs that the Python interface converted.
- Run OCR only where it is needed, for example when a PDF yields almost no text, and record it with `ocr: true`.
- Extract tables as cell strings and leave charts alone: turning chart images into numbers is unreliable.
- Hosted parsing services send your PDFs to someone else's servers. Check their cost, retention and licence terms before you use one for papers you may not redistribute.

## Versioning

`spec: 1` is this document. Later versions will only add optional keys and sections; a v1 file stays valid.
````
<!-- /file -->

## Spec — the patch

<!-- file: PATCH -->
```diff
diff --git a/README.md b/README.md
index 50d8674..39f9135 100644
--- a/README.md
+++ b/README.md
@@ -15,6 +15,7 @@ The agent searches your library first, sees whether it covers the topic well (`s
 - **Four tools:** `zotero_search`, `zotero_read`, `zotero_status` and `zotero_sync` (details below).
 - **A skill**, `hermes-zotero:zotero-library`, that tells the agent to use your library before the web and how to read the results.
 - **A command**, `hermes zotero`, with `doctor`, `snapshot` and `sync`.
+- **Tables and provenance flags**, if you supply your own Markdown conversions: tables are searched and read as tables, and papers read by OCR are flagged. See [the corpus guide](docs/CORPUS.md).
 
 ## Requirements
 
@@ -33,14 +34,16 @@ hermes zotero sync        # builds the index; safe to stop and run again, it res
 
 If you use the Hermes gateway (the desktop app or a messaging channel), run `hermes gateway restart` afterwards so it loads the plugin.
 
+**Updating from 0.1.0:** the index has a new layout, so it is rebuilt once. After the update run `hermes zotero sync` (it takes about as long as the first sync), or let the agent call `zotero_sync` until it reports `done: true`. Until then the tools answer with the error `index_outdated`.
+
 `doctor` looks for Zotero's data directory in Zotero's own `prefs.js`, then in `~/Zotero`. If it is somewhere else, set `zotero_data_dir` (see Settings).
 
 ## Tools
 
 | Tool | What it does |
 | --- | --- |
-| `zotero_search` | Full-text search over your library, ranked by passage (BM25). Returns short snippets and a `coverage` verdict: `strong`, `thin` or `none`. Filters: `collection`, `tag`, `year_from`, `year_to`, `library`. `doi` checks whether you hold a given paper. |
-| `zotero_read` | Reads a bounded part of one paper: at the best match for a query, or at an offset to page on. `mode` = `annotations` returns your own highlights, comments and notes instead. Every result carries a citation line. |
+| `zotero_search` | Full-text search over your library, ranked by passage (BM25). Returns short snippets and a `coverage` verdict: `strong`, `thin` or `none`. Filters: `collection`, `tag`, `year_from`, `year_to`, `library`. `in_tables` = true searches only inside tables. `doi` checks whether you hold a given paper. |
+| `zotero_read` | Reads a bounded part of one paper: at the best match for a query, or at an offset to page on. `mode` = `annotations` returns your own highlights, comments and notes instead. `mode` = `tables` lists the paper's tables, and with `table` = N returns one as rows. Every result carries a citation line. |
 | `zotero_status` | Whether the index is ready, what it holds, when the snapshot was taken, and what to do next. |
 | `zotero_sync` | Adds new and changed papers to the index. Each call stops after `budget_seconds` (default 30) and the next call resumes. |
 
@@ -97,11 +100,11 @@ hermes config set plugins.entries.hermes-zotero.settings.libraries '["user", "12
 
 For each paper the index takes the best text it can find, in this order:
 
-1. **Your own Markdown**, if `markdown_path` is set: one file per paper, named `K:<Zotero item key>.md` or `doi_<DOI>.md` (the DOI in lower case, with every character other than letters, digits, dots and hyphens replaced by `_`), directly in that folder or in its `library` subfolder. Files under 200 bytes are skipped. Headings become sections in the results.
+1. **Your own Markdown**, if `markdown_path` is set: one file per paper, named `K:<Zotero item key>.md` or `doi_<DOI>.md` (the DOI in lower case, with every character other than letters, digits, dots and hyphens replaced by `_`), directly in that folder or in its `library` subfolder. Files under 200 bytes are skipped. Headings become sections in the results. A file can also carry a small header (`ocr: true`) and a section of structured tables; [the corpus guide](docs/CORPUS.md) has the format and advice on producing such files. The plugin itself contains no converter.
 2. **Zotero's full-text cache** (`.zotero-ft-cache` next to each stored PDF), the text Zotero extracted itself.
 3. **The title and abstract** only.
 
-Results say which source was used and flag papers whose body text is missing: `body_not_read` (no text found), `scanned_or_empty` (a stored PDF with little or no extracted text: a scan without OCR, or a PDF Zotero has not indexed yet) and `truncated` (Zotero indexed only the first pages; raise Zotero's indexing limits to fix it).
+Results say which source was used and flag papers whose body text is missing: `body_not_read` (no text found), `scanned_or_empty` (a stored PDF with little or no extracted text: a scan without OCR, or a PDF Zotero has not indexed yet) and `truncated` (Zotero indexed only the first pages; raise Zotero's indexing limits to fix it). Two more flags describe the text itself: `ocr` (your Markdown file says the text came from OCR, so digits and symbols may be wrong) and `text_damaged` (the text shows clear conversion damage, such as words run together or missing letters; search can miss such a paper).
 
 ## Citations
 
@@ -121,13 +124,15 @@ What the plugin reads, writes and connects to:
 
 ## Disk space and speed
 
-The index needs about 180 KB per paper with full text, plus a copy of `zotero.sqlite`. Measured on an Apple-silicon MacBook Air with 19,290 papers: a first sync of about 70 seconds, a 3.5 GB index plus a 163 MB snapshot, a re-check of an unchanged library in under 2 seconds, and searches in under half a second.
+The index needs about 180 KB per paper with full text, plus a copy of `zotero.sqlite`. Measured on an Apple-silicon MacBook Air with 19,290 papers: a first sync of about 70 seconds (version 0.1.0; since 0.2.0 each paper's text is also checked for damage, which adds some time), a 3.5 GB index plus a 163 MB snapshot, a re-check of an unchanged library in under 2 seconds, and searches in under half a second.
 
 ## Limitations
 
 - Search is lexical (BM25 with stemming), not semantic: it finds the words you search for, not their synonyms. The skill tells the agent to use scientific names rather than brand names.
 - Papers whose PDFs have no text layer are searchable by title and abstract only, unless you supply Markdown for them.
 - Annotations are read from the snapshot when asked for; they are not searchable.
+- Tables are recognised only in the structured-tables section of your own Markdown files. Tables in Zotero's extracted text, and pipe tables in the body of a Markdown file, are plain text.
+- The `text_damaged` flag is one-sided: a paper without it can still have flaws in its text.
 - The plugin never changes your Zotero library: no tagging, filing or editing.
 
 ## Development
diff --git a/plugin.yaml b/plugin.yaml
index 5925713..401daae 100644
--- a/plugin.yaml
+++ b/plugin.yaml
@@ -1,5 +1,5 @@
 name: hermes-zotero
-version: "0.1.0"
+version: "0.2.0"
 manifest_version: 2
 description: "Search and read the papers in your Zotero library before the web: a local, read-only full-text index that works with Zotero closed. No writes to Zotero, no telemetry; its only network call goes to Zotero on this computer, for citations."
 author: "Gábor Erdősi"
diff --git a/pyproject.toml b/pyproject.toml
index 6a9111a..edb1a91 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -1,6 +1,6 @@
 [project]
 name = "hermes-zotero"
-version = "0.1.0"
+version = "0.2.0"
 description = "Read-only local Zotero index for Hermes Agent"
 requires-python = ">=3.11"
 license = "MIT"
diff --git a/zotcore/__init__.py b/zotcore/__init__.py
index a8bd9a6..4cf6823 100644
--- a/zotcore/__init__.py
+++ b/zotcore/__init__.py
@@ -1,3 +1,3 @@
 """hermes-zotero core logic (standard library only, no Hermes imports)."""
 
-__version__ = "0.1.0"
+__version__ = "0.2.0"
```
<!-- /file -->

## Acceptance tests — `tests/test_14_release.py`

<!-- file: tests/test_14_release.py -->
```python
import re
import tomllib
from pathlib import Path

from zotcore import __version__, tools
from zotcore.frontmatter import is_true, split_front_matter
from zotcore.settings import Settings
from zotcore.textsource import build_passages

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "CORPUS.md"


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def fenced(text):
    return re.findall(r"^```markdown\n(.*?)\n```$", text, re.S | re.M)


def test_version_is_0_2_0_everywhere():
    assert __version__ == "0.2.0"
    assert re.search(r'^version: "0\.2\.0"$', read("plugin.yaml"), re.M)
    assert tomllib.loads(read("pyproject.toml"))["project"]["version"] == "0.2.0"
    assert re.search(r"^version: 0\.2\.0$", read("skills/zotero-library/SKILL.md"), re.M)


def test_readme_covers_the_new_features_and_links_the_guide():
    text = read("README.md")
    assert "(docs/CORPUS.md)" in text and GUIDE.is_file()
    for word in ("`in_tables`", "`mode` = `tables`", "`table`", "`ocr`", "`text_damaged`", "`index_outdated`", "Updating from 0.1.0"):
        assert word in text, word
    specs = {s.name: s for s in tools.tool_specs(lambda: Settings(), data_root=lambda: Path("unused"))}
    assert "in_tables" in specs["zotero_search"].schema["parameters"]["properties"]
    assert {"mode", "table"} <= set(specs["zotero_read"].schema["parameters"]["properties"])


def test_guide_states_the_spec():
    text = read("docs/CORPUS.md")
    assert text.startswith("# The Markdown corpus (spec v1)\n")
    for word in ("`markdown_path`", "`doi_<slug>.md`", "`K:<key>.md`", "200 bytes", "`spec`", "`ocr`", "`text_tool`", "`tables`",
                 "`## Tables (structured)`", "`### Table N`", "`in_tables`", "`text_damaged`", "`truncated`", "no converter"):
        assert word in text, word
    links = re.findall(r"\]\(([^)#]+)\)", text)
    assert links and all(link.startswith("https://") for link in links)


def test_the_guide_examples_work_with_the_plugin():
    blocks = fenced(read("docs/CORPUS.md"))
    header = next(b for b in blocks if b.startswith("---\n"))
    values, body = split_front_matter(header + "\n")
    assert values == {"spec": "1", "ocr": "true", "text_tool": "docling 2.94", "tables": "structured"}
    assert is_true(values["ocr"]) and body == "# Title of the paper\n"
    section = next(b for b in blocks if b.startswith("## Tables (structured)"))
    text, passages, tables = build_passages("# Paper\n\nBody text.\n\n" + section + "\n", "markdown")
    assert [(t.number, t.caption, t.rows, t.cols) for t in tables] == [(1, "Table 1. Baseline characteristics", 3, 3), (2, "", 2, 2)]
    assert "| Age (yr) | 59 ± 11 | 58 ± 11 |" in text and "| Leptin | high |" in text
    assert "It is not indexed" not in text and "<td>" not in text
    assert [p.kind for p in passages] == ["text", "table", "table"]


def test_guide_has_nothing_to_run():
    text = read("docs/CORPUS.md")
    assert not re.search(r"^```(?:bash|sh|shell|zsh|python|console)\b", text, re.M)
    assert "$(" not in text and "!`" not in text and "\t" not in text
```
<!-- /file -->

## Live check and release (Gábor, on the Mac; not for the executor)

Paste the outputs into `tasks/14-report.md` under `## Live check`, then commit that file (`task 14: live check`).

**1. Validate a clean clone, then push.**

```bash
cd ~/Developer/hermes-zotero
git status --short
CLONE="$(mktemp -d)/hermes-zotero"
git clone --quiet . "$CLONE"
hermes plugins validate "$CLONE"
git push
git rev-parse HEAD
```

Expected: `git status` prints nothing (all committed); the validation ends with `Validation passed.` and the line `security scan — safe`; the last line is the 40-character ID of the release commit. Keep that ID: the catalog entry needs it. If the scan says anything other than `safe`, do not push; bring the output to the review session.

**2. Update the demo profile from GitHub and try it as a stranger would.** The profile `zdemo` has the plugin installed from GitHub at 0.1.0.

```bash
hermes -p zdemo plugins update hermes-zotero
hermes -p zdemo zotero doctor
time hermes -p zdemo zotero sync
hermes -p zdemo -z "Use my Zotero library: find a paper on ketogenic diets and insulin resistance and quote one sentence with its citation."
```

Expected: `doctor` prints `hermes-zotero 0.2.0`; the sync warns once that the index is rebuilt and finishes; the question is answered from the library with a citation. If `plugins update` is not the right command on your Hermes version, run `hermes plugins --help`, use the update or reinstall command it lists, and note which one worked.

**3. The catalog entry.** The catalog pins a commit, so 0.2.0 reaches catalog users only through a second pull request that changes the pin. The reviewer prepared it in `review/catalog/0.2.0/` (not committed): the new entry file, the PR text and step-by-step instructions. Do this after steps 1 and 2 pass, and after the review session has checked this task.

## Out of scope

Local tasks L1 (write `ocr: true` into the corpus files your own index marks as OCR, and make your pipeline write it for new files) and L2 (slim your own skills onto the new tools). They live in `review/local/` and are never committed.
