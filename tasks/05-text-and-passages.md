# Task 05 — Pick each item's text and split it into passages

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code |
| Reasoning | **low**: the rules are fully listed; rerun at **medium** if BLOCKED |
| Budget | ≤ 40 tool calls |
| Depends on | task 04 committed |
| Done when | `.venv/bin/python -m pytest` shows **73 passed** (62 old + 11 new), checksums match, report committed |

## Goal

For every item, choose the best available text: Gábor's converted Markdown first, then Zotero's own text cache, then the title and abstract. Flag items whose PDF text could not be read. Split the text into passages of at most 2,000 characters, which later become the search results.

## Facts (verified on Gábor's machine, 5 Nov 2026)

- The Markdown corpus (setting `markdown_path`, e.g. `~/Zotero-Markdown`) keeps one paper per file in a `library/` subfolder. Use `<markdown_path>/library` if it exists, otherwise `<markdown_path>` itself, without recursing. Two naming schemes exist:
  - `doi_<slug>.md` (17,984 files): the slug is the normalized DOI with every run of characters outside `[a-z0-9.-]` replaced by `_`, and `_` stripped from both ends. Some stems still carry a URL prefix (`https_doi.org_`, `http_doi.org_`, `https_dx.doi.org_`, `http_dx.doi.org_`); strip it.
  - `K:<KEY>.md` (331 files): `KEY` is the Zotero key of the item **or of one of its attachments**.
  - With these rules, 18,336 of 19,290 items find their Markdown file.
- Zotero's text cache is `<data_dir>/storage/<attachment key>/.zotero-ft-cache`. It is plain UTF-8 text with no headings and no page markers; 22,148 exist.
- Reference timings: picking the source for all 19,290 items took 0.9 s (file stats only); splitting averaged about 1 ms per paper.

## Files

```
create  zotcore/textsource.py
create  tests/test_05_textsource.py   (verbatim, below)
create  tasks/05-report.md
```

## Spec — `zotcore/textsource.py`

```python
MIN_BYTES = 200                     # smaller files count as unusable
STORED_LINK_MODES = (0, 1)

@dataclass(frozen=True)
class TextResult:
    source: str          # "markdown" | "ft-cache" | "metadata"
    text: str
    path: str | None     # the file read, or None for metadata
    flags: tuple[str, ...]
    signature: str       # see text_signature

@dataclass(frozen=True)
class Passage:
    section: str; start: int; end: int; text: str     # text == full_text[start:end]

def doi_slug(doi: str) -> str
class MarkdownCorpus:
    def __init__(self, root): ...       # root may be None, "", missing: then the corpus is empty
    def __len__(self) -> int: ...       # number of usable files found
    def find(self, item) -> Path | None: ...
def ft_cache_path(data_dir, attachment) -> Path
def text_signature(item, data_dir, corpus=None) -> str
def choose_text(item, data_dir, corpus=None) -> TextResult
def split_passages(text: str, source: str, *, window: int = 2000, overlap: int = 200) -> list[Passage]
```

Rules:

1. `MarkdownCorpus` expands a leading `~` in `root` (`os.path.expanduser`), then scans the folder once with `os.scandir` (fast on 18,000 files). It keeps `.md` files only: `K:` stems in an upper-cased key map, `doi_` stems (URL prefix removed, lower-cased) in a slug map. The first file wins on duplicates. `find(item)` tries `doi_slug(item.doi)`, then `item.key`, then each attachment key.
2. Selection, shared by `choose_text` and `text_signature`, uses **file stats only**:
   1. The Markdown file, if found and at least `MIN_BYTES` bytes.
   2. Otherwise the stored attachments (`link_mode` 0 or 1): PDFs (`application/pdf`) first, then the others, each group in attachment order. The first whose cache file exists and is at least `MIN_BYTES` bytes wins. Link-only attachments (`link_mode` 3) never count.
   3. Otherwise metadata.
3. `choose_text` reads the chosen file as UTF-8 with `errors="replace"`.
   - Markdown → flags `()`.
   - ft-cache → flags `("truncated",)` when the attachment's `indexed_pages` and `total_pages` are both set and `indexed_pages < total_pages`, else `()`.
   - Metadata → text = title and abstract joined by a blank line (skip empty parts), `path=None`, flags `("body_not_read",)`, plus `"scanned_or_empty"` when the item has any stored PDF attachment.
4. `text_signature` must never read file contents, only stat them; a test enforces this. It changes whenever the chosen text would change:
   - Markdown → `markdown:<file name>:<size>:<mtime_ns>`
   - ft-cache → `ft-cache:<attachment key>:<size>:<mtime_ns>`
   - Metadata → `metadata:` followed by `<key>:<cache size or -1>` for each stored attachment checked, joined with `|`.

   `choose_text(...).signature` must equal `text_signature(...)` for the same state.
5. `split_passages`:
   - Empty or whitespace-only text → `[]`.
   - `metadata` → one passage, section `"metadata"`, covering the whole text.
   - `markdown` → sections start at lines matching `^#{1,6}\s+(.*)$`. The section name is the heading text, stripped; text before the first heading is section `""`. Each section is windowed (rule 6); offsets refer to the whole text.
   - `ft-cache` (and anything else) → the whole text is windowed with section `""`.
6. Windowing within `[s, e)`: a piece is at most `window` characters. When the piece would end before `e`, cut **after** the last `"\n\n"` that lies inside the last 30% of the window (the cut point is just after the blank line). Failing that, cut after the last `"\n"` in that zone; failing that, cut at the window length. The next piece starts `overlap` characters before the cut, and always strictly after the previous start. Whitespace-only pieces are dropped. The result is deterministic.

## Acceptance tests (copy verbatim, then verify checksums)

| File | SHA-256 |
| --- | --- |
| `tests/test_05_textsource.py` | `cbaf17693d4011662660be1f5330bb0c3c69108b2c49cbab4ce450c499a341ac` |

### `tests/test_05_textsource.py`

```python
import os

import pytest

from tests.zfixture import ZoteroFixture
from zotcore.textsource import (MarkdownCorpus, Passage, TextResult, choose_text, doi_slug,
                                ft_cache_path, split_passages, text_signature)
from zotcore.zdb import list_items, load_items, open_snapshot

BODY = "Ferroptosis is an iron-dependent form of cell death.\n\n" * 20  # ~1,000 characters


def load(z, key):
    con = open_snapshot(z.db_path)
    ref = {r.key: r for r in list_items(con, ["user"])}[key]
    (item,) = load_items(con, [ref.item_id])
    con.close()
    return item


@pytest.fixture
def z(tmp_path):
    fx = ZoteroFixture(tmp_path / "Zotero")
    yield fx
    fx.close()


def write_md(root, name, text=BODY):
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def test_doi_slug_matches_the_corpus_file_names():
    assert doi_slug("10.1001/archinte.160.21.3265") == "10.1001_archinte.160.21.3265"
    assert doi_slug("10.1002/(sici)1096-8644(1998)107:27<177::aid-ajpa7>3.0.co;2-b") == \
        "10.1002_sici_1096-8644_1998_107_27_177_aid-ajpa7_3.0.co_2-b"
    assert doi_slug("10.1016/0002-9343(87)90058-1") == "10.1016_0002-9343_87_90058-1"
    assert doi_slug("") == ""


def test_corpus_finds_files_by_doi_item_key_and_attachment_key(z, tmp_path):
    art = z.add_item("ART00001", fields={"title": "A", "DOI": "10.1001/ARCHINTE.160.21.3265"})
    sici = z.add_item("ART00002", fields={"title": "B", "DOI": "10.1002/(SICI)1096-8644(1998)107:27<177::AID-AJPA7>3.0.CO;2-B"})
    url = z.add_item("ART00003", fields={"title": "C", "DOI": "10.1002/oby.20932"})
    bykey = z.add_item("ART00004", fields={"title": "D"})
    byatt = z.add_item("ART00005", fields={"title": "E"})
    z.add_attachment(byatt, "ATT00005")
    none = z.add_item("ART00006", fields={"title": "F", "DOI": "10.9/nothing"})
    lib = tmp_path / "md" / "library"
    write_md(lib, "doi_10.1001_archinte.160.21.3265.md")
    write_md(lib, "doi_10.1002_sici_1096-8644_1998_107_27_177_aid-ajpa7_3.0.co_2-b.md")
    write_md(lib, "doi_https_doi.org_10.1002_oby.20932.md")  # a DOI that was stored as a URL
    write_md(lib, "K:ART00004.md")
    write_md(lib, "K:ATT00005.md")
    write_md(lib, "notes.txt")
    corpus = MarkdownCorpus(tmp_path / "md")  # uses md/library/ when it exists
    assert len(corpus) == 5
    assert corpus.find(load(z, "ART00001")).name == "doi_10.1001_archinte.160.21.3265.md"
    assert corpus.find(load(z, "ART00002")) is not None
    assert corpus.find(load(z, "ART00003")).name == "doi_https_doi.org_10.1002_oby.20932.md"
    assert corpus.find(load(z, "ART00004")).name == "K:ART00004.md"
    assert corpus.find(load(z, "ART00005")).name == "K:ATT00005.md"
    assert corpus.find(load(z, "ART00006")) is None


def test_corpus_flat_folder_and_missing_folder(z, tmp_path):
    z.add_item("ART00001", fields={"title": "A", "DOI": "10.1/x"})
    write_md(tmp_path / "flat", "doi_10.1_x.md")
    assert MarkdownCorpus(tmp_path / "flat").find(load(z, "ART00001")) is not None
    assert len(MarkdownCorpus(tmp_path / "does-not-exist")) == 0
    assert len(MarkdownCorpus("")) == 0 and len(MarkdownCorpus(None)) == 0


def test_markdown_beats_ft_cache_beats_metadata(z, tmp_path):
    iid = z.add_item("ART00001", fields={"title": "T", "DOI": "10.1/x", "abstractNote": "Abstract."})
    z.add_attachment(iid, "PDF00001", ft_text="cache text " * 50)
    write_md(tmp_path / "md", "doi_10.1_x.md")
    item = load(z, "ART00001")
    r = choose_text(item, z.data_dir, MarkdownCorpus(tmp_path / "md"))
    assert isinstance(r, TextResult)
    assert (r.source, r.flags) == ("markdown", ())
    assert r.text == BODY and r.path.endswith("doi_10.1_x.md")
    r = choose_text(item, z.data_dir, None)
    assert r.source == "ft-cache" and r.text.startswith("cache text")
    assert r.path == str(ft_cache_path(z.data_dir, item.attachments[0]))


def test_ft_cache_rules(z):
    iid = z.add_item("ART00001", fields={"title": "T"})
    z.add_attachment(iid, "HTM00001", content_type="text/html", link_mode=1, ft_text="html text " * 50)
    z.add_attachment(iid, "TINY0001", ft_text="too short")  # under 200 bytes: not usable
    z.add_attachment(iid, "PDF00002", ft_text="pdf text " * 50, indexed_pages=100, total_pages=140)
    z.add_attachment(iid, "LNK00001", link_mode=3, content_type="application/pdf", ft_text="linked url " * 50)
    r = choose_text(load(z, "ART00001"), z.data_dir)
    assert r.source == "ft-cache"
    assert r.text.startswith("pdf text")  # stored PDFs first, in attachment order, skipping unusable ones
    assert r.flags == ("truncated",)  # Zotero indexed only 100 of 140 pages


def test_metadata_fallback_and_flags(z):
    a = z.add_item("ART00001", fields={"title": "Scanned paper", "abstractNote": "Only an abstract."})
    z.add_attachment(a, "PDF00001")  # a stored PDF without any text cache
    b = z.add_item("ART00002", fields={"title": "Web page only"})
    z.add_attachment(b, "HTM00001", content_type="text/html", link_mode=1)
    z.add_item("ART00003", fields={"title": "No attachments"})
    r = choose_text(load(z, "ART00001"), z.data_dir)
    assert r.source == "metadata" and r.path is None
    assert r.text == "Scanned paper\n\nOnly an abstract."
    assert r.flags == ("body_not_read", "scanned_or_empty")
    assert choose_text(load(z, "ART00002"), z.data_dir).flags == ("body_not_read",)
    assert choose_text(load(z, "ART00003"), z.data_dir).flags == ("body_not_read",)


def test_signature_tracks_the_chosen_text(z, tmp_path):
    iid = z.add_item("ART00001", fields={"title": "T", "DOI": "10.1/x"})
    z.add_attachment(iid, "PDF00001")
    item = load(z, "ART00001")
    s0 = text_signature(item, z.data_dir)
    assert s0 == text_signature(item, z.data_dir)  # stable
    assert choose_text(item, z.data_dir).signature == s0
    z.write_ft_cache("PDF00001", "now Zotero has indexed the PDF " * 20)
    s1 = text_signature(item, z.data_dir)
    assert s1 != s0  # the cache appeared
    cache = z.data_dir / "storage" / "PDF00001" / ".zotero-ft-cache"
    st = cache.stat()
    cache.write_text("re-indexed with more text " * 40, encoding="utf-8")
    os.utime(cache, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))
    s2 = text_signature(item, z.data_dir)
    assert s2 != s1  # the cache changed
    write_md(tmp_path / "md", "doi_10.1_x.md")
    assert text_signature(item, z.data_dir, MarkdownCorpus(tmp_path / "md")) != s2  # Markdown now wins


def test_signature_reads_no_file_contents(z, monkeypatch):
    iid = z.add_item("ART00001", fields={"title": "T"})
    z.add_attachment(iid, "PDF00001", ft_text="x" * 500)
    item = load(z, "ART00001")
    import pathlib

    def boom(*a, **k):
        raise AssertionError("text_signature must only stat files")
    monkeypatch.setattr(pathlib.Path, "read_text", boom)
    monkeypatch.setattr(pathlib.Path, "read_bytes", boom)
    assert text_signature(item, z.data_dir).startswith("ft-cache:")


def test_split_ft_cache_windows():
    text = "".join(f"Paragraph {n}. " + "word " * 60 + "\n\n" for n in range(60))  # ~19,000 chars
    ps = split_passages(text, "ft-cache")
    assert ps and all(isinstance(p, Passage) for p in ps)
    assert all(len(p.text) <= 2000 for p in ps)
    assert all(p.text == text[p.start:p.end] for p in ps)
    assert ps[0].start == 0 and ps[-1].end == len(text)
    for a, b in zip(ps, ps[1:]):
        assert b.start <= a.end  # no gaps
        assert a.end - b.start <= 200  # overlap at most 200 characters
        assert b.start > a.start
    assert all(p.text.endswith("\n\n") or p is ps[-1] for p in ps)  # cut at paragraph breaks
    assert split_passages(text, "ft-cache") == ps  # deterministic


def test_split_markdown_by_headings():
    text = ("# Title of paper\n\n- **Authors:** A, B\n\n---\n\nIntro text.\n\n"
            "## Methods\n\n" + "Method detail. " * 300 + "\n\n## Results\n\nSCD1 knockdown increased lipid peroxidation.\n")
    ps = split_passages(text, "markdown")
    sections = [p.section for p in ps]
    assert sections[0] == "Title of paper"
    assert "Methods" in sections and sections[-1] == "Results"
    assert sum(1 for s in sections if s == "Methods") >= 3  # a long section is windowed
    assert all(len(p.text) <= 2000 and p.text == text[p.start:p.end] for p in ps)
    assert "lipid peroxidation" in ps[-1].text


def test_split_preamble_metadata_and_empty():
    ps = split_passages("Preamble without heading.\n\n# H\n\nBody.", "markdown")
    assert [p.section for p in ps] == ["", "H"]
    assert split_passages("Title\n\nAbstract.", "metadata") == [Passage("metadata", 0, 16, "Title\n\nAbstract.")]
    assert split_passages("", "ft-cache") == [] and split_passages("  \n ", "markdown") == []
```


## Commands

```bash
.venv/bin/python -m pytest                     # expect: 73 passed
shasum -a 256 tests/test_05_textsource.py
```

No live check; task 06 exercises this on the real folders.

## Out of scope

OCR, PDF parsing, reading the database, the index.
