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
