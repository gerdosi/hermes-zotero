import hashlib
import json
from datetime import date

import pytest

from tests.zfixture import ZoteroFixture
from zotcore import tools
from zotcore.index import Index, sync
from zotcore.settings import Settings

Y = date.today().year
PARAS = [f"Paragraph {n:03d} describes adipose tissue remodelling and lipolysis in some detail.\n\n" for n in range(200)]
PARAS[120] = "Paragraph 120 mentions zeaxanthinmarker, a word that occurs only here.\n\n"
LONG = "".join(PARAS)
TH = "Brown fat thermogenesis requires uncoupling protein 1 activity in mitochondria.\n\n" * 5


def ydate(year):
    return f"{year}-00-00 {year}"


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lib07")
    z = ZoteroFixture(tmp / "Zotero")
    group = z.add_group(4805701, "Ancestralize")
    obesity = z.add_collection("Obesity")
    adipose = z.add_collection("Adipose", parent=obesity)
    neuro = z.add_collection("Neuro")
    i = z.add_item("FERRO001", fields={"title": "Ferroptosis in adipocytes", "DOI": "10.1000/ferro.1", "date": ydate(Y - 1)},
                   creators=[("Scott", "Dixon", "author"), ("Brent", "Stockwell", "author")], collections=[adipose])
    z.add_attachment(i, "PDFF0001", ft_text="Ferroptosis is an iron-dependent cell death driven by lipid peroxidation in adipocytes.\n\n" * 6)
    i = z.add_item("FERRO002", fields={"title": "Neuronal cell death", "date": ydate(Y - 3)}, collections=[neuro])
    z.add_attachment(i, "PDFF0002", ft_text="Ferroptosis also kills neurons after stroke.\n\n" * 6)
    i = z.add_item("META0001", fields={"title": "Adipocyte ferroptosis", "abstractNote": "Adipocyte ferroptosis limits fat mass expansion.",
                                       "date": ydate(Y - 2)})
    z.add_attachment(i, "PDFM0001")  # PDF without text: metadata only
    i = z.add_item("LONG0001", fields={"title": "Adipose remodelling", "date": ydate(Y - 6)})
    z.add_attachment(i, "PDFL0001", ft_text=LONG)
    for n, year in enumerate([Y, Y - 2, Y - 4, Y - 5, Y - 8, Y - 10, Y - 12, Y - 15, Y - 20]):
        i = z.add_item(f"THERM00{n}", fields={"title": f"Thermogenesis study {n}", "date": ydate(year)})
        z.add_attachment(i, f"PDFT000{n}", ft_text=TH)
    for n in range(3):
        i = z.add_item(f"KETONE0{n}", fields={"title": f"Ketone study {n}", "date": ydate(Y - 1)})
        z.add_attachment(i, f"PDFK000{n}", ft_text="Ketone bodies such as beta-hydroxybutyrate fuel the heart.\n\n" * 5)
    for n in range(30):
        i = z.add_item(f"FILL00{n:02d}", fields={"title": f"Insulin paper {n}", "date": ydate(Y - 7)})
        z.add_attachment(i, f"PDFI00{n:02d}", ft_text=f"Insulin signalling in adipocytes, report {n}.\n\n" * 60)  # 2 passages each
    i = z.add_item("SHARED01", fields={"title": "Shared paper, user copy", "DOI": "10.1000/shared.1", "date": ydate(Y - 3)})
    z.add_attachment(i, "PDFS0001", ft_text="Hepatocyte lipid droplets in fatty liver.\n\n" * 5)
    i = z.add_item("GRP00001", library_id=group, fields={"title": "Group copy", "DOI": "10.1000/shared.1", "date": ydate(Y - 3)})
    z.add_attachment(i, "PDFG0001", ft_text="Ferroptosis in hepatocytes during fatty liver disease.\n\n" * 5)
    i = z.add_item("DUPKEY01", fields={"title": "Same key, user library"})
    z.add_attachment(i, "PDFD0001", ft_text="User library text about myokines.\n\n" * 8)
    i = z.add_item("DUPKEY01", library_id=group, fields={"title": "Same key, group library"})
    z.add_attachment(i, "PDFD0002", ft_text="Group library text about myokines.\n\n" * 8)
    root = tmp / "pd"
    index = Index(root / "index.sqlite")
    rep = sync(index, z.db_path, z.data_dir, libraries=("user", "4805701"))
    assert rep.done and rep.indexed == 50
    index.close()
    z.close()
    return root


def handlers(root, settings=None):
    settings = settings or Settings(libraries=("user", "4805701"))
    specs = {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root)}
    return specs["zotero_search"].handler, specs["zotero_read"].handler


def call(handler, **args):
    out = handler(args)
    assert isinstance(out, str)
    return json.loads(out)


def keys(data):
    return [h["key"] for h in data["hits"]]


# ---------- registration -----------------------------------------------------------------------------

def test_both_tools_are_registered(plugin_module, fake_ctx):
    plugin_module.register(fake_ctx)
    assert {"zotero_status", "zotero_search", "zotero_read"} <= set(fake_ctx.tools)
    read_schema = fake_ctx.tools["zotero_read"]["schema"]["parameters"]
    assert read_schema["required"] == ["key"]
    search_props = fake_ctx.tools["zotero_search"]["schema"]["parameters"]["properties"]
    assert {"query", "doi", "collection", "library", "year_from", "year_to", "limit"} <= set(search_props)
    assert {"key", "library", "query", "offset", "max_chars"} <= set(read_schema["properties"])


# ---------- zotero_search ----------------------------------------------------------------------------

def test_search_returns_ranked_hits_with_passages(lib):
    search, _ = handlers(lib)
    data = call(search, query="ferroptosis adipocytes")
    assert data["ok"] is True and data["query"] == "ferroptosis adipocytes"
    assert data["terms"] == ["ferroptosis", "adipocytes"]
    assert set(keys(data)[:2]) == {"FERRO001", "META0001"}  # the only items with both words in one passage
    hit = next(h for h in data["hits"] if h["key"] == "FERRO001")
    assert hit["library"] == "user" and hit["title"] == "Ferroptosis in adipocytes"
    assert hit["first_author"] == "Dixon, Scott" and hit["n_authors"] == 2
    assert hit["year"] == Y - 1 and hit["doi"] == "10.1000/ferro.1"
    assert hit["collections"] == ["Obesity / Adipose"] and hit["text_source"] == "ft-cache" and hit["match"] == "all"
    assert 1 <= len(hit["passages"]) <= 2
    p = hit["passages"][0]
    assert isinstance(p["offset"], int) and "«" in p["snippet"] and "»" in p["snippet"]
    assert data["index_last_sync"].endswith("Z") and data["warnings"] == []


def test_coverage_strong(lib):
    search, _ = handlers(lib)
    cov = call(search, query="thermogenesis uncoupling")["coverage"]
    assert cov["matches_all"] == 9 and cov["matches_any"] == 9
    assert cov["recent"] == 3 and cov["recent_years"] == 5  # Y, Y-2 and Y-4 are recent; Y-5 is not
    assert cov["newest_year"] == Y and cov["verdict"] == "strong"


def test_coverage_thresholds_come_from_settings(lib):
    search, _ = handlers(lib, Settings(libraries=("user", "4805701"), coverage_strong_min=10))
    assert call(search, query="thermogenesis")["coverage"]["verdict"] == "thin"
    search, _ = handlers(lib, Settings(libraries=("user", "4805701"), coverage_recent_years=1))
    cov = call(search, query="thermogenesis")["coverage"]
    assert cov["recent"] == 1 and cov["recent_years"] == 1 and cov["verdict"] == "thin"


def test_coverage_thin_and_none(lib):
    search, _ = handlers(lib)
    data = call(search, query="ketone")
    assert data["coverage"]["matches_all"] == 3 and data["coverage"]["verdict"] == "thin"
    data = call(search, query="xyzzyquux")
    assert data["hits"] == [] and data["coverage"]["verdict"] == "none"
    assert data["coverage"]["matches_any"] == 0 and data["coverage"]["newest_year"] is None
    assert "hint" not in data["coverage"]


def test_no_passage_with_every_term_falls_back_to_any(lib):
    search, _ = handlers(lib)
    data = call(search, query="ketone zebrafish")
    cov = data["coverage"]
    assert cov["matches_all"] == 0 and cov["matches_any"] == 3 and cov["verdict"] == "none"
    assert "fewer" in cov["hint"]
    assert sorted(keys(data)) == ["KETONE00", "KETONE01", "KETONE02"]
    assert {h["match"] for h in data["hits"]} == {"any"}


def test_all_matches_come_before_any_matches(lib):
    search, _ = handlers(lib)
    data = call(search, query="ferroptosis neurons", limit=3)
    assert keys(data)[0] == "FERRO002" and data["hits"][0]["match"] == "all"
    assert all(h["match"] == "any" for h in data["hits"][1:]) and len(data["hits"]) == 3


def test_stopwords_and_odd_syntax(lib):
    search, _ = handlers(lib)
    data = call(search, query="Ferroptosis in the Adipocytes")
    assert data["terms"] == ["ferroptosis", "adipocytes"]
    assert set(keys(data)[:2]) == {"FERRO001", "META0001"}
    assert call(search, query="the of")["terms"] == ["the", "of"]  # nothing but stop words: keep them
    for q in ['ferroptosis AND (adipocytes) OR NOT* "col:x" NEAR(a b) ^title -x', 'SCD-1 "', "10.1000/ferro.1", "ü ß"]:
        assert call(search, query=q)["ok"] is True, q
    assert call(search, query="*:-()")["error"]["code"] == "invalid_argument"  # no words at all


def test_group_libraries_and_library_filter(lib):
    search, _ = handlers(lib)
    data = call(search, query="hepatocytes")  # default: every indexed library
    assert sorted((h["library"], h["key"]) for h in data["hits"]) == [("4805701", "GRP00001"), ("user", "SHARED01")]
    data = call(search, query="ferroptosis", library="4805701")
    assert keys(data) == ["GRP00001"] and data["coverage"]["matches_all"] == 1
    assert keys(call(search, query="ferroptosis", library=4805701)) == ["GRP00001"]  # an int works too
    assert "GRP00001" not in keys(call(search, query="ferroptosis", library="user"))


def test_collection_and_year_filters(lib):
    search, _ = handlers(lib)
    assert keys(call(search, query="ferroptosis", collection="Obesity")) == ["FERRO001"]  # subcollections count
    assert keys(call(search, query="ferroptosis", collection="adipose")) == ["FERRO001"]  # last part, any case
    assert keys(call(search, query="ferroptosis", collection="Neuro")) == ["FERRO002"]
    data = call(search, query="ferroptosis", collection="Nope")
    assert data["hits"] == [] and data["coverage"]["verdict"] == "none" and data["warnings"]
    data = call(search, query="thermogenesis", year_from=Y - 4)
    assert sorted(keys(data)) == ["THERM000", "THERM001", "THERM002"] and data["coverage"]["matches_all"] == 3
    data = call(search, query="thermogenesis", year_to=Y - 10)
    assert sorted(keys(data)) == ["THERM005", "THERM006", "THERM007", "THERM008"]
    assert sorted(keys(call(search, query="thermogenesis", year_from=Y - 8, year_to=Y - 5))) == ["THERM003", "THERM004"]


def test_limit_and_size_cap(lib):
    search, _ = handlers(lib)
    data = call(search, query="insulin")
    assert len(data["hits"]) == 10 and all(len(h["passages"]) == 2 for h in data["hits"])
    assert len(call(search, query="insulin", limit="3")["hits"]) == 3
    for limit in (25, 100):
        out = search({"query": "insulin", "limit": limit})
        data = json.loads(out)
        assert len(out) <= 12000 and 10 < len(data["hits"]) <= 25
        assert all(len(h["passages"]) == 1 for h in data["hits"])
        assert len({h["key"] for h in data["hits"]}) == len(data["hits"])  # one entry per paper


def test_doi_check(lib):
    search, _ = handlers(lib)
    data = call(search, doi="https://doi.org/10.1000/FERRO.1")
    check = data["doi_check"]
    assert check["doi"] == "10.1000/ferro.1" and check["held"] is True
    assert [i["key"] for i in check["items"]] == ["FERRO001"] and check["items"][0]["passages"][0]["snippet"]
    assert data["hits"] == [] and data["coverage"] is None
    check = call(search, doi="10.1000/shared.1")["doi_check"]
    assert sorted((i["library"], i["key"]) for i in check["items"]) == [("4805701", "GRP00001"), ("user", "SHARED01")]
    data = call(search, doi="10.9999/not-held", query="ferroptosis")
    assert data["doi_check"] == {"doi": "10.9999/not-held", "held": False, "items": []}
    assert data["hits"] and data["coverage"]["matches_all"] >= 3


def test_search_errors(lib, tmp_path):
    search, _ = handlers(lib)
    for args in ({}, {"query": "   "}, {"query": "x", "year_from": "abc"}, {"doi": "not a doi"}, {"query": ["a"]}):
        data = json.loads(search(args))
        assert data["ok"] is False and data["error"]["code"] == "invalid_argument", args
    empty = tmp_path / "empty"
    search, read = handlers(empty)
    for handler, args in ((search, {"query": "x"}), (read, {"key": "FERRO001"})):
        data = json.loads(handler(args))
        assert data["ok"] is False and data["error"]["code"] == "no_index" and "sync" in data["error"]["hint"]
    assert not (empty / "index.sqlite").exists()  # the tools never create the index
    specs = {s.name: s for s in tools.tool_specs(Settings)}  # no data_root at all
    assert json.loads(specs["zotero_search"].handler({"query": "x"}))["ok"] is False
    assert json.loads(specs["zotero_read"].handler({"key": "X"}))["ok"] is False


def test_tools_do_not_modify_the_index(lib):
    path = lib / "index.sqlite"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    search, read = handlers(lib)
    call(search, query="ferroptosis", collection="Obesity", year_from=2000)
    call(search, doi="10.1000/ferro.1", query="iron")
    call(read, key="LONG0001", query="zeaxanthinmarker")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


# ---------- zotero_read ------------------------------------------------------------------------------

def test_read_by_offset_pages_through_the_exact_text(lib):
    _, read = handlers(lib)
    data = call(read, key="LONG0001", offset=0, max_chars=1000)
    assert data["ok"] is True and data["key"] == "LONG0001" and data["library"] == "user"
    assert data["title"] == "Adipose remodelling" and data["year"] == Y - 6 and data["text_source"] == "ft-cache"
    assert data["text"] == LONG[:1000] and data["offset"] == 0 and data["next_offset"] == 1000
    assert data["total_chars"] == len(LONG)
    pieces, offset = [], 0
    while offset is not None:
        page = call(read, key="LONG0001", offset=offset, max_chars=3000)
        pieces.append(page["text"])
        offset = page["next_offset"]
    assert "".join(pieces) == LONG


def test_read_at_query_match(lib):
    _, read = handlers(lib)
    data = call(read, key="long0001", query="zeaxanthinmarker")  # keys are case-insensitive
    assert "zeaxanthinmarker" in data["text"] and data["warnings"] == []
    assert data["text"] == LONG[data["offset"]:data["offset"] + len(data["text"])]
    assert data["offset"] <= LONG.index("zeaxanthinmarker") and len(data["text"]) == 4000
    data = call(read, key="LONG0001", query="nonexistentword")
    assert data["offset"] == 0 and data["text"] == LONG[:4000] and data["warnings"]


def test_read_caps_and_defaults(lib):
    _, read = handlers(lib)
    assert len(call(read, key="LONG0001", max_chars=999999)["text"]) == 12000  # read_max_chars_cap
    assert len(call(read, key="LONG0001", max_chars="10")["text"]) == 200  # floor
    _, read = handlers(lib, Settings(read_max_chars_default=1500, read_max_chars_cap=5000))
    assert len(call(read, key="LONG0001")["text"]) == 1500
    assert len(call(read, key="LONG0001", max_chars=8000)["text"]) == 5000
    data = call(read, key="LONG0001", offset=-5, max_chars=300)
    assert data["offset"] == 0 and data["text"] == LONG[:300]


def test_read_edge_cases(lib):
    _, read = handlers(lib)
    data = call(read, key="LONG0001", offset=len(LONG) + 10)
    assert data["ok"] is True and data["text"] == "" and data["next_offset"] is None and data["warnings"]
    data = call(read, key="META0001")
    assert data["text_source"] == "metadata" and "body_not_read" in data["flags"]
    assert "fat mass expansion" in data["text"] and data["next_offset"] is None
    data = call(read, key="FERRO001")
    assert data["doi"] == "10.1000/ferro.1" and data["creators"] == ["Dixon, Scott", "Stockwell, Brent"]
    assert data["n_authors"] == 2
    data = call(read, key="NOSUCHKY")
    assert data["ok"] is False and data["error"]["code"] == "not_found"
    data = call(read, key="DUPKEY01")
    assert data["ok"] is False and data["error"]["code"] == "ambiguous" and "4805701" in data["error"]["message"]
    data = call(read, key="DUPKEY01", library="4805701")
    assert data["library"] == "4805701" and "Group library" in data["text"]
    for args in ({}, {"key": ""}, {"key": "LONG0001", "offset": "abc"}):
        data = json.loads(read(args))
        assert data["ok"] is False and data["error"]["code"] == "invalid_argument", args


def test_handlers_never_raise(lib):
    def broken():
        raise RuntimeError("kaboom")
    specs = {s.name: s for s in tools.tool_specs(broken, data_root=lambda: lib)}
    for name in ("zotero_search", "zotero_read"):
        data = json.loads(specs[name].handler({"query": "x", "key": "LONG0001"}))
        assert data["ok"] is False and data["error"]["code"] == "internal_error"
