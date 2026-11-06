import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from zotcore import tools
from zotcore.settings import Settings
from zotcore.snapshot import SnapshotError, is_stale, load_info, take_snapshot


def count_items(db_path, immutable=False):
    uri = f"file:{db_path}?immutable=1" if immutable else f"file:{db_path}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        return con.execute("SELECT count(*) FROM items").fetchone()[0]
    finally:
        con.close()


@pytest.fixture
def zotero_like(tmp_path):
    """A data dir whose zotero.sqlite behaves like a running Zotero: WAL mode, exclusive lock,
    one row checkpointed into the main file and one row still only in the -wal file."""
    data_dir = tmp_path / "Zotero"
    data_dir.mkdir()
    con = sqlite3.connect(data_dir / "zotero.sqlite", isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA wal_autocheckpoint=0")
    con.execute("CREATE TABLE items(itemID INTEGER PRIMARY KEY, key TEXT)")
    con.execute("INSERT INTO items(key) VALUES ('AAAA1111')")
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("PRAGMA locking_mode=EXCLUSIVE")
    con.execute("INSERT INTO items(key) VALUES ('BBBB2222')")
    yield data_dir, con
    con.close()


def fingerprint(directory: Path):
    return {p.name: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(directory.iterdir()) if p.is_file()}


def bump_mtime(path):
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))


def test_snapshot_includes_rows_still_in_wal(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    # Why this module exists: an immutable read of the live file misses the WAL row.
    assert count_items(data_dir / "zotero.sqlite", immutable=True) == 1
    info = take_snapshot(data_dir, tmp_path / "snap", settle_seconds=0)
    assert info.attempts == 1
    assert info.quick_check == "ok"
    assert info.source_wal_size > 0
    assert count_items(info.path) == 2


def test_snapshot_is_self_contained(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    info = take_snapshot(data_dir, tmp_path / "snap", settle_seconds=0)
    current = Path(info.path).parent
    assert current.name == "current"
    assert sorted(p.name for p in current.iterdir()) == ["snapshot.json", "zotero.sqlite"]
    assert count_items(info.path, immutable=True) == 2


def test_source_is_never_modified(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    before = fingerprint(data_dir)
    take_snapshot(data_dir, tmp_path / "snap", settle_seconds=0)
    assert fingerprint(data_dir) == before


def test_retries_when_main_file_changes_during_copy(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    calls = {"bumped": False}

    def flaky_copy(src, dst):
        shutil.copyfile(src, dst)
        if Path(src).name == "zotero.sqlite" and not calls["bumped"]:
            calls["bumped"] = True
            bump_mtime(src)

    info = take_snapshot(data_dir, tmp_path / "snap", settle_seconds=0, copy=flaky_copy)
    assert info.attempts == 2
    assert count_items(info.path) == 2


def test_wal_growth_after_copy_is_accepted(zotero_like, tmp_path):
    data_dir, writer = zotero_like

    def copy_then_write(src, dst):
        shutil.copyfile(src, dst)
        if Path(src).name == "zotero.sqlite-wal":
            writer.execute("INSERT INTO items(key) VALUES ('CCCC3333')")

    info = take_snapshot(data_dir, tmp_path / "snap", settle_seconds=0, copy=copy_then_write)
    assert info.attempts == 1
    assert count_items(info.path) == 2  # the late row is not in the copy, and that is consistent


def test_gives_up_and_keeps_previous_snapshot(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    dest = tmp_path / "snap"
    first = take_snapshot(data_dir, dest, settle_seconds=0)

    def always_busy(src, dst):
        shutil.copyfile(src, dst)
        if Path(src).name == "zotero.sqlite":
            bump_mtime(src)

    with pytest.raises(SnapshotError) as exc:
        take_snapshot(data_dir, dest, retries=3, settle_seconds=0, copy=always_busy)
    assert exc.value.code == "source_busy"
    assert load_info(dest) == first
    assert count_items(first.path) == 2
    assert sorted(os.listdir(dest)) == ["current"]


def test_corrupt_copy_is_rejected(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    dest = tmp_path / "snap"
    first = take_snapshot(data_dir, dest, settle_seconds=0)

    def corrupting_copy(src, dst):
        if Path(src).name == "zotero.sqlite":
            Path(dst).write_bytes(b"this is not a database" * 500)
        else:
            shutil.copyfile(src, dst)

    with pytest.raises(SnapshotError) as exc:
        take_snapshot(data_dir, dest, settle_seconds=0, copy=corrupting_copy)
    assert exc.value.code == "corrupt_copy"
    assert load_info(dest) == first
    assert sorted(os.listdir(dest)) == ["current"]


def test_second_snapshot_replaces_first(zotero_like, tmp_path):
    data_dir, writer = zotero_like
    dest = tmp_path / "snap"
    take_snapshot(data_dir, dest, settle_seconds=0)
    writer.execute("INSERT INTO items(key) VALUES ('DDDD4444')")
    info = take_snapshot(data_dir, dest, settle_seconds=0)
    assert count_items(info.path) == 3
    assert sorted(os.listdir(dest)) == ["current"]


def test_load_info_round_trip_and_staleness(zotero_like, tmp_path):
    data_dir, writer = zotero_like
    dest = tmp_path / "snap"
    assert load_info(dest) is None
    info = take_snapshot(data_dir, dest, settle_seconds=0)
    assert load_info(dest) == info
    meta = json.loads((Path(info.path).parent / "snapshot.json").read_text(encoding="utf-8"))
    assert meta["taken_at"].endswith("Z")
    assert is_stale(info, data_dir) is False
    writer.execute("INSERT INTO items(key) VALUES ('EEEE5555')")
    assert is_stale(info, data_dir) is True


def test_plain_database_without_wal(tmp_path):
    data_dir = tmp_path / "Zotero"
    data_dir.mkdir()
    con = sqlite3.connect(data_dir / "zotero.sqlite")
    con.execute("CREATE TABLE items(itemID INTEGER PRIMARY KEY, key TEXT)")
    con.execute("INSERT INTO items(key) VALUES ('AAAA1111')")
    con.commit()
    con.close()
    info = take_snapshot(data_dir, tmp_path / "snap", settle_seconds=0)
    assert info.source_wal_size == 0
    assert count_items(info.path) == 1


def test_missing_database(tmp_path):
    (tmp_path / "Zotero").mkdir()
    with pytest.raises(SnapshotError) as exc:
        take_snapshot(tmp_path / "Zotero", tmp_path / "snap", settle_seconds=0)
    assert exc.value.code == "no_database"


def test_status_reports_snapshot(zotero_like, tmp_path):
    data_dir, _ = zotero_like
    plugin_data = tmp_path / "plugin-data"
    provider = lambda: Settings(zotero_data_dir=str(data_dir))
    specs = {s.name: s for s in tools.tool_specs(provider, data_root=lambda: plugin_data)}
    status = specs["zotero_status"].handler
    assert json.loads(status({}))["snapshot"] is None
    take_snapshot(data_dir, plugin_data / "snapshot", settle_seconds=0)
    snap = json.loads(status({}))["snapshot"]
    assert snap["stale"] is False
    assert snap["taken_at"].endswith("Z")


def test_status_survives_unavailable_plugin_data_dir(zotero_like):
    data_dir, _ = zotero_like
    def broken_root():
        raise RuntimeError("no hermes home")
    provider = lambda: Settings(zotero_data_dir=str(data_dir))
    specs = {s.name: s for s in tools.tool_specs(provider, data_root=broken_root)}
    data = json.loads(specs["zotero_status"].handler({}))
    assert data["ok"] is True
    assert data["snapshot"] is None
    assert any("plugin data" in w for w in data["warnings"])


def test_cli_snapshot_command(zotero_like, tmp_path, capsys):
    import argparse
    from zotcore import cli
    data_dir, _ = zotero_like
    parser = argparse.ArgumentParser(prog="hermes zotero")
    cli.setup_parser(parser)
    settings = Settings(zotero_data_dir=str(data_dir))
    rc = cli.run(parser.parse_args(["snapshot"]), settings, data_root=lambda: tmp_path / "pd")
    assert rc == 0
    assert "snapshot" in capsys.readouterr().out.lower()
    assert count_items(tmp_path / "pd" / "snapshot" / "current" / "zotero.sqlite") == 2
    # A missing data dir is a clean non-zero exit, not a traceback.
    rc = cli.run(parser.parse_args(["snapshot"]), Settings(zotero_data_dir=str(tmp_path / "nope")),
                 data_root=lambda: tmp_path / "pd")
    assert rc == 2
