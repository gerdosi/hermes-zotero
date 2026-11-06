# Task 07 — `zotero_search` (with coverage and DOI check) and `zotero_read`

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code |
| Reasoning | **medium** (the logic is fully specified; high is fine too). Set it in the app's model picker before pasting the prompt. |
| Budget | ≤ 50 tool calls |
| Depends on | task 06b committed (87 tests pass) |
| Done when | `.venv/bin/python -m pytest` shows **106 passed** (87 old + 19 new), checksum matches, report committed |

## Goal

Give the agent the two tools that make the index useful. `zotero_search` finds papers in the local index, returns a few passages per paper and a **coverage block** that says whether the library covers the topic (`strong` / `thin` / `none`); `doi=` checks whether one paper is held. `zotero_read` returns a bounded piece of one paper's text, at the best match for a query or at a character offset, so the agent can page through a paper without loading it whole. Both tools only **read** the index; they never create, change or lock it.

## Facts (reference implementation on Gábor's real index, 6 Nov 2026: 19,290 items, 1,067,135 passages)

- Every FTS5 query below, including the four coverage counts, took 0.06–1.1 s (the 1.1 s was a cold first query for "insulin resistance": 10,469 matching papers). Reading 4,000 characters at offset 10,000,000 of the largest item (a 20.1-million-character encyclopedia, 13,276 passages) took 0.02 s; reading it at a query match took 1.5 s.
- Answer size with `limit` 10 and 2 passages per paper: 6,900–8,300 characters of JSON. With `limit` 25 it would be about 14,000, hence 1 passage per paper above 10 and a 12,000-character cap.
- Within one item, passage `rowid`s are consecutive and in text order (task 06's `upsert` inserts them in one go). 300 random items: passages ordered by `rowid` have increasing `start`, no gaps, and the last `end` equals the text length.
- Requiring every word in one passage is strict. "glucagon receptor antagonist" matches 444 papers, but adding "hepatic glucose output zebrafish" leaves 0. Hence the fallback to any-word hits and the `hint` below; the bundled skill (task 09) will tell the agent to search with 2–4 keywords.
- 87 DOIs occur more than once in the index (same paper in My Library and the group, or duplicates), so a DOI check can return several items.

## Files

```
create  zotcore/search.py
modify  zotcore/tools.py                  (two new tools; zotero_status unchanged)
modify  plugin.yaml                       (provides_tools gains zotero_search and zotero_read)
create  tests/test_07_search_read.py      (verbatim, below)
create  tasks/07-report.md
commit  tasks/07-search-and-read.md, tasks/README.md   (added or updated by the reviewer; commit them as they are)
```

Do not touch `zotcore/index.py`, `zotcore/textsource.py`, `zotcore/zdb.py`, `__init__.py` or any existing test.

## Spec — `zotcore/search.py` (standard library only)

Module constants:

```python
STOPWORDS = frozenset(
    "a an the of on in and or to for with by at from as is are was were be been it its this that these those "
    "what which who how does do did vs versus about into than".split())
MAX_TERMS = 12
POOL = 200                 # top passages examined before grouping them by item
SNIPPET_TOKENS = 24
MAX_SEARCH_CHARS = 12000   # cap on the whole JSON answer of zotero_search
MAX_COLLECTIONS = 3        # collection paths shown per hit
BM25 = "bm25(passages, 2.0, 1.0, 1.0)"   # title counts double; columns are title, section, body
```

`class SearchError(Exception)` with attributes `code`, `message`, `hint` (hint may be `None`). The tools turn it into `err(code, message, hint)`.

### Opening the index

`open_index(path) -> sqlite3.Connection`: if the file does not exist, raise `SearchError("no_index", "The Zotero index has not been built yet.", "Run `hermes zotero sync` in a terminal, then try again.")`. Otherwise open it **read-only**: `sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)`. Never use `Index(...)` here: it creates files and runs `PRAGMA`s. TEMP tables still work on a read-only connection.

### Query terms

`query_terms(query) -> list[str]`:

1. Tokens are `re.findall(r"[^\W_]+", query)`, lower-cased. This is the same split as FTS5's `unicode61` tokenizer, so `SCD-1` gives `scd`, `1`.
2. Drop tokens in `STOPWORDS`, **unless** that would leave nothing; then keep them all (`"the of"` → `["the", "of"]`).
3. Remove duplicates, keeping first occurrence. Keep at most `MAX_TERMS`; if more were dropped, the search adds the warning `only the first 12 query terms were used`.

Never pass the user's text to `MATCH` directly. Build expressions from the terms, each wrapped in double quotes (terms contain only letters and digits, so quoting is always safe and `AND`/`OR`/`NOT`/`NEAR`/`*`/`:` lose their meaning):

- all-terms expression: `"a" "b" "c"` (FTS5 implicit AND: one passage contains every term)
- any-term expression: `"a" OR "b" OR "c"`

### Filters (scope)

Filters: `library` (string), `collection` (string), `year_from`, `year_to` (ints). With no filter, search the whole index (**all indexed libraries**: groups are already opt-in through the `libraries` setting). With any filter:

1. Select `library, item_key, collections` from `items`, applying `library = ?`, `year >= ?`, `year <= ?` in SQL (items with no year drop out when a year filter is set).
2. Collection match, in Python: the item matches when, compared with `casefold()`, any of its collection paths **equals** the argument, **starts with** argument + `" / "` (subcollections), or its **last** `" / "` part equals the argument.
3. Put the surviving pairs in `CREATE TEMP TABLE IF NOT EXISTS scope (library TEXT, item_key TEXT, PRIMARY KEY (library, item_key))` (clear it first), and add `JOIN temp.scope s ON s.library = m.library AND s.item_key = m.item_key` to every query below.
4. If the scope is empty, add the warning `no indexed items match the filters` (the result then has no hits and verdict `none`).

All passage queries join the map: `FROM passages p JOIN passage_map m ON m.rowid = p.rowid [scope join] WHERE passages MATCH ?`.

### Hits

`limit` papers. `per_item` = 2 passages when `limit <= 10`, else 1.

1. Run the **all** expression, then (if fewer than `limit` papers were found) the **any** expression, each as
   `SELECT m.library, m.item_key, p.start, CASE WHEN p.section = p.title THEN '' ELSE p.section END, snippet(passages, 2, '«', '»', '…', 24) ... ORDER BY bm25(passages, 2.0, 1.0, 1.0) LIMIT max(POOL, limit * 20)`.
2. Walk the rows in order. A paper seen for the first time gets the next slot (until `limit` papers) and remembers which pass found it (`"all"` or `"any"`). Add the row as a passage only if it came from that same pass and the paper has fewer than `per_item` passages. So papers matching every term always come first, and a paper is listed once.
3. Passage: `{"offset": start, "snippet": snippet}` plus `"section"` only when the section is non-empty.
4. Hit (one `items` row per paper): `key`, `library`, `title`, `first_author` (first element of `creators`, or `""`), `n_authors`, `year`, `doi` (`None` when empty), `collections` (first 3 paths), `text_source`, `match` (`"all"` / `"any"` / `"doi"`), `passages`, and `flags` only when non-empty.

### Coverage

Computed over the same scope, from **distinct papers** (`SELECT COUNT(*) FROM (SELECT DISTINCT m.library, m.item_key ...)`):

- `matches_all`: papers with at least one passage containing every term.
- `matches_any`: papers with at least one passage containing any term.
- `recent`: papers counted in `matches_all` whose `items.year >= this_year - coverage_recent_years + 1` (with the default 5 years in 2026: 2022 or later). `this_year` is `date.today().year`; `search` takes an optional `this_year` argument for tests.
- `recent_years`: the setting. `newest_year`: highest year among the `matches_all` papers, `None` when there are none.
- `verdict`: `"none"` when `matches_all == 0`; `"strong"` when `matches_all >= coverage_strong_min` **and** `recent >= coverage_recent_min`; otherwise `"thin"`.
- `hint`, only when `matches_all == 0`, `matches_any > 0` and there is more than one term: `"No passage contains every term; retry with fewer or broader terms before using the web."`

### DOI check

`doi` argument: `value = normalize_doi(doi)` (from `zdb`). If it does not start with `10.` or has no `/`, raise `SearchError("invalid_argument", "not a DOI: ...", "Pass a DOI such as 10.1038/nature12345.")`. Otherwise select every item with `doi = value` (ordered by library, key) and return

```json
{"doi": "<normalized>", "held": true, "items": [<hit with match "doi" and exactly one passage>]}
```

The passage is `{"offset": o, "snippet": <the first 300 characters of the item's text from offset o, stripped>}`, where `o` is the item's best passage for the query terms (see `best_offset` below) or 0 when there is no query or no match. Not held: `{"doi": value, "held": false, "items": []}`.

### `search(con, settings, *, query=None, doi=None, library=None, collection=None, year_from=None, year_to=None, limit=10, this_year=None) -> dict`

- If there are no terms and no `doi`: `SearchError("invalid_argument", "query is empty", "Pass a few keywords, or doi= to check one paper.")`. A query of only punctuation (`"*:-()"`) has no terms.
- Result keys, in this order: `query` (the original string or `None`), `terms`, `doi_check` (**only** when `doi` was given), `hits`, `coverage`, `index_last_sync` (state `last_sync`, or `None`), `warnings` (list).
- With terms: hits and coverage as above. Without terms (doi only): `hits = []`, `coverage = None`.

### Reading

`best_offset(con, library, key, terms) -> int | None`: `lo, hi` = `MIN(rowid), MAX(rowid)` from `passage_map` for the item; `None` if no terms or no passages. Try the all expression, then the any expression:
`SELECT p.start FROM passages p JOIN passage_map m ON m.rowid = p.rowid WHERE passages MATCH ? AND p.rowid BETWEEN ? AND ? AND m.library = ? AND m.item_key = ? ORDER BY bm25(...) LIMIT 1`. The `rowid` range keeps FTS5 fast on large items; the `m.` conditions keep it exact.

`read_window(con, library, key, offset, max_chars) -> (text, end, total, section)`:

1. Fetch `m.rowid, p.start, p."end"` for the item ordered by `m.rowid` (quote `"end"`: it is an SQL keyword). `total` = the largest `end` (0 if none).
2. Keep spans with `end > offset` and `start < offset + max_chars`. Walk them with `cursor = offset`: skip a span if `end <= cursor`; fetch its `section, body` by rowid; the first span used gives `section`; if `start > cursor`, append `"\n"` and set `cursor = start` (a whitespace-only stretch was not stored); append `body[cursor - start : min(end, limit) - start]`, set `cursor` to that end, stop at `limit`.
3. Return the joined text, `cursor` (as `end`), `total`, `section`. Fetch bodies only for the spans you use: the largest item has 13,276 passages.

`find_item(con, key, library=None) -> (library, key)`: upper-case and strip the key. Empty → `invalid_argument` ("key is required"). No row → `SearchError("not_found", "no item with key K in the index", "Use a key from zotero_search results; run `hermes zotero sync` if the paper is new.")`. Rows in more than one library and no `library` given → `SearchError("ambiguous", "key K exists in libraries 4805701, user", "Pass library= as well.")` (libraries sorted, comma-separated).

`read_item(con, *, key, library=None, query=None, offset=None, max_chars) -> dict`:

- Position: if `offset` is given, use it (and if a query was also given, warn `offset given, so query was not used to position the passage`). Else, if a query is given, `best_offset(...)`; when that is `None`, use 0 and warn `query terms not found in this item; showing the start`. Else 0.
- `read_window(...)`. If the text has characters but `offset >= total`, warn `offset <O> is past the end of the text (<T> characters)`.
- Result keys: `key`, `library`, `title`, `creators` (first 3), `n_authors`, `year`, `doi` (`None` when empty), `publication` (`None` when empty), `text_source`, `flags` (list), `total_chars`, `offset`, `next_offset` (`end`, or `None` when `end >= total`), `section` (`None` when empty), `text`, `warnings`.

## Spec — `zotcore/tools.py`

Add two tools after `zotero_status`; keep `zotero_status` exactly as it is. Both handlers are wrapped with `safe`, call `settings_provider()` first (so a broken provider becomes `internal_error`), open the index with `open_index(Path(data_root()) / "index.sqlite")`, close it in `finally`, and turn `SearchError` into `err(e.code, e.message, e.hint)`. With `data_root is None`, return `err("no_index", "plugin data dir unavailable")`.

Argument parsing (tolerant, because models send `"5"` for 5):

- integers accept `int` or a digit string (optionally with a leading `-`); `bool` and anything else → `err("invalid_argument", "<name> must be an integer")`. Missing, `None` or `""` → default.
- strings accept `str` (stripped; empty → `None`) or `int` (converted, so `library=4805701` works); anything else → `err("invalid_argument", "<name> must be a string")`.

`zotero_search`: `query`, `doi`, `library`, `collection` (strings); `year_from`, `year_to` (integers); `limit` (integer, default 10, clamped to 1–25). Call `search(...)` and return `ok(**payload)`. If that JSON string is longer than `MAX_SEARCH_CHARS`, remove hits from the end until it fits and set `payload["hits_dropped_for_size"]` to the number removed.

`zotero_read`: `key`, `library`, `query` (strings); `offset` (integer, clamped to ≥ 0); `max_chars` (integer, default `settings.read_max_chars_default`, clamped to 200 … `settings.read_max_chars_cap`). Call `read_item(...)` and return `ok(**payload)`.

Descriptions (Tool Search shows the first ~60 characters; the tests require "Zotero" there):

```python
SEARCH_DESC = ("Zotero library search: find papers the user already has, by full text, offline. "
               "Returns ranked papers with short passages and a coverage verdict (strong / thin / none) "
               "for the topic; doi= checks whether one specific paper is held. Search here before the web.")
READ_DESC = ("Zotero paper reader: read a bounded passage of one paper from the user's library, by item key, "
             "at the best match for a query or at a character offset. Use keys from zotero_search.")
```

Schemas (`{"name": ..., "description": ..., "parameters": ...}`, as for `zotero_status`):

```python
SEARCH_SCHEMA = {"type": "object", "properties": {
    "query": {"type": "string", "description": "Keywords, e.g. 'SCD1 ferroptosis'. Every word counts."},
    "doi": {"type": "string", "description": "Check whether this DOI is in the library."},
    "collection": {"type": "string", "description": "Only this Zotero collection (and its subcollections)."},
    "library": {"type": "string", "description": "'user' or a group ID. Default: all indexed libraries."},
    "year_from": {"type": "integer"},
    "year_to": {"type": "integer"},
    "limit": {"type": "integer", "minimum": 1, "maximum": 25, "description": "Papers to return (default 10)."}}}
READ_SCHEMA = {"type": "object", "properties": {
    "key": {"type": "string", "description": "Item key from zotero_search, e.g. 'ABCD2345'."},
    "library": {"type": "string", "description": "Only needed when the key exists in two libraries."},
    "query": {"type": "string", "description": "Start at the passage that best matches these words."},
    "offset": {"type": "integer", "minimum": 0, "description": "Start at this character (next_offset of a previous read)."},
    "max_chars": {"type": "integer", "description": "Characters to return (default and cap set by the user)."}},
    "required": ["key"]}
```

`plugin.yaml`: `provides_tools` lists `zotero_status`, `zotero_search`, `zotero_read` (test_01_manifest checks that it matches the registered tools).

## Acceptance test (copy verbatim, then verify the checksum)

| File | SHA-256 |
| --- | --- |
| `tests/test_07_search_read.py` | `fc19bc066caf1128cd1e83fab7917406d3d61cb08e8a862b480fd47073a541f2` |

The test builds a 50-item library once (module-scoped fixture), syncs it with task 06's `sync`, and calls the tools through `tool_specs(...)` exactly as Hermes would.

### `tests/test_07_search_read.py`

```python
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
```

## Commands

```bash
.venv/bin/python -m pytest                          # expect: 106 passed
shasum -a 256 tests/test_07_search_read.py
```

Finish with `tasks/07-report.md` and one commit: `task 07: zotero_search and zotero_read`.

## Live check (Gábor, in the same or a new Claude Code session, after the commit)

Expected values come from the reference implementation on your index of 6 Nov (19,290 items). Small differences are fine if you added papers since.

1. Direct check, no Hermes involved. Run this from the repo and paste the output into the report under `## Live check`:

```bash
.venv/bin/python - <<'EOF'
import json, time
from pathlib import Path
from zotcore import tools
from zotcore.settings import Settings
root = Path.home() / ".hermes/plugin-data/hermes-zotero"
specs = {s.name: s.handler for s in tools.tool_specs(lambda: Settings(libraries=("user", "4805701")), data_root=lambda: root)}
def run(name, **args):
    t = time.time(); out = specs[name](args); d = json.loads(out)
    print(f"\n{name} {args}  {time.time() - t:.2f}s  {len(out)} chars")
    if not d["ok"]: print(d); return
    if name == "zotero_read":
        print({k: d[k] for k in ("key", "offset", "next_offset", "total_chars", "section")}); return
    print("coverage:", d["coverage"]); print("top:", [h["key"] for h in d["hits"][:3]])
    if "doi_check" in d: print("doi:", d["doi_check"]["held"], [i["key"] for i in d["doi_check"]["items"]])
run("zotero_search", query="ferroptosis")
run("zotero_search", query="glucagon receptor antagonist hepatic glucose output zebrafish")
run("zotero_search", query="glucagon receptor antagonist")
run("zotero_search", query="brown adipose tissue thermogenesis", collection="Obesity")
run("zotero_search", query="ketogenic diet", library="4805701")
run("zotero_search", query="insulin resistance", limit=25)
run("zotero_search", doi="10.1016/j.immuni.2024.03.019")
run("zotero_search", doi="10.1002/alz.12362")
run("zotero_search", doi="10.1234/not.held.2026", query="ferroptosis")
run("zotero_read", key="RMRFLJX6", query="peroxisomes ether phospholipids")
run("zotero_read", key="N4AKAC5N", query="vitamin K coagulation")
run("zotero_read", key="N4AKAC5N", offset=10000000)
EOF
```

Expected:

| Call | Expected |
| --- | --- |
| `ferroptosis` | matches_all 200, recent 134, newest_year 2026, **strong**; top RMRFLJX6, ZIYQHNNR, 8EA5FWG5 |
| `glucagon … zebrafish` | matches_all 0, **none**, with the `hint`; hits all `match: any` |
| `glucagon receptor antagonist` | matches_all 444, recent 67, **strong** |
| `brown adipose …`, collection Obesity | matches_all 50, recent 23, **strong**; top JHMERHPJ |
| `ketogenic diet`, library 4805701 | matches_all 42, recent 10, newest_year 2022, **strong** |
| `insulin resistance`, limit 25 | at most 12,000 chars; maybe `hits_dropped_for_size` |
| doi `10.1016/j.immuni.2024.03.019` | held true, RMRFLJX6 |
| doi `10.1002/alz.12362` | held true, two items (RB659BDL in user, ZFFUB9WK in 4805701) |
| doi `10.1234/not.held.2026` + `ferroptosis` | held false; coverage strong |
| read RMRFLJX6 at query | offset 17933 |
| read N4AKAC5N at query | offset 18472198, section "Assessment of Vitamin K Status" |
| read N4AKAC5N at offset 10,000,000 | next_offset 10004000, total_chars 20125419 |

Every call should take under about 2 seconds.

2. Through Hermes. Restart the gateway first, or Hermes keeps the old code: `hermes gateway restart`. Then ask Hermes: "Use zotero_search to check whether my library covers ferroptosis in adipocytes, then read the best passage with zotero_read." Paste the two tool calls it made (names and arguments) and the coverage verdict into the report.

## Out of scope

Annotations mode, the citation line, the `zotero_sync` tool (task 08); the skill and description tuning (task 09). Do not change ranking weights or coverage thresholds: calibration on your past prompts comes with task 09.
