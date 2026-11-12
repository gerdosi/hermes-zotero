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
