# Task 12 — Front matter of corpus files and the `ocr` flag

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code |
| Reasoning | **low** (two verbatim files and a three-line patch). Set it in the app's model picker before pasting the prompt. |
| Budget | ≤ 20 tool calls |
| Depends on | task 11 committed (184 tests pass) |
| Done when | `.venv/bin/python -m pytest` shows **214 passed** (184 old + 30 new), the checksums match, report committed |

## Goal

Corpus spec v1 (plan v4, section 3) lets a converter put a small header at the very top of a Markdown file:

```
---
spec: 1
ocr: true
text_tool: docling 2.14
tables: structured
---
# Title of the paper
```

After this task the plugin reads that header: `ocr: true` puts the flag `ocr` on the paper (in search hits, in reads and in the status counts), next to the existing `body_not_read`, `scanned_or_empty` and `truncated`. The header itself is neither indexed nor returned as text. Until now the OCR flag lived only in Gábor's own database and his skill looked it up with SQL for every citation.

## Facts

- None of Gábor's 18,331 corpus files has front matter today (checked 12 Nov). Each starts with `# <title>`, then `- **Key:** value` lines and a `---` rule further down. The parser therefore accepts a block only at the first character of the file, and only when its first line is a `key: value` pair; that rule in the header is never mistaken for it. Files without front matter stay valid and are read exactly as before.
- No YAML library: the plugin stays standard-library only. The parser reads top-level `key: value` lines; indented lines, list items and comments are skipped; unknown keys are kept and ignored; a block that does not close within 100 lines is not front matter.
- Only `ocr` is used in this release. `spec`, `text_tool` and `tables` are part of the spec for converters and other tools.
- A file's signature is its name, size and modification time, so adding front matter to a file makes the next sync re-index that one paper. Passage offsets do not move, because the header is cut off before the text is split.
- Front matter belongs to Markdown corpus files. In Zotero's own text cache a leading `---` block is plain text.

## Files

```
create  zotcore/frontmatter.py                    (verbatim, below)
create  tests/test_12_frontmatter.py              (verbatim, below)
replace skills/zotero-library/SKILL.md            (verbatim, below; one bullet added)
modify  zotcore/textsource.py                     (the patch below)
create  tasks/12-report.md
commit  tasks/12-front-matter-ocr.md, tasks/README.md   (added or updated by the reviewer; commit them as they are)
```

Do not touch any other file.

## Steps

1. Run `.venv/bin/python -m pytest` first: 184 passed.
2. From the repo root, run this. It writes the three verbatim files and puts the patch into the system's temporary folder, and prints a SHA-256 for each:

```python
import hashlib, pathlib, re, tempfile
md = pathlib.Path("tasks/12-front-matter-ocr.md").read_text(encoding="utf-8")
for name, body in re.findall(r"<!-- file: (\S+) -->\n```\w*\n(.*?)\n```\n<!-- /file -->", md, re.S):
    out = pathlib.Path(tempfile.gettempdir()) / "task12.patch" if name == "PATCH" else pathlib.Path(name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body + "\n", encoding="utf-8", newline="\n")
    print(hashlib.sha256(out.read_bytes()).hexdigest(), out)
```

3. Compare the printed checksums with the table below. A mismatch means the copy went wrong: stop and fix it, do not edit the files.
4. Apply the patch from the repo root: `git apply --check <path printed for the patch>`, then `git apply <the same path>`. If it does not apply, make the same change by hand; the tests decide.
5. Run `.venv/bin/python -m pytest`: 214 passed.
6. Fill in the report `tasks/12-report.md` (the template is in the project rules file) and make one commit: `task 12: front matter, ocr flag`.

### Checksums

| File | SHA-256 |
| --- | --- |
| `zotcore/frontmatter.py` | `5e70994d05738f63bc2b3777c7cbe21fc5dac561efbfc22785c167d780114068` |
| `tests/test_12_frontmatter.py` | `c7f8fdd0d0c1c53de1c51abc579ce2a388ab6cb51d22f3186841efe14d5fffb7` |
| `skills/zotero-library/SKILL.md` | `745321865b88b17cf0643693be870b4e61f1830aea03820145f224083df9c389` |
| the patch file | `c7bb1d25755c2a008924e45c032109a2eccaa52693601e992f2c432bdaaebec3` |
| `zotcore/textsource.py` after the patch | `9e9d3b30e874c4b918fc2b9885c1808c311f93f6173a3be3d1398b74e1a52c76` |

## Spec — `zotcore/frontmatter.py`

<!-- file: zotcore/frontmatter.py -->
```python
"""Front matter of a corpus file (Markdown corpus spec v1), read without a YAML library.

A block of 'key: value' lines between two '---' lines at the very top of the file:

    ---
    spec: 1
    ocr: true
    ---
    # Title of the paper
"""
from __future__ import annotations

import re

MAX_LINES = 100     # a block that does not close within this many lines is not front matter
_PAIR = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)[ \t]*:(?:[ \t]+(.*))?$")
_TRUE = frozenset(("true", "yes", "on", "1"))
_BOM = chr(0xFEFF)   # byte-order mark; written this way so that this file holds no invisible character


def _value(raw: str | None) -> str:
    value = (raw or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value.split(" #", 1)[0].strip()


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """(values, body). A text without front matter comes back as ({}, text).

    The block must start at the first character (a byte-order mark may precede it) and its first
    line must be a 'key: value' pair in the first column; a '---' anywhere else is an ordinary
    Markdown rule. Keys are lower-cased. Indented lines, list items and comments are skipped.
    """
    start = 1 if text.startswith(_BOM) else 0
    lines = text[start:].split("\n", MAX_LINES + 2)
    if len(lines) < 3 or lines[0].rstrip() != "---" or not _PAIR.match(lines[1].rstrip()):
        return {}, text
    values: dict[str, str] = {}
    pos = start + len(lines[0]) + 1
    for line in lines[1:MAX_LINES + 2]:
        pos += len(line) + 1
        stripped = line.rstrip()
        if stripped == "---":
            return values, text[pos:]
        pair = _PAIR.match(stripped)
        if pair:
            values.setdefault(pair.group(1).lower(), _value(pair.group(2)))
    return {}, text


def is_true(value: str | None) -> bool:
    """True for the YAML-style words true / yes / on / 1, in any letter case."""
    return (value or "").strip().lower() in _TRUE
```
<!-- /file -->

## Spec — the patch (`zotcore/textsource.py`)

`choose_text` splits the front matter off a Markdown file and sets the flag; nothing else changes.

<!-- file: PATCH -->
```diff
diff --git a/zotcore/textsource.py b/zotcore/textsource.py
index b243b0b..88bdfd6 100644
--- a/zotcore/textsource.py
+++ b/zotcore/textsource.py
@@ -6,6 +6,7 @@ import re
 from dataclasses import dataclass
 from pathlib import Path
 
+from .frontmatter import is_true, split_front_matter
 from .tables import Table, prepare
 from .zdb import normalize_doi
 
@@ -146,7 +147,9 @@ def choose_text(item, data_dir, corpus=None) -> TextResult:
     """Best available text: Markdown, then Zotero's cache, then title and abstract."""
     source, path, att, signature = _select(item, data_dir, corpus)
     if source == "markdown":
-        return TextResult("markdown", _read(path), str(path), (), signature)
+        values, body = split_front_matter(_read(path))
+        flags = ("ocr",) if is_true(values.get("ocr")) else ()
+        return TextResult("markdown", body, str(path), flags, signature)
     if source == "ft-cache":
         flags: tuple[str, ...] = ()
         if (att.indexed_pages is not None and att.total_pages is not None
```
<!-- /file -->

## Spec — `skills/zotero-library/SKILL.md`

Reviewer-written; replace the file with this, byte for byte.

<!-- file: skills/zotero-library/SKILL.md -->
```markdown
---
name: zotero-library
description: "Research questions: check the user's Zotero library first"
version: 0.2.0
metadata:
  hermes:
    tags: [zotero, literature, research, citations, local-first]
---

# Zotero library first

The hermes-zotero plugin keeps a local, read-only index of the user's Zotero library. For any question about scientific or scholarly literature, a specific paper, or the user's own highlights and notes, search the library before the web. The tools never change Zotero.

## Search

1. Call `zotero_search` with 2-4 distinctive keywords, not a sentence: `SCD1 ferroptosis`, not "what does SCD1 do in ferroptosis". Use scientific names, not brand names (`tirzepatide`, not Mounjaro). A hit with `match: all` has one passage holding every word; `match: any` hits hold only some of them and are weaker evidence.
2. Check `terms` in the result: stop words and words like the "a" in Lp(a) are dropped. If the distinctive word is missing, rephrase.
3. When the user names a collection, tag, year range or group, pass `collection`, `tag`, `year_from`, `year_to` or `library`. Filters also narrow the coverage counts, so judge gaps from a search without them. To check one paper, pass `doi` and read `doi_check.held`.
4. Let `coverage.verdict` decide where to look:
   - `strong`: answer from the library.
   - `thin`: answer from the library, then use the web only for what is missing, and say which sources came from where.
   - `none` with a `hint`: no passage holds every word. Retry with fewer or broader words before treating it as a gap.
   - `none` without a hint: the library has nothing on this. Say so, then use the web.

## Read before citing

A snippet is a search hit, not evidence. For the 3-5 best papers, call `zotero_read` with `key` and `query`: it starts at the best-matching passage. Page on with `offset` set to `next_offset` when the methods or results come later. Ask for what the question needs (`max_chars` 1500-4000), never a whole paper.

- Cite with the `citation` field. `approximate: true` means it was built from the index, not by Zotero: check the details before giving a formatted reference.
- Flags `body_not_read` or `scanned_or_empty` mean the paper's body text is not in the index (metadata only); `truncated` means Zotero extracted only the first pages. Do not report results you have not read.
- Flag `ocr`: the text was read from a scan, so digits and symbols may be wrong. Say so when you quote numbers from it.
- `mode` = `annotations` returns the user's highlights, comments and notes on the paper. `author: user` marks the user's own words; quote them as theirs. Any other author is a group member or the PDF's creator.

## Numbers and tables

For numbers (baseline values, effect sizes, doses), use the papers' tables, which are kept as pipe rows:

- `zotero_search` with `in_tables` = true searches table cells only. Its coverage then counts tables only: never judge a gap from it.
- A passage with `kind: table` names its `table`. `zotero_read` with `mode` = `tables` and that `table` returns the whole table; without `table` it lists the paper's tables.
- Cells are the PDF's own strings, and a long table comes in pieces that repeat the header. Check the header and the units before quoting a number.

## Keep the index fresh

- Error `no_index`: ask the user to run `hermes zotero sync` once in a terminal. A large library takes a few minutes.
- Error `index_outdated` (after a plugin update): call `zotero_sync` until it returns `done: true`.
- `zotero_status` says whether the index is `ready` and gives a `hint` when Zotero has changed since the last sync.
- When the user has added papers, or the hint says so, call `zotero_sync`. While it returns `done: false`, call it again.

## Limits

- Use these tools, not other ways of opening Zotero's database or the plugin's index.
- Quote short passages with their citation; do not paste whole papers into the answer.
```
<!-- /file -->

## Acceptance tests — `tests/test_12_frontmatter.py`

<!-- file: tests/test_12_frontmatter.py -->
```python
import json
import re
from pathlib import Path

import pytest

from tests.zfixture import ZoteroFixture
from zotcore import tools
from zotcore.frontmatter import is_true, split_front_matter
from zotcore.index import Index, sync
from zotcore.settings import Settings
from zotcore.textsource import MarkdownCorpus, choose_text
from zotcore.zdb import load_items, open_snapshot

ROOT = Path(__file__).resolve().parents[1]
BODY = ("# Fasting and nitrogen excretion\n\n- **Authors:** Smith, J.\n- **Year:** 1963\n\n**Abstract:** Old scan.\n\n---\n\n"
        "## Results\n\nNitrogen excretion fell from 12.0 to 8.4 g per day during the fast.\n\n" * 3)
FM = "---\nspec: 1\nocr: true\ntext_tool: docling 2.14\ntables: structured\n---\n"


# ---------- the parser ----------------------------------------------------------------------------------

def test_front_matter_is_split_from_the_body():
    values, body = split_front_matter(FM + BODY)
    assert values == {"spec": "1", "ocr": "true", "text_tool": "docling 2.14", "tables": "structured"}
    assert body == BODY


@pytest.mark.parametrize("text", [
    BODY,                                             # the header's own '---' rule is not a fence
    "\n" + FM + BODY,                                 # not at the very top
    " ---\nocr: true\n---\n" + BODY,
    "---\n\nocr: true\n---\n" + BODY,                 # the first line must be a pair
    "---\nJust a rule, then prose.\n---\n" + BODY,
    "---\n---\n" + BODY,
    "---\nocr: true\n" + BODY.replace("---", "***"),  # never closed
    "---\nocr: true\n" + "x: 1\n" * 100 + "---\n" + BODY,   # closes too late
    "----\nocr: true\n----\n" + BODY,
    "---",
    "",
])
def test_text_without_front_matter_is_returned_whole(text):
    assert split_front_matter(text) == ({}, text)


def test_values_quotes_comments_and_odd_lines():
    text = (chr(0xFEFF) + "---  \r\nOCR: \"Yes\"\r\nspec :  1   # corpus spec\r\n# a comment\r\n\r\ntext_tool: 'my tool: v2 #3'\r\n"
            "authors:\r\n  - A. One\r\n  - B. Two\r\n  nested: 5\r\nocr: false\r\nempty:\r\nurl: https://example.org/a#b\r\n---\r\nBody\r\n---\r\n")
    values, body = split_front_matter(text)
    assert values == {"ocr": "Yes", "spec": "1", "text_tool": "my tool: v2 #3", "authors": "", "empty": "",
                      "url": "https://example.org/a#b"}       # the first 'ocr' wins; indented lines are skipped
    assert body == "Body\r\n---\r\n"
    assert split_front_matter("---\nocr: true\n---") == ({"ocr": "true"}, "")
    assert split_front_matter("---\na: 1\n" + "b: 2\n" * 99 + "---\nBody") == ({"a": "1", "b": "2"}, "Body")


@pytest.mark.parametrize("value, expected", [
    ("true", True), ("True", True), (" YES ", True), ("on", True), ("1", True),
    ("false", False), ("no", False), ("0", False), ("", False), (None, False), ("maybe", False), ("truely", False),
])
def test_is_true(value, expected):
    assert is_true(value) is expected


# ---------- through the index -------------------------------------------------------------------------

def make_library(tmp):
    z = ZoteroFixture(tmp / "Zotero")
    md = tmp / "md"
    md.mkdir()
    papers = {"OCRPAPER": ("10.1000/ocr.1", FM + BODY), "PLAINMD1": ("10.1000/plain.1", BODY),
              "NOTOCR01": ("10.1000/not.1", "---\nspec: 1\nocr: false\n---\n" + BODY),
              "TABOCR01": ("10.1000/tab.1", FM + BODY + "## Tables (structured)\n\nNote.\n\n### Table 1\n\n<table>\n"
                           "<tr><th>Hours</th><th>Nitrogen, g</th></tr>\n<tr><td>24</td><td>12.0</td></tr>\n</table>\n")}
    for key, (doi, text) in papers.items():
        i = z.add_item(key, fields={"title": f"Paper {key}", "DOI": doi, "date": "1963-00-00 1963"})
        z.add_attachment(i, "PDF" + key[:5])
        (md / ("doi_" + doi.replace("/", "_") + ".md")).write_text(text, encoding="utf-8")
    i = z.add_item("CACHE001", fields={"title": "Cache paper"})
    z.add_attachment(i, "PDFCACHE", ft_text="---\nocr: true\n---\nNitrogen in Zotero's own text cache.\n" * 8)
    return z, md


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lib12")
    z, md = make_library(tmp)
    root = tmp / "pd"
    index = Index(root / "index.sqlite")
    assert sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md)).indexed == 5
    index.close()
    z.close()
    return root


def handlers(root):
    settings = Settings()
    specs = {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root)}
    return specs["zotero_search"].handler, specs["zotero_read"].handler, specs["zotero_status"].handler


def call(handler, **args):
    return json.loads(handler(args))


def test_choose_text_drops_front_matter_and_sets_the_flag(tmp_path):
    z, md = make_library(tmp_path)
    con = open_snapshot(z.db_path)
    try:
        ids = [r[0] for r in z.con.execute("SELECT itemID FROM items WHERE key IN ('OCRPAPER', 'PLAINMD1', 'NOTOCR01', 'CACHE001')")]
        items = {item.key: item for item in load_items(con, ids)}
        corpus = MarkdownCorpus(md)
        ocr = choose_text(items["OCRPAPER"], z.data_dir, corpus)
        assert (ocr.source, ocr.text, ocr.flags) == ("markdown", BODY, ("ocr",))
        for key in ("PLAINMD1", "NOTOCR01"):
            result = choose_text(items[key], z.data_dir, corpus)
            assert (result.source, result.text, result.flags) == ("markdown", BODY, ())
        cache = choose_text(items["CACHE001"], z.data_dir, corpus)   # front matter belongs to Markdown files only
        assert cache.source == "ft-cache" and cache.flags == () and cache.text.startswith("---\nocr: true\n---\n")
    finally:
        con.close()
        z.close()


def test_flag_is_on_hits_reads_and_status(lib):
    search, read, status = handlers(lib)
    hits = {h["key"]: h for h in call(search, query="nitrogen excretion")["hits"] if h["match"] == "all"}
    assert set(hits) == {"OCRPAPER", "PLAINMD1", "NOTOCR01", "TABOCR01"}
    assert hits["OCRPAPER"]["flags"] == ["ocr"] and hits["TABOCR01"]["flags"] == ["ocr"]
    assert "flags" not in hits["PLAINMD1"] and "flags" not in hits["NOTOCR01"]
    data = call(read, key="OCRPAPER", max_chars=12000)
    assert data["flags"] == ["ocr"] and data["text"] == BODY and data["total_chars"] == len(BODY)
    assert call(read, key="PLAINMD1", max_chars=12000)["flags"] == []
    assert call(read, key="CACHE001")["flags"] == []
    table = call(read, key="TABOCR01", mode="tables", table=1)
    assert table["flags"] == ["ocr"] and table["text"] == "### Table 1\n| Hours | Nitrogen, g |\n| --- | --- |\n| 24 | 12.0 |\n"
    assert call(status)["index"]["flags"] == {"ocr": 2}


def test_front_matter_is_not_searchable(lib):
    search, read, _ = handlers(lib)
    assert call(search, query="docling")["hits"] == [] and call(search, query="structured")["hits"] == []
    assert [h["key"] for h in call(search, query="spec ocr")["hits"]] == ["CACHE001"]  # only where it is plain text
    assert "spec: 1" not in call(read, key="TABOCR01", max_chars=12000)["text"]


def test_adding_front_matter_to_a_file_reindexes_only_that_paper(tmp_path):
    z, md = make_library(tmp_path)
    index = Index(tmp_path / "pd" / "index.sqlite")
    try:
        assert sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md)).indexed == 5
        before = index.con.execute("SELECT n_passages, flags FROM items WHERE item_key = 'PLAINMD1'").fetchone()
        assert json.loads(before[1]) == []
        (md / "doi_10.1000_plain.1.md").write_text("---\nspec: 1\nocr: true\n---\n" + BODY, encoding="utf-8")
        rep = sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md))
        assert (rep.indexed, rep.deleted) == (1, 0)
        after = index.con.execute("SELECT n_passages, flags FROM items WHERE item_key = 'PLAINMD1'").fetchone()
        assert after[0] == before[0] and json.loads(after[1]) == ["ocr"]
        offsets = [r[0] for r in index.con.execute("SELECT start FROM passages WHERE item_key = 'PLAINMD1' ORDER BY rowid")]
        same = [r[0] for r in index.con.execute("SELECT start FROM passages WHERE item_key = 'OCRPAPER' ORDER BY rowid")]
        assert offsets == same and offsets[0] == 0
    finally:
        index.close()
        z.close()


def test_skill_explains_the_ocr_flag():
    text = (ROOT / "skills" / "zotero-library" / "SKILL.md").read_text(encoding="utf-8")
    assert "`ocr`" in text and re.search(r"`ocr`[^\n]*numbers", text) and len(text) <= 4000
```
<!-- /file -->

## Live check (Gábor; not for the executor)

Nothing to run now: no file in your corpus has front matter yet, so no paper gets the flag and nothing is re-indexed. The real check is part of local task L1, which writes `ocr: true` into the 360 files your own index marks as OCR and then confirms the flag through `zotero_search` and `zotero_read`. If you want a quick sanity check after the commit:

```bash
cd ~/Developer/hermes-zotero && hermes zotero sync && hermes gateway restart
```

Expected: a normal incremental sync (a few seconds, `indexed` near 0) and no `ocr` among the flags in the last line.

## Out of scope

Writing front matter into corpus files (local task L1; no converter is part of this plugin). The damaged-text flag (task 13). README and the corpus guide (task 14).
