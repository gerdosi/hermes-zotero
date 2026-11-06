import pytest

import zotcore.index as index_module
from tests.zfixture import ZoteroFixture
from zotcore.index import Index, sync


@pytest.fixture
def lib(tmp_path):
    z = ZoteroFixture(tmp_path / "Zotero")
    for n in range(5):
        iid = z.add_item(f"PAPER00{n}", fields={"title": f"Paper {n}", "abstractNote": f"Abstract {n}."})
        z.add_attachment(iid, f"PDF0000{n}", ft_text=f"Body text number{n} about adipose tissue.\n\n" * 20)
    index = Index(tmp_path / "idx.sqlite")
    yield z, index
    index.close()
    z.close()


def test_unreadable_text_does_not_block_the_sync(lib, monkeypatch):
    z, index = lib
    real = index_module.choose_text

    def flaky(item, data_dir, corpus=None):
        if item.key == "PAPER002":
            raise PermissionError(13, "Permission denied", "/Zotero/storage/PDF00002/.zotero-ft-cache")
        return real(item, data_dir, corpus)

    monkeypatch.setattr(index_module, "choose_text", flaky)
    rep = sync(index, z.db_path, z.data_dir, batch_items=2)
    assert rep.done is True and rep.indexed == 5  # the other four are indexed, and so is PAPER002 (metadata only)
    assert any("PAPER002" in w and "Permission denied" in w for w in rep.warnings)
    row = index.con.execute("SELECT text_source, flags FROM items WHERE item_key='PAPER002'").fetchone()
    assert row[0] == "metadata"
    assert "read_error" in row[1] and "body_not_read" in row[1]
    found = index.con.execute("SELECT item_key FROM passages WHERE passages MATCH 'abstract'").fetchall()
    assert ("PAPER002",) in found  # title and abstract are still searchable
    assert index.counts()["flags"]["read_error"] == 1

    # Unchanged files are not retried on every run ...
    rep2 = sync(index, z.db_path, z.data_dir, batch_items=2)
    assert rep2.indexed == 0 and rep2.warnings == ()

    # ... but once the file changes and becomes readable, the item is re-indexed with its full text.
    monkeypatch.setattr(index_module, "choose_text", real)
    z.write_ft_cache("PDF00002", "Fixed body text about mitochondrial uncoupling.\n\n" * 20)
    rep3 = sync(index, z.db_path, z.data_dir, batch_items=2)
    assert rep3.indexed == 1
    assert index.con.execute("SELECT text_source FROM items WHERE item_key='PAPER002'").fetchone()[0] == "ft-cache"


def test_many_read_errors_are_summarised(lib, monkeypatch):
    z, index = lib

    def broken(item, data_dir, corpus=None):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(index_module, "choose_text", broken)
    rep = sync(index, z.db_path, z.data_dir)
    assert rep.done is True and rep.indexed == 5
    assert len(rep.warnings) <= 21  # at most 20 item warnings plus one summary line
    assert any("5 items" in w and "could not be read" in w for w in rep.warnings)
