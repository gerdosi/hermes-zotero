import sqlite3
import time

import pytest

from tests.zfixture import ZoteroFixture
from zotcore.zdb import (Attachment, Item, ItemRef, libraries, list_items, load_items, normalize_doi,
                         open_snapshot, parse_date)


@pytest.fixture
def lib(tmp_path):
    z = ZoteroFixture(tmp_path / "Zotero")
    group_lib = z.add_group(4805701, "Ancestralize")
    z.add_feed_library()
    parent = z.add_collection("Metabolism")
    child = z.add_collection("Ferroptosis", parent=parent)
    art = z.add_item("ART00001", fields={
        "title": "Fatty acid desaturation and ferroptosis", "date": "2026-06-29 2026-06-29",
        "DOI": "https://doi.org/10.1016/J.CELL.2026.10.001", "publicationTitle": "Cell",
        "abstractNote": "We show that SCD1 ..."},
        creators=[("Lena", "Kuehnemann", "author"), ("WHO Consortium", "author"), ("Ann", "Editor", "editor")],
        collections=[child], tags=["Important", "lipids"])
    z.add_attachment(art, "PDF00001", ft_text="x" * 500, indexed_pages=10, total_pages=12)
    z.add_attachment(art, "HTM00001", content_type="text/html", link_mode=1, path="storage:page.html")
    z.add_attachment(art, "URL00001", content_type="text/html", link_mode=3, path=None)
    trashed_att = z.add_attachment(art, "PDF0GONE")
    z.trash(trashed_att)
    z.add_note(art, "NOTE0001")
    z.add_item("SEC00001", "bookSection", fields={"title": "A chapter", "date": "2001-00-00 2001",
                                                   "bookTitle": "Big Book", "extra": "PMID: 1\nDOI: 10.1000/ABC"})
    z.add_item("NODATE01", "report", fields={"title": "Undated", "date": "0000-00-00 n.d."})
    gone = z.add_item("TRASHED1", fields={"title": "In the trash"})
    z.trash(gone)
    z.add_item("GRP00001", library_id=group_lib, fields={"title": "Group paper"})
    z.close()
    con = open_snapshot(z.db_path)
    yield con
    con.close()


def test_normalize_doi():
    assert normalize_doi("https://doi.org/10.1016/J.CELL.2026.10.001") == "10.1016/j.cell.2026.10.001"
    assert normalize_doi("http://dx.doi.org/10.2741/4160") == "10.2741/4160"
    assert normalize_doi("doi: 10.1/X ") == "10.1/x"
    assert normalize_doi("  10.1002/(SICI)1096-8644(1998)107:27<177::AID-AJPA7>3.0.CO;2-B") == \
        "10.1002/(sici)1096-8644(1998)107:27<177::aid-ajpa7>3.0.co;2-b"
    assert normalize_doi("https://journals.physiology.org/doi/full/10.1152/ajpendo.00323.2019") == \
        "10.1152/ajpendo.00323.2019"  # a publisher link pasted into the DOI field
    assert normalize_doi("10.1038/ s41577-018-0113-4") == "10.1038/s41577-018-0113-4"
    assert normalize_doi("") == "" and normalize_doi(None) == ""


def test_parse_date():
    assert parse_date("2026-06-29 2026-06-29") == (2026, "2026-06-29")
    assert parse_date("2001-00-00 2001") == (2001, "2001")
    assert parse_date("2019-03-00 March 2019") == (2019, "March 2019")
    assert parse_date("0000-00-00 n.d.") == (None, "n.d.")
    assert parse_date("") == (None, "")


def test_open_snapshot_is_read_only(lib):
    with pytest.raises(sqlite3.OperationalError):
        lib.execute("CREATE TABLE x(y)")


def test_libraries(lib):
    libs = libraries(lib)
    assert set(libs) == {"user", "4805701"}  # the feed library is not a library we index
    assert libs["user"].label == "My Library"
    assert libs["4805701"].label == "Ancestralize"


def test_list_items_regular_only(lib):
    refs = list_items(lib, ["user"])
    assert [r.key for r in refs] == ["ART00001", "NODATE01", "SEC00001"]  # sorted; no attachments, notes, trash
    assert all(isinstance(r, ItemRef) and r.library == "user" and r.modified for r in refs)
    assert [r.key for r in list_items(lib, ["4805701"])] == ["GRP00001"]
    both = [r.key for r in list_items(lib, ["user", "4805701", "999", "user"])]  # unknown group and repeats ignored
    assert both == ["ART00001", "NODATE01", "SEC00001", "GRP00001"]  # libraries in the order asked, keys sorted


def test_modified_changes_when_item_changes(tmp_path):
    z = ZoteroFixture(tmp_path / "Z")
    iid = z.add_item("AAAA0001", fields={"title": "t"})
    before = list_items(open_snapshot(z.db_path), ["user"])[0].modified
    z.set_field(iid, "title", "t2")
    after = list_items(open_snapshot(z.db_path), ["user"])[0].modified
    assert before != after


def test_load_item_fields(lib):
    ref = {r.key: r for r in list_items(lib, ["user"])}
    (art,) = load_items(lib, [ref["ART00001"].item_id])
    assert isinstance(art, Item)
    assert art.title == "Fatty acid desaturation and ferroptosis"
    assert art.item_type == "journalArticle"
    assert art.creators == ("Kuehnemann, Lena", "WHO Consortium", "Editor, Ann")
    assert (art.year, art.date) == (2026, "2026-06-29")
    assert art.doi == "10.1016/j.cell.2026.10.001"
    assert art.publication == "Cell"
    assert art.abstract.startswith("We show")
    assert art.collections == ("Metabolism / Ferroptosis",)
    assert art.tags == ("Important", "lipids")
    assert art.library == "user"
    assert art.modified == ref["ART00001"].modified
    assert [a.key for a in art.attachments] == ["PDF00001", "HTM00001", "URL00001"]  # trashed one excluded
    pdf = art.attachments[0]
    assert isinstance(pdf, Attachment)
    assert (pdf.content_type, pdf.link_mode, pdf.path) == ("application/pdf", 0, "storage:paper.pdf")
    assert (pdf.indexed_pages, pdf.total_pages) == (10, 12)
    assert art.attachments[2].link_mode == 3 and art.attachments[2].path is None


def test_load_item_fallbacks(lib):
    ref = {r.key: r for r in list_items(lib, ["user"])}
    sec, nodate = load_items(lib, [ref["SEC00001"].item_id, ref["NODATE01"].item_id])
    assert sec.publication == "Big Book"  # bookTitle when there is no publicationTitle
    assert sec.doi == "10.1000/abc"  # DOI taken from the Extra field
    assert (sec.year, sec.date) == (2001, "2001")
    assert sec.creators == () and sec.collections == () and sec.tags == () and sec.attachments == ()
    assert (nodate.year, nodate.date, nodate.doi, nodate.publication) == (None, "n.d.", "", "")


def test_load_items_keeps_order_and_skips_unknown(lib):
    ref = {r.key: r for r in list_items(lib, ["user"])}
    ids = [ref["SEC00001"].item_id, 999999, ref["ART00001"].item_id]
    assert [i.key for i in load_items(lib, ids)] == ["SEC00001", "ART00001"]


def test_load_many_items_quickly(tmp_path):
    z = ZoteroFixture(tmp_path / "Z")
    z.con.execute("BEGIN")
    for n in range(1500):  # more than SQLite's default limit of 999 bound parameters
        iid = z.add_item(f"K{n:07d}", fields={"title": f"Paper {n}", "date": "2020-00-00 2020"},
                         creators=[("A", f"Author{n}", "author")])
        z.add_attachment(iid, f"A{n:07d}")
    z.con.execute("COMMIT")
    z.close()
    con = open_snapshot(z.db_path)
    refs = list_items(con, ["user"])
    started = time.monotonic()
    items = load_items(con, [r.item_id for r in refs])
    assert len(items) == 1500
    assert all(len(i.attachments) == 1 for i in items)
    assert time.monotonic() - started < 5
