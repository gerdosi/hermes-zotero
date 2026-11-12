import argparse
import hashlib
import json
import shutil
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

import zotcore.index as index_module
from tests.zfixture import ZoteroFixture
from zotcore import cli, tools
from zotcore.citation import approximate_citation, fetch_zotero_citation
from zotcore.index import Index, sync
from zotcore.settings import Settings
from zotcore.snapshot import take_snapshot
from zotcore.synctool import sync_lock, sync_step

ME, COLLEAGUE = 1111111, 2222222
ACCOUNT_DDL = """
CREATE TABLE settings (setting TEXT, key TEXT, value, PRIMARY KEY (setting, key));
CREATE TABLE users (userID INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE groupItems (itemID INTEGER PRIMARY KEY, createdByUserID INT, lastModifiedByUserID INT);
"""
BIB = ('<div class="csl-bib-body" style="line-height: 2; margin-left: 2em; text-indent:-2em;">\n'
       '  <div class="csl-entry">Dixon, S. J., &amp; Stockwell, B. R. (2025). Ferroptosis in adipocytes. '
       '<i>Cell Metabolism</i>, <i>37</i>(2), 100–110. https://doi.org/10.1000/ferro.1</div>\n</div>')
BIB_TEXT = ("Dixon, S. J., & Stockwell, B. R. (2025). Ferroptosis in adipocytes. Cell Metabolism, 37(2), 100–110. "
            "https://doi.org/10.1000/ferro.1")


def annotate(z, attachment, key, text, *, sort, page, kind=1, comment="", color="#ffd400", external=False,
             author_name=None, created_by=None, tags=()):
    item_id = z.add_annotation(attachment, key, text, comment=comment, page_label=page, color=color, kind=kind)
    z.con.execute("UPDATE itemAnnotations SET sortIndex = ?, isExternal = ?, authorName = ? WHERE itemID = ?",
                  (sort, int(external), author_name, item_id))
    if created_by is not None:
        z.con.execute("INSERT INTO groupItems (itemID, createdByUserID) VALUES (?, ?)", (item_id, created_by))
    for tag in tags:
        z.con.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
        tag_id = z.con.execute("SELECT tagID FROM tags WHERE name = ?", (tag,)).fetchone()[0]
        z.con.execute("INSERT INTO itemTags VALUES (?, ?, 0)", (item_id, tag_id))
    return item_id


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lib08")
    z = ZoteroFixture(tmp / "Zotero")
    z.con.executescript(ACCOUNT_DDL)
    z.con.execute("INSERT INTO settings VALUES ('account', 'userID', ?)", (ME,))
    z.con.executemany("INSERT INTO users VALUES (?, ?)", [(ME, "me_myself"), (COLLEAGUE, "colleague_k")])
    group = z.add_group(4805701, "Ancestralize")

    i = z.add_item("ANNOT001", fields={"title": "Ferroptosis in adipocytes", "DOI": "10.1000/ferro.1",
                                       "date": "2025-00-00 2025", "publicationTitle": "Cell Metabolism"},
                   creators=[("Scott", "Dixon", "author"), ("Brent", "Stockwell", "author")])
    a = z.add_attachment(i, "PDFA0001", ft_text="Ferroptosis is an iron-dependent cell death.\n\n" * 20)
    b = z.add_attachment(i, "PDFA0002", ft_text=None)  # a supplement PDF
    # inserted out of order: the output follows attachment, then sortIndex
    annotate(z, a, "ANN00004", None, sort="00003|000001|00001", page="4", kind=2, comment="Compare with Smith 2021",
             tags=("Methods", "For review"))
    annotate(z, b, "ANN00007", "Supplementary figure shows the same.", sort="00000|000001|00001", page="S1",
             color="#5fb236")
    annotate(z, a, "ANN00002", "Lipid peroxides accumulate in adipocytes.", sort="00002|000010|00020", page="3",
             kind=5, color="#f19837")
    z.trash(annotate(z, a, "ANN00006", "Deleted highlight", sort="00000|000001|00001", page="1"))
    annotate(z, a, "ANN00001", "Ferroptosis requires loss of GPX4 activity.", sort="00001|000100|00050", page="2",
             comment="Key mechanism for the review")
    annotate(z, a, "ANN00005", "Imported from the PDF file.", sort="00004|000001|00001", page="5", external=True,
             author_name="Reviewer 2")
    annotate(z, a, "ANN00003", None, sort="00002|000500|00100", page="3", kind=3)  # image: nothing to quote
    z.add_note(i, "NOTE0001", html='<div class="zotero-note znv1"><p>My own note &amp; idea</p><p>Second   line</p></div>')
    z.add_note(i, "NOTE0002", html="<p> </p>")
    z.trash(z.add_note(i, "NOTE0003", html="<p>Deleted note</p>"))

    i = z.add_item("GANNOT01", library_id=group, fields={"title": "Group paper", "date": "2024-00-00 2024"},
                   creators=[("Maria", "Lindqvist", "author"), ("Peter", "Novak", "author"), ("Ann", "Other", "author")])
    g = z.add_attachment(i, "GPDF0001", ft_text="Group paper text about ketone bodies.\n\n" * 20)
    annotate(z, g, "GANN0001", "Group highlight by a colleague.", sort="00006|000001|00001", page="7",
             created_by=COLLEAGUE)
    annotate(z, g, "GANN0002", "My highlight in the group.", sort="00007|000001|00001", page="8", created_by=ME)
    annotate(z, g, "GANN0003", "Unknown creator with a name.", sort="00008|000001|00001", page="9",
             author_name="Visitor")
    note = z.add_note(i, "GNOTE001", html="<p>Colleague note</p>")
    z.con.execute("INSERT INTO groupItems (itemID, createdByUserID) VALUES (?, ?)", (note, COLLEAGUE))

    i = z.add_item("MANYANN1", fields={"title": "Many highlights"})
    m = z.add_attachment(i, "PDFM0001", ft_text="Many highlights body text.\n\n" * 20)
    for n in range(30):
        annotate(z, m, f"MANY{n:04d}", f"Highlight {n:02d} " + "x" * 87, sort=f"{n:05d}|000000|00000", page=str(n + 1))

    i = z.add_item("BIGNOTE1", fields={"title": "Long note"})
    z.add_note(i, "BIGN0001", html="<p>" + "y" * 5000 + "</p>")
    i = z.add_item("PLAIN001", fields={"title": "No annotations"})
    z.add_attachment(i, "PDFP0001", ft_text="Plain body text.\n\n" * 20)

    root = tmp / "pd"
    info = take_snapshot(z.data_dir, root / "snapshot")
    index = Index(root / "index.sqlite")
    rep = sync(index, info.path, z.data_dir, libraries=("user", "4805701"))
    assert rep.done and rep.indexed == 5
    index.close()
    z.close()
    return root


class FakeZotero(BaseHTTPRequestHandler):
    """Answers like Zotero's local API (server_localAPI.js); 404 for unknown items."""

    def do_GET(self):
        self.server.seen.append((self.path, self.headers.get("Host")))
        if self.server.disabled:
            return self._send(403, "text/plain", "Local API is not enabled")
        path = urlsplit(self.path).path
        known = {"/api/users/0/items/ANNOT001": "ANNOT001", "/api/groups/4805701/items/GANNOT01": "GANNOT01",
                 "/api/users/0/items/PLAIN001": "WRONGKEY"}  # an answer for another item must not be used
        if path not in known:
            return self._send(404, "text/plain", "Not found")
        body = {"key": known[path], "version": 5, "library": {"type": "user", "id": 0}, "meta": {}, "bib": BIB}
        self._send(200, "application/json", json.dumps(body, indent=4))

    def _send(self, status, ctype, text):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def zotero_api(monkeypatch):
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")  # a proxy that is never there: loopback must bypass it
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeZotero)
    server.daemon_threads = True
    server.seen, server.disabled = [], False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def base_url(server):
    return f"http://127.0.0.1:{server.server_address[1]}/api"


def read_handler(root, citation_api=None, settings=None):
    settings = settings or Settings(libraries=("user", "4805701"))
    specs = {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root, citation_api=citation_api)}
    return specs["zotero_read"].handler


def call(handler, **args):
    out = handler(args)
    assert isinstance(out, str)
    return json.loads(out)


# ---------- registration ------------------------------------------------------------------------------

def test_sync_tool_is_registered_and_read_has_mode(plugin_module, fake_ctx):
    plugin_module.register(fake_ctx)
    assert {"zotero_status", "zotero_search", "zotero_read", "zotero_sync"} == set(fake_ctx.tools)
    mode = fake_ctx.tools["zotero_read"]["schema"]["parameters"]["properties"]["mode"]
    assert mode["enum"] == ["text", "annotations", "tables"]
    props = fake_ctx.tools["zotero_sync"]["schema"]["parameters"]["properties"]
    assert set(props) == {"budget_seconds"}
    assert "Zotero" in fake_ctx.tools["zotero_sync"]["schema"]["description"][:60]
    assert "annotations" in fake_ctx.tools["zotero_read"]["schema"]["description"]


# ---------- annotations mode --------------------------------------------------------------------------

def test_annotations_are_the_users_words_in_reading_order(lib):
    read = read_handler(lib)
    data = call(read, key="ANNOT001", mode="annotations")
    assert data["ok"] is True and data["mode"] == "annotations" and data["key"] == "ANNOT001"
    assert data["title"] == "Ferroptosis in adipocytes" and data["doi"] == "10.1000/ferro.1"
    assert data["annotations"] == [
        {"type": "highlight", "page": "2", "text": "Ferroptosis requires loss of GPX4 activity.",
         "comment": "Key mechanism for the review", "color": "#ffd400", "author": "user"},
        {"type": "underline", "page": "3", "text": "Lipid peroxides accumulate in adipocytes.", "color": "#f19837",
         "author": "user"},
        {"type": "note", "page": "4", "comment": "Compare with Smith 2021", "color": "#ffd400", "author": "user",
         "tags": ["For review", "Methods"]},
        {"type": "highlight", "page": "5", "text": "Imported from the PDF file.", "color": "#ffd400",
         "author": "Reviewer 2", "external": True},
        {"type": "highlight", "page": "S1", "text": "Supplementary figure shows the same.", "color": "#5fb236",
         "author": "user"},
        {"type": "item_note", "text": "My own note & idea\nSecond line", "author": "user"},
    ]
    assert data["total_annotations"] == 6 and data["empty_omitted"] == 2  # the image and the blank note
    assert data["offset"] == 0 and data["next_offset"] is None and data["warnings"] == []
    assert data["snapshot_taken_at"].endswith("Z")


def test_group_annotations_name_their_author(lib):
    read = read_handler(lib)
    data = call(read, key="GANNOT01", mode="annotations")
    assert [(a.get("text"), a["author"]) for a in data["annotations"]] == [
        ("Group highlight by a colleague.", "colleague_k"),
        ("My highlight in the group.", "user"),
        ("Unknown creator with a name.", "Visitor"),
        ("Colleague note", "colleague_k"),
    ]


def test_annotations_paging_and_caps(lib):
    read = read_handler(lib)
    texts, offset, pages = [], 0, 0
    while offset is not None:
        data = call(read, key="MANYANN1", mode="annotations", offset=offset, max_chars=1000)
        assert len(data["annotations"]) == 10 and data["total_annotations"] == 30
        texts += [a["text"] for a in data["annotations"]]
        offset, pages = data["next_offset"], pages + 1
    assert pages == 3 and texts == [f"Highlight {n:02d} " + "x" * 87 for n in range(30)]
    assert len(call(read, key="MANYANN1", mode="annotations")["annotations"]) == 30  # default 4000 chars: all fit
    data = call(read, key="BIGNOTE1", mode="Annotations", max_chars=1000)  # mode is case-insensitive
    note = data["annotations"][0]
    assert note["type"] == "item_note" and note["text"] == "y" * 1000 and note["truncated"] is True
    assert data["next_offset"] is None
    data = call(read, key="MANYANN1", mode="annotations", offset=40)
    assert data["annotations"] == [] and data["next_offset"] is None and data["warnings"]


def test_annotations_edge_cases(lib, tmp_path):
    read = read_handler(lib)
    data = call(read, key="PLAIN001", mode="annotations")
    assert data["annotations"] == [] and data["total_annotations"] == 0 and data["warnings"] == []
    data = call(read, key="ANNOT001", mode="annotations", query="GPX4")
    assert len(data["annotations"]) == 6 and any("query" in w for w in data["warnings"])
    assert call(read, key="ANNOT001", mode="pdf")["error"]["code"] == "invalid_argument"
    assert call(read, key="NOSUCHKY", mode="annotations")["error"]["code"] == "not_found"
    bare = tmp_path / "bare"  # an index but no snapshot
    bare.mkdir()
    shutil.copy(lib / "index.sqlite", bare / "index.sqlite")
    data = call(read_handler(bare), key="ANNOT001", mode="annotations")
    assert data["ok"] is True and data["annotations"] == [] and data["snapshot_taken_at"] is None
    assert any("sync" in w for w in data["warnings"])
    assert call(read_handler(bare), key="ANNOT001")["annotations_count"] is None


def test_text_mode_reports_annotation_count(lib):
    read = read_handler(lib)
    data = call(read, key="ANNOT001", max_chars=300)
    assert data["mode"] == "text" and data["annotations_count"] == 6 and data["text"].startswith("Ferroptosis is")
    assert call(read, key="PLAIN001")["annotations_count"] == 0
    assert call(read, key="GANNOT01")["annotations_count"] == 4


def test_reads_do_not_modify_index_or_snapshot(lib, zotero_api):
    paths = [lib / "index.sqlite", lib / "snapshot" / "current" / "zotero.sqlite"]
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    read = read_handler(lib, base_url(zotero_api))
    for key in ("ANNOT001", "GANNOT01", "MANYANN1", "PLAIN001"):
        call(read, key=key)
        call(read, key=key, mode="annotations")
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths] == before


# ---------- citation line -----------------------------------------------------------------------------

def test_approximate_citation_format():
    assert approximate_citation(["Dixon, Scott", "Stockwell, Brent"], 2025, "Ferroptosis in adipocytes",
                                "Cell Metabolism", "10.1000/ferro.1") == (
        "Dixon & Stockwell (2025). Ferroptosis in adipocytes. Cell Metabolism. https://doi.org/10.1000/ferro.1")
    assert approximate_citation(["World Health Organization"], None, "Is fat bad?", "", "") == (
        "World Health Organization (n.d.). Is fat bad?")
    assert approximate_citation(["Lindqvist, Maria", "Novak, Peter", "Other, Ann"], 2024, "Group paper", None, None) == (
        "Lindqvist et al. (2024). Group paper.")
    assert approximate_citation([], 2020, "Untitled report.", "WHO", "") == "(2020). Untitled report. WHO."


def test_citation_is_approximate_without_zotero(lib):
    data = call(read_handler(lib), key="ANNOT001")  # citation_api=None: Zotero is never called
    assert data["citation"] == {
        "text": "Dixon & Stockwell (2025). Ferroptosis in adipocytes. Cell Metabolism. https://doi.org/10.1000/ferro.1",
        "source": "index", "approximate": True}
    port = socket.socket()
    port.bind(("127.0.0.1", 0))
    closed = f"http://127.0.0.1:{port.getsockname()[1]}/api"
    port.close()  # nothing listens here: like Zotero being closed
    data = call(read_handler(lib, closed), key="GANNOT01", mode="annotations")
    assert data["citation"]["approximate"] is True and data["citation"]["text"] == "Lindqvist et al. (2024). Group paper."


def test_citation_from_zotero_local_api(lib, zotero_api):
    read = read_handler(lib, base_url(zotero_api))
    data = call(read, key="ANNOT001")
    assert data["citation"] == {"text": BIB_TEXT, "source": "zotero", "style": "apa", "approximate": False}
    path, host = zotero_api.seen[-1]
    url = urlsplit(path)
    assert url.path == "/api/users/0/items/ANNOT001" and host == f"127.0.0.1:{zotero_api.server_address[1]}"
    assert parse_qs(url.query) == {"format": ["json"], "include": ["bib"], "style": ["apa"]}
    data = call(read, key="GANNOT01", mode="annotations")
    assert data["citation"]["source"] == "zotero"
    assert urlsplit(zotero_api.seen[-1][0]).path == "/api/groups/4805701/items/GANNOT01"
    data = call(read, key="PLAIN001")  # Zotero answers for a different key: fall back
    assert data["citation"]["source"] == "index" and data["citation"]["text"] == "(n.d.). No annotations."
    assert call(read, key="MANYANN1")["citation"]["source"] == "index"  # Zotero answers 404
    zotero_api.disabled = True  # 403 "Local API is not enabled"
    assert call(read, key="ANNOT001")["citation"]["approximate"] is True


def test_citation_fetch_has_a_timeout():
    class Slow(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(1.5)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        t = time.monotonic()
        assert fetch_zotero_citation(base_url(server), "user", "ANNOT001", timeout=0.3) is None
        assert time.monotonic() - t < 1.2
    finally:
        server.shutdown()
        server.server_close()


# ---------- zotero_sync -------------------------------------------------------------------------------

@pytest.fixture
def zlib(tmp_path):
    z = ZoteroFixture(tmp_path / "Zotero")
    for n in range(9):
        i = z.add_item(f"SYNC{n:04d}", fields={"title": f"Sync paper {n}"})
        z.add_attachment(i, f"SPDF{n:04d}", ft_text=f"Body of sync paper number{n} on brown fat.\n\n" * 10)
    settings = Settings(zotero_data_dir=str(z.data_dir), sync_batch_items=2)
    yield z, settings, tmp_path / "pd"
    z.close()


def sync_handler(settings, root):
    specs = {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root)}
    return specs["zotero_sync"].handler


def test_sync_tool_indexes_then_reuses_the_snapshot(zlib):
    z, settings, root = zlib
    run = sync_handler(settings, root)
    data = call(run)
    assert data["ok"] is True and data["done"] is True and data["indexed"] == 9 and data["remaining"] == 0
    assert data["total"] == 9 and data["eta_seconds"] is None and data["next"] is None
    assert data["snapshot"]["reused"] is False and data["index_last_sync"].endswith("Z")
    data = call(run, budget_seconds=5)
    assert data["done"] is True and data["indexed"] == 0 and data["snapshot"]["reused"] is True
    i = z.add_item("SYNC0100", fields={"title": "A new paper on beige adipocytes"})
    z.add_attachment(i, "SPDF0100", ft_text="Beige adipocytes appear after cold exposure.\n\n" * 10)
    data = call(run, budget_seconds="20")
    assert data["done"] is True and data["indexed"] == 1 and data["snapshot"]["reused"] is False
    search = {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root)}["zotero_search"].handler
    assert [h["key"] for h in call(search, query="beige adipocytes")["hits"]] == ["SYNC0100"]


def test_sync_step_is_time_boxed_and_resumes(zlib, monkeypatch):
    z, settings, root = zlib
    work = {"seconds": 0}
    real_upsert = index_module.Index.upsert

    def slow_upsert(self, *args, **kwargs):
        work["seconds"] += 1  # indexing one item "takes" a second; nothing else does
        return real_upsert(self, *args, **kwargs)

    monkeypatch.setattr(index_module.Index, "upsert", slow_upsert)
    clock = lambda: work["seconds"]
    first = sync_step(settings, root, budget_seconds=3, clock=clock)
    assert first["done"] is False and 0 < first["examined"] < 9 and first["remaining"] == 9 - first["examined"]
    assert first["total"] == 9 and "again" in first["next"] and first["index_last_sync"] is None
    assert first["eta_seconds"] is None or first["eta_seconds"] >= 0
    steps = [first]
    while not steps[-1]["done"]:
        assert len(steps) < 20
        steps.append(sync_step(settings, root, budget_seconds=3, clock=clock))
    assert steps[-1]["remaining"] == 0 and steps[-1]["index_last_sync"].endswith("Z")
    assert sum(s["indexed"] for s in steps) == 9
    assert all(s["snapshot"]["reused"] for s in steps[1:])  # Zotero did not change between the calls


def test_sync_tool_arguments_and_errors(zlib, tmp_path):
    z, settings, root = zlib
    run = sync_handler(settings, root)
    assert call(run, budget_seconds="abc")["error"]["code"] == "invalid_argument"
    assert call(run, budget_seconds=1)["done"] is True  # clamped up to 5 seconds
    missing = Settings(zotero_data_dir=str(tmp_path / "no-zotero-here"))
    data = call(sync_handler(missing, tmp_path / "pd2"))
    assert data["ok"] is False and data["error"]["code"] == "no_zotero" and "doctor" in data["error"]["hint"]
    specs = {s.name: s for s in tools.tool_specs(lambda: settings)}  # no data_root
    assert call(specs["zotero_sync"].handler)["ok"] is False

    def broken():
        raise RuntimeError("kaboom")
    specs = {s.name: s for s in tools.tool_specs(broken, data_root=lambda: root)}
    assert call(specs["zotero_sync"].handler)["error"]["code"] == "internal_error"


def test_only_one_sync_at_a_time(zlib, capsys):
    z, settings, root = zlib
    with sync_lock(root):
        data = call(sync_handler(settings, root))
        assert data["ok"] is False and data["error"]["code"] == "busy"
        parser = argparse.ArgumentParser(prog="hermes zotero")
        cli.setup_parser(parser)
        assert cli.run(parser.parse_args(["sync"]), settings, data_root=lambda: root) == 1
        assert "Another sync is running" in capsys.readouterr().out
    assert call(sync_handler(settings, root))["done"] is True  # the lock is released afterwards
    assert cli.run(parser.parse_args(["sync"]), settings, data_root=lambda: root) == 0


def test_read_errors_are_reported_by_partial_runs_and_capped_in_the_tool(zlib, monkeypatch):
    z, settings, root = zlib

    def broken(item, data_dir, corpus=None):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(index_module, "choose_text", broken)
    index = Index(root / "partial.sqlite")
    try:
        rep = sync(index, z.db_path, z.data_dir, batch_items=2, budget_seconds=0)
        assert rep.done is False and rep.examined == 2 and rep.read_errors == 2
        assert any(w.startswith("2 items could not be read") for w in rep.warnings)
    finally:
        index.close()
    data = call(sync_handler(settings, root))
    assert data["done"] is True and data["indexed"] == 9
    item_lines = [w for w in data["warnings"] if w.startswith("item ")]
    assert len(item_lines) == 3 and any(w.startswith("9 items could not be read") for w in data["warnings"])
