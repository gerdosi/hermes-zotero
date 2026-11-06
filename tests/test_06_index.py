import argparse
import json
import time

import pytest

from tests.zfixture import ZoteroFixture
from zotcore import cli, tools
from zotcore.index import Index, SyncReport, sync
from zotcore.settings import Settings
from zotcore.textsource import MarkdownCorpus

TEXT = "Stearoyl-CoA desaturase protects cancer cells from lipid peroxidation and ferroptosis.\n\n" * 30


def hits(index, query):
    rows = index.con.execute("SELECT DISTINCT item_key FROM passages WHERE passages MATCH ? ORDER BY item_key", (query,))
    return [r[0] for r in rows]


@pytest.fixture
def setup(tmp_path):
    z = ZoteroFixture(tmp_path / "Zotero")
    group = z.add_group(4805701, "Ancestralize")
    a = z.add_item("MDPAPER1", fields={"title": "Markdown paper", "DOI": "10.1/md"})
    z.add_attachment(a, "PDFMD001", ft_text="cache that loses to markdown " * 20)
    b = z.add_item("FTPAPER1", fields={"title": "Cache paper"})
    z.add_attachment(b, "PDFFT001", ft_text=TEXT, indexed_pages=5, total_pages=9)
    c = z.add_item("SCANNED1", fields={"title": "Scanned paper", "abstractNote": "Mitochondrial uncoupling in brown fat."})
    z.add_attachment(c, "PDFSC001")
    g = z.add_item("GROUPPP1", library_id=group, fields={"title": "Group paper"})
    z.add_attachment(g, "PDFGR001", ft_text="Group text about insulin resistance and myokines.\n\n" * 10)
    md = tmp_path / "md"
    md.mkdir()
    (md / "doi_10.1_md.md").write_text("# Markdown paper\n\nIntro.\n\n## Results\n\nKetogenic diet lowered hepatic triglycerides.\n" * 3,
                                       encoding="utf-8")
    index = Index(tmp_path / "plugin" / "index.sqlite")
    yield z, index, MarkdownCorpus(md), tmp_path
    index.close()
    z.close()


def run(index, z, corpus=None, **kw):
    return sync(index, z.db_path, z.data_dir, corpus=corpus, **kw)


def test_first_sync_builds_the_index(setup):
    z, index, corpus, _ = setup
    rep = run(index, z, corpus)
    assert isinstance(rep, SyncReport)
    assert (rep.examined, rep.indexed, rep.deleted, rep.remaining, rep.done) == (3, 3, 0, 0, True)
    c = index.counts()
    assert c["items"] == 3 and c["libraries"] == {"user": 3}
    assert c["by_source"] == {"markdown": 1, "ft-cache": 1, "metadata": 1}
    assert c["flags"] == {"truncated": 1, "body_not_read": 1, "scanned_or_empty": 1}
    assert c["passages"] >= 4
    assert c["last_sync"].endswith("Z")
    assert hits(index, "triglycerides") == ["MDPAPER1"]
    assert hits(index, "peroxidation") == ["FTPAPER1"]
    assert hits(index, "uncoupling") == ["SCANNED1"]  # metadata-only items are searchable too
    assert hits(index, "loses") == []  # the losing ft-cache text is not indexed
    assert hits(index, "desaturases") == ["FTPAPER1"]  # porter stemming


def test_item_row_holds_metadata(setup):
    z, index, corpus, _ = setup
    run(index, z, corpus)
    row = index.con.execute("SELECT title, doi, text_source, flags, n_passages, creators FROM items WHERE item_key='FTPAPER1'").fetchone()
    assert row[0] == "Cache paper" and row[2] == "ft-cache"
    assert json.loads(row[3]) == ["truncated"] and row[4] >= 1 and json.loads(row[5]) == []
    assert index.con.execute("SELECT doi FROM items WHERE item_key='MDPAPER1'").fetchone()[0] == "10.1/md"


def test_second_sync_does_nothing(setup):
    z, index, corpus, _ = setup
    run(index, z, corpus)
    passages = index.counts()["passages"]
    rep = run(index, z, corpus)
    assert (rep.examined, rep.indexed, rep.deleted, rep.done) == (3, 0, 0, True)
    assert index.counts()["passages"] == passages


def test_changes_are_reindexed_without_duplicates(setup):
    z, index, corpus, _ = setup
    run(index, z, corpus)
    before = index.counts()["passages"]
    item_id = z.con.execute("SELECT itemID FROM items WHERE key='FTPAPER1'").fetchone()[0]
    z.set_field(item_id, "title", "Cache paper, renamed")
    assert run(index, z, corpus).indexed == 1
    assert index.counts()["passages"] == before
    assert index.con.execute("SELECT title FROM items WHERE item_key='FTPAPER1'").fetchone()[0] == "Cache paper, renamed"


def test_new_text_cache_triggers_reindex(setup):
    z, index, corpus, _ = setup
    run(index, z, corpus)
    z.write_ft_cache("PDFSC001", "Now indexed: thermogenesis and UCP1 expression.\n\n" * 10)
    rep = run(index, z, corpus)
    assert rep.indexed == 1
    assert hits(index, "thermogenesis") == ["SCANNED1"]
    assert index.con.execute("SELECT text_source FROM items WHERE item_key='SCANNED1'").fetchone()[0] == "ft-cache"


def test_trashed_items_are_removed(setup):
    z, index, corpus, _ = setup
    run(index, z, corpus)
    z.trash(z.con.execute("SELECT itemID FROM items WHERE key='FTPAPER1'").fetchone()[0])
    rep = run(index, z, corpus)
    assert rep.deleted == 1
    assert hits(index, "peroxidation") == []
    assert index.counts()["items"] == 2


def test_group_libraries_are_opt_in(setup):
    z, index, corpus, _ = setup
    rep = run(index, z, corpus, libraries=("user", "4805701", "999"))
    assert rep.indexed == 4
    assert any("999" in w for w in rep.warnings)
    assert hits(index, "myokines") == ["GROUPPP1"]
    assert index.con.execute("SELECT library FROM items WHERE item_key='GROUPPP1'").fetchone()[0] == "4805701"
    rep = run(index, z, corpus, libraries=("user",))
    assert rep.deleted == 1 and hits(index, "myokines") == []  # a library removed from settings leaves the index


def test_budget_stops_early_and_next_run_resumes(tmp_path):
    z = ZoteroFixture(tmp_path / "Z")
    for n in range(10):
        iid = z.add_item(f"K{n:07d}", fields={"title": f"Paper {n}"})
        z.add_attachment(iid, f"A{n:07d}", ft_text=f"unique{n} " * 50)
    index = Index(tmp_path / "idx.sqlite")
    ticks = iter(range(1000))
    rep = sync(index, z.db_path, z.data_dir, batch_items=2, budget_seconds=3, clock=lambda: next(ticks))
    assert rep.done is False and 0 < rep.examined < 10 and rep.remaining == 10 - rep.examined
    assert index.counts()["last_sync"] is None  # not complete yet
    rep2 = sync(index, z.db_path, z.data_dir, batch_items=2)
    assert rep2.done is True and rep2.indexed == 10 - rep.indexed
    assert index.counts()["items"] == 10
    assert len(hits(index, "unique7")) == 1
    index.close()
    z.close()


def test_progress_and_persistence(setup):
    z, index, corpus, tmp_path = setup
    seen = []
    run(index, z, corpus, batch_items=1, progress=lambda done, total: seen.append((done, total)))
    assert seen == [(1, 3), (2, 3), (3, 3)]
    counts = index.counts()
    index.close()
    again = Index(tmp_path / "plugin" / "index.sqlite")  # reopening must not reset anything
    assert again.counts() == counts
    again.close()


def test_sync_speed(tmp_path):
    z = ZoteroFixture(tmp_path / "Z")
    z.con.execute("BEGIN")
    for n in range(300):
        iid = z.add_item(f"K{n:07d}", fields={"title": f"Paper {n}"})
        z.add_attachment(iid, f"A{n:07d}", ft_text=("Insulin signalling in adipocytes. " * 30 + "\n\n") * 8)
    z.con.execute("COMMIT")
    index = Index(tmp_path / "idx.sqlite")
    started = time.monotonic()
    rep = sync(index, z.db_path, z.data_dir)
    assert rep.indexed == 300
    assert time.monotonic() - started < 20
    index.close()
    z.close()


def test_cli_sync_and_status(setup, capsys):
    z, _, _, tmp_path = setup
    parser = argparse.ArgumentParser(prog="hermes zotero")
    cli.setup_parser(parser)
    root = tmp_path / "pd"
    settings = Settings(zotero_data_dir=str(z.data_dir), markdown_path=str(tmp_path / "md"))
    assert cli.run(parser.parse_args(["sync"]), settings, data_root=lambda: root) == 0
    out = capsys.readouterr().out
    assert "Sync: indexed 3," in out and "Index: 3 items" in out
    assert (root / "index.sqlite").is_file() and (root / "snapshot" / "current" / "zotero.sqlite").is_file()
    assert cli.run(parser.parse_args(["sync"]), settings, data_root=lambda: root) == 0
    assert "Sync: indexed 0," in capsys.readouterr().out
    status = {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root)}["zotero_status"].handler
    data = json.loads(status({}))
    assert data["index"]["items"] == 3
    assert data["index"]["by_source"]["markdown"] == 1
    assert data["index"]["last_sync"].endswith("Z")
    assert cli.run(parser.parse_args(["sync"]), Settings(zotero_data_dir=str(tmp_path / "nope")),
                   data_root=lambda: root) == 2


def test_status_without_index(tmp_path):
    root = tmp_path / "pd"
    status = {s.name: s for s in tools.tool_specs(Settings, data_root=lambda: root)}["zotero_status"].handler
    data = json.loads(status({}))
    assert data["ok"] is True and data["index"] is None
    assert not (root / "index.sqlite").exists()  # status never creates the index
