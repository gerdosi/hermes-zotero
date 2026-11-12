import json
import re
import sqlite3
from pathlib import Path

import pytest

from tests.zfixture import ZoteroFixture
from zotcore import tools
from zotcore.index import SCHEMA_VERSION, Index, sync
from zotcore.settings import Settings
from zotcore.tables import prepare
from zotcore.textsource import MarkdownCorpus, build_passages, split_passages

ROOT = Path(__file__).resolve().parents[1]
NOTE = "Extracted from the PDF layout. These are the cell strings, not a paraphrase of the prose.\n\n"
HEAD = "# Paper\n\n- **Year:** 2020\n\n---\n\n## Results\n\nBody text about adiponectin in plasma.\n\n"
T1 = ("### Table 1\n\n<table>\n<tr><th></th><th>Women (n = 12)</th><th>Men</th></tr>\n"
      "<tr><td>Age (yr)</td><td>59 &plusmn; 11</td><td>58 &#177; 11</td></tr>\n"
      "<tr><td>P value</td><td>p &lt; 0.05</td><td></td></tr>\n"
      "<tr><td></td><td></td><td></td></tr>\n"
      "<tr><td>Ratio a|b</td><td>  1.5\n  (0.9) </td><td>n/a</td></tr>\n</table>\n\n")
T1_PIPES = ("### Table 1\n|  | Women (n = 12) | Men |\n| --- | --- | --- |\n| Age (yr) | 59 ± 11 | 58 ± 11 |\n"
            "| P value | p < 0.05 |\n| Ratio a\\|b | 1.5 (0.9) | n/a |\n")


def doc(*sections, head=HEAD, note=NOTE):
    return head + "## Tables (structured)\n\n" + note + "".join(sections)


def long_table(number=2, rows=60):
    body = "".join(f"<tr><td>Subject {n:03d}</td><td>glucose {n * 1.5:.1f} mmol/L</td><td>insulin {n} pmol/L</td></tr>\n"
                   for n in range(rows))
    return (f"### Table {number}\n\n<table>\n<tr><th>Subject</th><th>Fasting glucose</th><th>Fasting insulin</th></tr>\n"
            f"{body}</table>\n\n")


def data_rows(text):
    return [line for line in text.splitlines() if re.match(r"\| Subject \d", line)]


# ---------- prepare: HTML and pipe tables become pipe rows ---------------------------------------------

def test_html_table_becomes_pipe_rows():
    prep = prepare(doc(T1), "markdown")
    assert prep.text == HEAD + T1_PIPES + "\n"
    assert prep.body_end == len(HEAD) and prep.text[:prep.body_end] == HEAD
    assert "Tables (structured)" not in prep.text and "Extracted from the PDF" not in prep.text
    (table,) = prep.tables
    assert (table.number, table.caption, table.rows, table.cols) == (1, "", 4, 3)
    assert prep.text[table.start:table.end] == T1_PIPES
    (seg,) = prep.segments
    assert (seg.kind, seg.number, seg.start, seg.end) == ("table", 1, table.start, table.end)


def test_merged_cells_header_rows_and_inner_tags():
    html = ("### Table 3\nTable 3. Lipids by <b>sex</b>\n<TABLE class=\"x\">\n"
            "<tr><th rowspan=\"2\">Variable</th><th colspan=\"2\">Women</th><th colspan='2'>Men</th></tr>\n"
            "<tr><th></th><th>VAT</th><th>SAT</th><th>VAT</th><th>SAT</th></tr>\n"
            "<tr><td>BMI<sup>a</sup></td><td>0.61<br>0.70</td><td><i>0.83</i></td><td>0.5</td><td>0.6</td>\n"
            "<tr><td>LDL&nbsp;C<td>1<td>2</tr>\n</TABLE>\nValues are r.\n")
    prep = prepare(doc(html), "markdown")
    assert prep.text[prep.body_end:] == (
        "### Table 3\nTable 3. Lipids by <b>sex</b>\n"
        "| Variable | Women |  | Men |\n|  | VAT | SAT | VAT | SAT |\n| --- | --- | --- | --- | --- |\n"
        "| BMIa | 0.61 0.70 | 0.83 | 0.5 | 0.6 |\n| LDL C | 1 | 2 |\nValues are r.\n\n")
    (table,) = prep.tables
    assert (table.number, table.caption, table.rows, table.cols) == (3, "Table 3. Lipids by <b>sex</b>", 4, 5)


def test_pipe_table_in_the_tables_section():
    src = ("### Table 1\nBaseline values\n\n| Group | n | Note |\n|:---|---:|---|\n| Keto \\| low | 12 | |\n"
           "|Control|11|x|\n\n### Table 2\n| only | data |\n| 1 | 2 |\n")
    prep = prepare(doc(src), "markdown")
    assert prep.text[prep.body_end:] == (
        "### Table 1\nBaseline values\n| Group | n | Note |\n| --- | --- | --- |\n| Keto \\| low | 12 |\n"
        "| Control | 11 | x |\n\n### Table 2\n| only | data |\n| 1 | 2 |\n\n")
    assert [(t.number, t.caption, t.rows, t.cols) for t in prep.tables] == [(1, "Baseline values", 3, 3), (2, "", 2, 2)]


def test_long_table_is_cut_at_row_ends_and_repeats_the_header():
    prep = prepare(doc(T1, long_table()), "markdown", window=700)
    pieces = [prep.text[s.start:s.end] for s in prep.segments if s.number == 2]
    assert len(pieces) >= 5 and all(len(p) <= 700 for p in pieces)
    top = "| Subject | Fasting glucose | Fasting insulin |\n| --- | --- | --- |\n"
    assert pieces[0].startswith("### Table 2\n" + top)
    assert all(p.startswith("### Table 2 (continued)\n" + top) for p in pieces[1:])
    assert all(p.endswith("|\n") and "<t" not in p for p in pieces)
    rows = [row for p in pieces for row in data_rows(p)]
    assert rows == [f"| Subject {n:03d} | glucose {n * 1.5:.1f} mmol/L | insulin {n} pmol/L |" for n in range(60)]
    table = prep.tables[1]
    assert (table.number, table.rows, table.cols) == (2, 61, 3)
    assert table.start == prep.segments[1].start and table.end == prep.segments[-1].end
    assert [s.start for s in prep.segments[2:]] == [s.end + 1 for s in prep.segments[1:-1]]  # one blank line apart


def test_a_row_longer_than_the_window_stays_whole():
    wide = "x" * 900
    src = f"### Table 1\n<table><tr><th>A</th></tr><tr><td>one</td></tr><tr><td>{wide}</td></tr><tr><td>two</td></tr></table>\n"
    prep = prepare(doc(src), "markdown", window=300)
    pieces = [prep.text[s.start:s.end] for s in prep.segments]
    assert len(pieces) == 3 and f"| {wide} |\n" in pieces[1] and len(pieces[1]) > 300
    assert all("| A |\n| --- |\n" in p for p in pieces)


def test_a_huge_header_is_not_repeated():
    wide = "h" * 400
    rows = "".join(f"<tr><td>row {n} {'y' * 80}</td></tr>" for n in range(8))
    prep = prepare(doc(f"### Table 1\n<table><tr><th>{wide}</th></tr>{rows}</table>\n"), "markdown", window=500)
    pieces = [prep.text[s.start:s.end] for s in prep.segments]
    assert len(pieces) >= 2 and wide in pieces[0]
    assert all(wide not in p and p.startswith("### Table 1 (continued)\n| row ") for p in pieces[1:])


@pytest.mark.parametrize("text, source", [
    (HEAD + "| a | b |\n|---|---|\n| 1 | 2 |\n", "markdown"),                       # a pipe table in the body is text
    (HEAD + "## Tables (structured)\n\n" + NOTE, "markdown"),                       # marker without tables
    (doc(T1), "ft-cache"),                                                           # only Markdown has the section
    (HEAD.replace("## Results", "### Table 1") + "<table><tr><td>x</td></tr></table>\n", "markdown"),  # no marker
    ("", "markdown"),
])
def test_text_without_a_tables_section_is_left_alone(text, source):
    prep = prepare(text, source)
    assert prep.text == text and prep.body_end == len(text) and prep.segments == () and prep.tables == ()
    out, passages, tables = build_passages(text, source)
    assert out == text and tables == () and all(p.kind == "text" and p.table is None for p in passages)
    assert [(p.section, p.start, p.end, p.text) for p in passages] == \
        [(p.section, p.start, p.end, p.text) for p in split_passages(text, source)]


def test_sections_without_a_table_and_empty_tables():
    src = ("### Table 1\n\nSee the supplement for this table.\n\n"
           "### Table 2\n\n<table>\n<tr><th></th></tr>\n</table>\n\n"
           "### Table 3\n\n" + "### Table 4\n<table><tr><td>kept</td></tr></table>\n")
    prep = prepare(doc(src), "markdown")
    assert prep.text[prep.body_end:] == "### Table 1\n\nSee the supplement for this table.\n\n### Table 4\n| kept |\n\n"
    assert [(s.kind, s.number) for s in prep.segments] == [("text", 1), ("table", 4)]
    assert [(t.number, t.rows, t.cols) for t in prep.tables] == [(4, 1, 1)]


@pytest.mark.parametrize("junk", [
    "<table>", "<table><tr><td>open cell", "<table></table>", "<table><tr></tr></table>", "<td>stray</td>",
    "<table><tr><td colspan='x'>a</td><td colspan='0'>b</td><td colspan='999999'>c</td></tr></table>",
    "<table><tr><td><table><tr><td>inner</td></tr></table></td></tr></table>", "|", "|||", "| --- |", "\x00<table",
    "<table><tr><td>&bogus; &#xZZ; &amp;</td></tr>", "<table" + "<tr>" * 500,
])
def test_broken_markup_never_raises(junk):
    text = doc(f"### Table 1\n{junk}\n### Table 2\n<table><tr><td>fine</td></tr></table>\n")
    out, passages, tables = build_passages(text, "markdown")
    assert tables[-1].number == 2 and out.endswith("### Table 2\n| fine |\n\n")
    assert all(p.text == out[p.start:p.end] and p.text.strip() for p in passages)


def test_build_passages_marks_table_passages():
    text = doc(T1, long_table(), "### Table 3\n\nNot a table.\n")
    out, passages, tables = build_passages(text, "markdown", window=700, overlap=50)
    assert all(p.text == out[p.start:p.end] for p in passages)
    kinds = [(p.kind, p.table, p.section) for p in passages]
    assert kinds[:3] == [("text", None, "Paper"), ("text", None, "Results"), ("table", 1, "Table 1")]
    assert kinds[-1] == ("text", None, "Table 3") and set(kinds[3:-1]) == {("table", 2, "Table 2")}
    assert [t.number for t in tables] == [1, 2]
    assert not any("<td" in p.text or "Tables (structured)" in p.text for p in passages)
    assert out.count("| Subject 0") == 60


# ---------- index ---------------------------------------------------------------------------------------

V1_SCHEMA = (
    """CREATE TABLE items (library TEXT NOT NULL, item_key TEXT NOT NULL, item_id INTEGER, item_type TEXT, title TEXT,
  creators TEXT, year INTEGER, date TEXT, doi TEXT, publication TEXT, abstract TEXT, collections TEXT, tags TEXT,
  date_added TEXT, modified TEXT, text_source TEXT, text_path TEXT, flags TEXT, signature TEXT, n_passages INTEGER,
  PRIMARY KEY (library, item_key))""",
    "CREATE TABLE passage_map (rowid INTEGER PRIMARY KEY, library TEXT NOT NULL, item_key TEXT NOT NULL)",
    """CREATE VIRTUAL TABLE passages USING fts5(title, section, body, library UNINDEXED, item_key UNINDEXED,
  start UNINDEXED, end UNINDEXED, tokenize='porter unicode61 remove_diacritics 2')""",
    "CREATE TABLE state (key TEXT PRIMARY KEY, value TEXT)",
    "INSERT INTO state VALUES ('last_sync', '2026-11-06T12:00:00Z')",
    "INSERT INTO items (library, item_key, title, modified, signature, n_passages) VALUES ('user', 'OLDITEM1', 'Old', 'm', 's', 1)",
    "INSERT INTO passage_map (rowid, library, item_key) VALUES (1, 'user', 'OLDITEM1')",
    "INSERT INTO passages (rowid, title, section, body, library, item_key, start, \"end\") "
    "VALUES (1, 'Old', '', 'stale words from version one', 'user', 'OLDITEM1', 0, 28)",
)


def make_library(tmp):
    z = ZoteroFixture(tmp / "Zotero")
    md = tmp / "md"
    md.mkdir()
    i = z.add_item("TABLES01", fields={"title": "Adiponectin and visceral fat", "DOI": "10.1000/tab.1", "date": "2020-00-00 2020"},
                   creators=[("Ada", "Lovelace", "author")])
    z.add_attachment(i, "PDFTAB01", ft_text="cache text that loses to markdown " * 10)
    (md / "doi_10.1000_tab.1.md").write_text(doc(T1, long_table(), "### Table 3\n| Marker | Level |\n|---|---|\n| leptin | high |\n"),
                                             encoding="utf-8")
    i = z.add_item("PLAIN001", fields={"title": "Glucose without tables", "DOI": "10.1000/plain.1", "date": "2021-00-00 2021"})
    z.add_attachment(i, "PDFPLN01", ft_text="Fasting glucose and insulin were measured in plasma. td tr th.\n\n" * 6)
    for n in range(12):
        i = z.add_item(f"FILL00{n:02d}", fields={"title": f"Filler {n}", "date": "2019-00-00 2019"})
        z.add_attachment(i, f"PDFFL0{n:02d}", ft_text=f"Unrelated filler text number {n} about myokines.\n\n" * 4)
    return z, md


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lib11")
    z, md = make_library(tmp)
    root = tmp / "pd"
    index = Index(root / "index.sqlite")
    rep = sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md))
    assert rep.done and rep.indexed == 14
    index.close()
    z.close()
    return root


def handlers(root):
    settings = Settings()
    specs = {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root)}
    return specs["zotero_search"].handler, specs["zotero_read"].handler, specs["zotero_status"].handler


def call(handler, **args):
    out = handler(args)
    assert isinstance(out, str)
    return json.loads(out)


def test_index_stores_kinds_and_the_table_list(lib):
    con = sqlite3.connect(lib / "index.sqlite")
    try:
        assert con.execute("SELECT value FROM state WHERE key = 'schema'").fetchone() == (str(SCHEMA_VERSION),)
        kinds = con.execute("SELECT kind, table_no, COUNT(*) FROM passage_map WHERE item_key = 'TABLES01' "
                            "GROUP BY kind, table_no ORDER BY table_no").fetchall()
        assert kinds[0][:2] == ("text", None) and [k[:2] for k in kinds[1:]] == [("table", 1), ("table", 2), ("table", 3)]
        assert dict((k[1], k[2]) for k in kinds[1:])[2] >= 2  # the long table needs several passages
        assert con.execute("SELECT COUNT(*) FROM passage_map WHERE kind != 'text' AND item_key != 'TABLES01'").fetchone() == (0,)
        rows = con.execute('SELECT number, caption, n_rows, n_cols, "end" - start FROM item_tables ORDER BY start').fetchall()
        assert [r[:4] for r in rows] == [(1, "", 4, 3), (2, "", 61, 3), (3, "", 2, 2)] and all(r[4] > 0 for r in rows)
        bodies = [r[0] for r in con.execute("SELECT body FROM passages WHERE item_key = 'TABLES01'")]
        assert not any("<td" in b or "<tr" in b for b in bodies)
    finally:
        con.close()
    index = Index(lib / "index.sqlite")
    try:
        counts = index.counts()
        assert counts["schema"] == SCHEMA_VERSION >= 2 and counts["tables"] == 3 and counts["items"] == 14
    finally:
        index.close()


def test_resync_replaces_and_removes_table_rows(tmp_path):
    z, md = make_library(tmp_path)
    index = Index(tmp_path / "pd" / "index.sqlite")
    try:
        corpus = MarkdownCorpus(md)
        assert sync(index, z.db_path, z.data_dir, corpus=corpus).indexed == 14
        (md / "doi_10.1000_tab.1.md").write_text(doc(T1) + "\nA new line, so the file size changes.\n", encoding="utf-8")
        assert sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md)).indexed == 1
        assert index.con.execute("SELECT number FROM item_tables").fetchall() == [(1,)]
        assert index.con.execute("SELECT COUNT(*) FROM passage_map WHERE kind = 'table'").fetchone() == (1,)
        z.trash(z.con.execute("SELECT itemID FROM items WHERE key = 'TABLES01'").fetchone()[0])
        assert sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md)).deleted == 1
        assert index.counts()["tables"] == 0
    finally:
        index.close()
        z.close()


def test_an_index_from_version_1_is_rebuilt_by_sync(tmp_path):
    z, md = make_library(tmp_path)
    root = tmp_path / "pd"
    root.mkdir()
    con = sqlite3.connect(root / "index.sqlite")
    for statement in V1_SCHEMA:
        con.execute(statement)
    con.commit()
    con.close()
    search, read, status = handlers(root)

    data = call(status)
    assert data["ready"] is False and data["index"]["schema"] == 1 and data["index"]["items"] == 1
    assert "zotero_sync" in data["hint"] and "older version" in data["hint"]
    for data in (call(search, query="stale words"), call(read, key="OLDITEM1")):
        assert data["ok"] is False and data["error"]["code"] == "index_outdated" and "zotero_sync" in data["error"]["hint"]
    con = sqlite3.connect(root / "index.sqlite")  # looking at an old index never changes its contents
    assert con.execute("SELECT COUNT(*) FROM passage_map").fetchone() == (1,)
    assert con.execute("SELECT value FROM state WHERE key = 'schema'").fetchone() is None
    con.close()

    ticks = iter(range(0, 10_000, 10))
    index = Index(root / "index.sqlite")
    try:
        assert index.schema_version() == 1
        rep = sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md), batch_items=5, budget_seconds=5,
                   clock=lambda: next(ticks))
        assert rep.done is False and rep.indexed == 5 and rep.remaining == 9
        assert any("rebuilt" in w for w in rep.warnings)
        assert index.schema_version() == SCHEMA_VERSION and index.get_state("last_sync") is None
        assert index.con.execute("SELECT COUNT(*) FROM items WHERE item_key = 'OLDITEM1'").fetchone() == (0,)
    finally:
        index.close()
    data = call(status)
    assert data["ready"] is True and "still being built" in data["hint"] and "zotero_sync" in data["hint"]
    assert call(search, query="stale words")["hits"] == []

    index = Index(root / "index.sqlite")
    try:
        rep = sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md))
        assert rep.done and rep.indexed == 9 and not any("rebuilt" in w for w in rep.warnings)
    finally:
        index.close()
        z.close()
    data = call(status)
    assert data["ready"] is True and data["index"]["items"] == 14 and data["index"]["tables"] == 3
    assert "still being built" not in (data["hint"] or "")
    assert call(search, query="leptin", in_tables=True)["hits"][0]["key"] == "TABLES01"


# ---------- zotero_search -------------------------------------------------------------------------------

def test_table_hits_say_kind_and_table_number(lib):
    search, _, _ = handlers(lib)
    data = call(search, query="leptin")
    (hit,) = data["hits"]
    assert hit["key"] == "TABLES01" and hit["match"] == "all"
    passage = hit["passages"][0]
    assert passage["kind"] == "table" and passage["table"] == 3 and passage["section"] == "Table 3"
    assert "«leptin»" in passage["snippet"] and "<td" not in passage["snippet"]
    data = call(search, query="adiponectin plasma")
    passage = next(h for h in data["hits"] if h["key"] == "TABLES01")["passages"][0]
    assert "kind" not in passage and "table" not in passage and passage["section"] == "Results"


def test_in_tables_limits_hits_and_coverage(lib):
    search, _, _ = handlers(lib)
    everywhere = call(search, query="fasting glucose insulin")
    assert {h["key"] for h in everywhere["hits"]} == {"TABLES01", "PLAIN001"}
    assert everywhere["coverage"]["matches_all"] == 2 and "in_tables" not in everywhere["coverage"]
    for flag in (True, "true", "TRUE", 1, "yes"):
        data = call(search, query="fasting glucose insulin", in_tables=flag)
        assert [h["key"] for h in data["hits"]] == ["TABLES01"]
        assert all(p["kind"] == "table" and p["table"] == 2 for p in data["hits"][0]["passages"])
        cov = data["coverage"]
        assert cov["matches_all"] == 1 and cov["matches_any"] == 1 and cov["in_tables"] is True
        assert "without in_tables" in cov["hint"]
    for flag in (False, "false", 0, "", None, "no"):
        assert len(call(search, query="fasting glucose insulin", in_tables=flag)["hits"]) == 2
    data = call(search, query="myokines", in_tables=True)
    assert data["hits"] == [] and data["coverage"]["verdict"] == "none" and data["coverage"]["in_tables"] is True
    data = call(search, query="glucose", in_tables="maybe")
    assert data["ok"] is False and data["error"]["code"] == "invalid_argument" and "in_tables" in data["error"]["message"]


def test_markup_words_are_not_indexed_for_tables(lib):
    search, _, _ = handlers(lib)
    assert [h["key"] for h in call(search, query="td tr th")["hits"]] == ["PLAIN001"]  # words in prose still count
    assert call(search, query="structured")["hits"] == [] and call(search, query="paraphrase")["hits"] == []


# ---------- zotero_read ---------------------------------------------------------------------------------

def test_mode_tables_lists_the_tables(lib):
    _, read, _ = handlers(lib)
    data = call(read, key="TABLES01", mode="tables")
    assert data["ok"] is True and data["mode"] == "tables" and data["total_tables"] == 3 and data["warnings"] == []
    assert [(t["table"], t["caption"], t["rows"], t["cols"]) for t in data["tables"]] == \
        [(1, None, 4, 3), (2, None, 61, 3), (3, None, 2, 2)]
    assert data["tables"][0]["chars"] == len(T1_PIPES) and data["tables"][1]["chars"] > 2000
    assert data["title"] == "Adiponectin and visceral fat" and data["citation"]["text"] and "text" not in data
    data = call(read, key="PLAIN001", mode="tables", query="glucose")
    assert data["ok"] is True and data["total_tables"] == 0 and data["tables"] == []
    assert any("no structured tables" in w for w in data["warnings"]) and any("query" in w for w in data["warnings"])


def test_mode_tables_returns_one_table(lib):
    _, read, _ = handlers(lib)
    data = call(read, key="TABLES01", mode="tables", table=1)
    assert data["text"] == T1_PIPES and data["next_offset"] is None and data["warnings"] == []
    assert data["table"] == {"table": 1, "caption": None, "rows": 4, "cols": 3, "chars": len(T1_PIPES)}
    assert data["total_chars"] == len(T1_PIPES) and data["mode"] == "tables" and data["citation"]["text"]
    assert call(read, key="TABLES01", mode="tables", table="3")["text"] == "### Table 3\n| Marker | Level |\n| --- | --- |\n| leptin | high |\n"
    data = call(read, key="TABLES01", mode="tables", table=9)
    assert data["ok"] is False and data["error"]["code"] == "not_found" and "mode=tables" in data["error"]["hint"]
    assert call(read, key="NOSUCH01", mode="tables")["error"]["code"] == "not_found"
    assert call(read, key="TABLES01", mode="table")["error"]["code"] == "invalid_argument"


def test_a_long_table_is_paged_in_whole_pieces(lib):
    _, read, _ = handlers(lib)
    pages = []
    offset = None
    for _ in range(10):
        args = {"key": "TABLES01", "mode": "tables", "table": 2, "max_chars": 2500}
        if offset is not None:
            args["offset"] = offset
        data = call(read, **args)
        assert data["ok"] is True and data["warnings"] == [] and len(data["text"]) <= 2500
        pages.append(data["text"])
        offset = data["next_offset"]
        if offset is None:
            break
    assert len(pages) >= 2 and pages[0].startswith("### Table 2\n| Subject | Fasting glucose | Fasting insulin |\n| --- |")
    assert all(p.startswith("### Table 2 (continued)\n| Subject | Fasting glucose |") for p in pages[1:])
    assert [row[:13] for p in pages for row in data_rows(p)] == [f"| Subject {n:03d}" for n in range(60)]
    whole = call(read, key="TABLES01", mode="tables", table=2, max_chars=12000)
    assert whole["next_offset"] is None and len(data_rows(whole["text"])) == 60 and "\n\n### Table 2 (continued)\n" in whole["text"]
    stray = call(read, key="TABLES01", mode="tables", table=2, offset=3)
    assert stray["offset"] == whole["offset"] and any("outside table 2" in w for w in stray["warnings"])


def test_a_small_max_chars_cuts_at_a_row_end(lib):
    _, read, _ = handlers(lib)
    rows, offset, warned = [], None, False
    for _ in range(40):
        args = {"key": "TABLES01", "mode": "tables", "table": 2, "max_chars": 600}
        if offset is not None:
            args["offset"] = offset
        data = call(read, **args)
        assert 0 < len(data["text"]) <= 2000 and data["text"].endswith("|\n")
        warned = warned or any("max_chars is smaller" in w for w in data["warnings"])
        rows += data_rows(data["text"])
        offset = data["next_offset"]
        if offset is None:
            break
    assert offset is None and warned
    assert [row[:13] for row in rows] == [f"| Subject {n:03d}" for n in range(60)]


def test_text_mode_reads_tables_as_pipe_rows(lib):
    _, read, _ = handlers(lib)
    data = call(read, key="TABLES01", max_chars=12000, table=2)
    assert data["mode"] == "text" and data["tables_count"] == 3 and data["next_offset"] is None
    assert any("table is only used" in w for w in data["warnings"])
    text = data["text"]
    assert text.startswith(HEAD) and T1_PIPES in text and "<t" not in text and "Tables (structured)" not in text
    assert len(data_rows(text)) == 60 and text.rstrip().endswith("| leptin | high |")
    assert data["total_chars"] == len(text)
    data = call(read, key="TABLES01", query="leptin", max_chars=300)
    assert data["section"] == "Table 3" and data["text"].startswith("### Table 3\n| Marker | Level |")
    assert call(read, key="PLAIN001")["tables_count"] == 0


# ---------- registration and skill ----------------------------------------------------------------------

def test_schemas_and_descriptions(plugin_module, fake_ctx):
    plugin_module.register(fake_ctx)
    read = fake_ctx.tools["zotero_read"]["schema"]
    props = read["parameters"]["properties"]
    assert props["mode"]["enum"] == ["text", "annotations", "tables"] and "tables" in props["mode"]["description"]
    assert props["table"]["type"] == "integer" and read["parameters"]["required"] == ["key"]
    assert "tables" in read["description"][:80] and "mode=tables" in read["description"] and len(read["description"]) <= 400
    search = fake_ctx.tools["zotero_search"]["schema"]
    assert search["parameters"]["properties"]["in_tables"]["type"] == "boolean"
    assert "in_tables" in search["description"] and len(search["description"]) <= 400


def test_skill_explains_the_table_route():
    text = (ROOT / "skills" / "zotero-library" / "SKILL.md").read_text(encoding="utf-8")
    assert re.search(r"^version: 0\.2\.0$", text, re.M) and len(text) <= 4000
    for word in ("`in_tables`", "`table`", "`tables`", "`kind: table`", "`index_outdated`"):
        assert word in text
