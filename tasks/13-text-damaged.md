# Task 13 — The damaged-text flag `text_damaged`

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code |
| Reasoning | **low** (two verbatim files and a small patch). Set it in the app's model picker before pasting the prompt. |
| Budget | ≤ 20 tool calls |
| Depends on | task 12 committed (214 tests pass) |
| Done when | `.venv/bin/python -m pytest` shows **224 passed** (214 old + 10 new), the checksums match, report committed |

## Goal

Some PDFs convert badly: the words are there but run together, or letters are missing. Search misses such papers, and an agent that quotes them quotes garbage. After this task a paper whose text shows clear signs of that carries the flag `text_damaged` in search hits, reads and the status counts, and the bundled skill tells the agent what to do with it.

## Calibration (Gábor's corpus, 18,331 Markdown files, 12 Nov 2026)

Plan v4 made this task conditional: calibrate first, ship only if the detector is reliable. Result: **ship, with different signals than the plan proposed.**

- **The plan's signal does not work.** It proposed counting common words with the letter t dropped ("he", "ha", "wih" against "the", "that", "with"). On the corpus the dropped forms are almost always something else: `ha` and `han` are hyaluronan and a surname, `differen` and `effec` come from words hyphenated at line ends, `daa` and `boh` are abbreviations. No paper today shows a letter t missing throughout the body.
- **What the corpus does have,** found by measuring word shapes across all files and reading samples:

| Kind | Sign | Papers flagged | Read by eye |
| --- | --- | --- | --- |
| Words run together ("Onestudyofadultshadahighsecondaryattackrate") | 5 or more distinct words of 25+ letters, and at least 2 per 1,000 words | 383 | 24 sampled, all damaged; 40 more read below and around the threshold, all run-together text apart from one file of DNA sequences, which the rule now skips |
| Lost ligatures ("signicant eect": fi, fl or ff dropped) | 5 or more words from a fixed list of such forms | 24 | all 24 damaged |
| Fragments ("a e hi i e b idi g") | 35% or more one-letter words | 4 | all 4 damaged |
| Unreadable font encoding | 15% or more words of 4+ letters without a vowel | 1 | damaged |

- **412 papers (2.2%) get the flag.** Not flagged, on purpose: long chemical names (they repeat, so they are few distinct words), DNA and protein sequences, texts under 500 words, texts mostly in a non-Latin script, and the structured-tables part (table cells are not prose). The Czech and German papers in the corpus are not flagged.
- **The flag is one-sided.** Set means damage was found. Not set means no sign was found, not that the text is intact: milder cases stay unflagged (a few run-together words per page; "fi rst" written with a stray space, about 100 papers).
- Only the first 60,000 characters of the prose are examined. The check takes a few milliseconds per paper, so a full rebuild gets roughly 30 to 60 s slower; ordinary syncs do not change.

## Design in short

- `zotcore/textquality.py`: `damage(text)` returns the kind (`run_together`, `fragments`, `unreadable`, `ligatures`) or `None`. A pure function, standard library only.
- `zotcore/textsource.py`: `choose_text` adds `text_damaged` for Markdown and for Zotero's text cache; the check runs on the text before the `## Tables (structured)` marker. Metadata-only items are not checked.
- `zotcore/index.py`: `SCHEMA_VERSION` goes from 2 to 3, so the next sync rebuilds the index once and every paper is checked. (Flags are stored when a paper is indexed; without the bump only new and changed papers would get the flag.)
- Only the flag is stored, not the kind.

## Files

```
create  zotcore/textquality.py                    (verbatim, below)
create  tests/test_13_text_damage.py              (verbatim, below)
replace skills/zotero-library/SKILL.md            (verbatim, below)
modify  zotcore/textsource.py, zotcore/index.py   (the patch below)
create  tasks/13-report.md
commit  tasks/13-text-damaged.md, tasks/README.md   (added or updated by the reviewer; commit them as they are)
```

Do not touch any other file.

## Steps

1. Run `.venv/bin/python -m pytest` first: 214 passed.
2. From the repo root, run this. It writes the three verbatim files and puts the patch into the system's temporary folder, and prints a SHA-256 for each:

```python
import hashlib, pathlib, re, tempfile
md = pathlib.Path("tasks/13-text-damaged.md").read_text(encoding="utf-8")
for name, body in re.findall(r"<!-- file: (\S+) -->\n```\w*\n(.*?)\n```\n<!-- /file -->", md, re.S):
    out = pathlib.Path(tempfile.gettempdir()) / "task13.patch" if name == "PATCH" else pathlib.Path(name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body + "\n", encoding="utf-8", newline="\n")
    print(hashlib.sha256(out.read_bytes()).hexdigest(), out)
```

3. Compare the printed checksums with the table below. A mismatch means the copy went wrong: stop and fix it, do not edit the files.
4. Apply the patch from the repo root: `git apply --check <path printed for the patch>`, then `git apply <the same path>`. If it does not apply, make the same change by hand; the tests decide.
5. Run `.venv/bin/python -m pytest`: 224 passed.
6. Fill in the report `tasks/13-report.md` (the template is in the project rules file) and make one commit: `task 13: damaged-text flag`.

### Checksums

| File | SHA-256 |
| --- | --- |
| `zotcore/textquality.py` | `68eabac795df050c398ec6c40f07d8b7cf0fa046f1160d2ec875eec0307c3fa6` |
| `tests/test_13_text_damage.py` | `9b6e3aa2fc742d69a4a380a4f6908b91e6b8daafe2e48fac1e20be1aebb81f13` |
| `skills/zotero-library/SKILL.md` | `6238c8a8c4d88bd44b39d42a4de4689546aaff6603fbeb839e17c2525c52bb1e` |
| the patch file | `5dc55007d2462de1a2f1782d76ff883602bccf64ff4d102d97a717ff9346a523` |
| `zotcore/textsource.py` after the patch | `6cf83894a785af198407eaa09d8466ce480cee35efc51d6dc48dffaed3a40886` |
| `zotcore/index.py` after the patch | `9efac12712b2ac5c4969e48a3e905affa0e3d99164ea2805d36a80880ae3693a` |

## Spec — `zotcore/textquality.py`

<!-- file: zotcore/textquality.py -->
```python
"""Signs that a paper's text was damaged when its PDF was converted (standard library only)."""
from __future__ import annotations

import re

SAMPLE_CHARS = 60_000       # only the start of a long text is examined
MIN_WORDS = 500             # shorter texts are not judged
LONG_WORD = 25              # letters; longer "words" are nearly always several words without spaces
RUN_ON_PER_1000 = 2.0       # distinct long words per 1,000 words ...
RUN_ON_MIN = 5              # ... and at least this many of them
FRAGMENT_SHARE = 0.35       # share of one-letter words
NO_VOWEL_SHARE = 0.15       # share of words of 4+ letters without a vowel
LIGATURE_MIN = 5            # words that lost fi / fl / ff (English)

_WORD = re.compile(r"[^\W\d_]+")
_VOWELS = frozenset("aeiouyàáâãäåæèéêëìíîïòóôõöøùúûüýÿāăąēęěīıōőœūůűų")
_SEQUENCE = frozenset("acgtun")
_LIGATURE = re.compile(
    r"\b(?:signicant|signicantly|specic|specically|eect|eects|eective|dierent|dierence|dierences|identied|"
    r"dened|inammation|inammatory|ecient|ecacy|coecient|sucient|insucient|deciency|decient|dicult|conrmed|"
    r"inuence|classied|modied|puried|quantied|uorescence|uorescent)\b")


def damage(text: str) -> str | None:
    """Kind of damage found in the text, or None: 'run_together', 'fragments', 'unreadable', 'ligatures'.

    None means no sign was found, not that the text is intact. Texts that are short or mostly
    in a non-Latin script are not judged.
    """
    sample = text[:SAMPLE_CHARS]
    words = _WORD.findall(sample)
    if len(words) < MIN_WORDS:
        return None
    letters = sum(map(len, words))
    if sum(len(w) for w in words if ord(w[0]) < 0x250) < 0.9 * letters:
        return None
    lower = [w.lower() for w in words]
    long_words = {w for w, raw in zip(lower, words)
                  if len(w) >= LONG_WORD and not raw.isupper() and not set(w) <= _SEQUENCE}
    if len(long_words) >= RUN_ON_MIN and 1000 * len(long_words) / len(words) >= RUN_ON_PER_1000:
        return "run_together"
    if sum(1 for w in words if len(w) == 1) / len(words) >= FRAGMENT_SHARE:
        return "fragments"
    four = [w for w in lower if len(w) >= 4]
    if four and sum(1 for w in four if not _VOWELS.intersection(w)) / len(four) >= NO_VOWEL_SHARE:
        return "unreadable"
    if len(_LIGATURE.findall(sample.lower())) >= LIGATURE_MIN:
        return "ligatures"
    return None
```
<!-- /file -->

## Spec — the patch

<!-- file: PATCH -->
```diff
diff --git a/zotcore/index.py b/zotcore/index.py
index c2aac6d..74fbc4e 100644
--- a/zotcore/index.py
+++ b/zotcore/index.py
@@ -14,7 +14,7 @@ from .textsource import TextResult, build_passages, choose_text, text_signature
 from .zdb import list_items, libraries as zotero_libraries, load_items, open_snapshot
 
 CHUNK = 500
-SCHEMA_VERSION = 2   # 2: passages know their kind, structured tables are listed (0.2.0)
+SCHEMA_VERSION = 3   # 2: passage kinds and the table list; 3: every paper checked for damaged text (0.2.0)
 MAX_ITEM_WARNINGS = 20
 
 SCHEMA = (
diff --git a/zotcore/textsource.py b/zotcore/textsource.py
index 88bdfd6..dd3440a 100644
--- a/zotcore/textsource.py
+++ b/zotcore/textsource.py
@@ -7,7 +7,8 @@ from dataclasses import dataclass
 from pathlib import Path
 
 from .frontmatter import is_true, split_front_matter
-from .tables import Table, prepare
+from .tables import MARKER, Table, prepare
+from .textquality import damage
 from .zdb import normalize_doi
 
 MIN_BYTES = 200
@@ -143,19 +144,26 @@ def _read(path: Path) -> str:
         return fh.read()
 
 
+def _damage_flag(text: str) -> tuple[str, ...]:
+    """('text_damaged',) when the prose (structured tables left aside) shows conversion damage."""
+    marker = MARKER.search(text)
+    return ("text_damaged",) if damage(text[:marker.start()] if marker else text) else ()
+
+
 def choose_text(item, data_dir, corpus=None) -> TextResult:
     """Best available text: Markdown, then Zotero's cache, then title and abstract."""
     source, path, att, signature = _select(item, data_dir, corpus)
     if source == "markdown":
         values, body = split_front_matter(_read(path))
         flags = ("ocr",) if is_true(values.get("ocr")) else ()
-        return TextResult("markdown", body, str(path), flags, signature)
+        return TextResult("markdown", body, str(path), flags + _damage_flag(body), signature)
     if source == "ft-cache":
         flags: tuple[str, ...] = ()
         if (att.indexed_pages is not None and att.total_pages is not None
                 and att.indexed_pages < att.total_pages):
             flags = ("truncated",)
-        return TextResult("ft-cache", _read(path), str(path), flags, signature)
+        text = _read(path)
+        return TextResult("ft-cache", text, str(path), flags + _damage_flag(text), signature)
     text = "\n\n".join(p for p in (item.title, item.abstract) if p)
     flags = ("body_not_read",)
     if any(a.content_type == "application/pdf" for a in _stored(item)):
```
<!-- /file -->

## Spec — `skills/zotero-library/SKILL.md`

Reviewer-written; replace the file with this, byte for byte. Besides the new bullet, a few sentences were shortened to stay under the 4,000-character limit that an earlier test sets.

<!-- file: skills/zotero-library/SKILL.md -->
```markdown
---
name: zotero-library
description: "Research questions: check the user's Zotero library first"
version: 0.2.0
metadata:
  hermes:
    tags: [zotero, literature, research, citations, local-first]
---

# Zotero library first

The hermes-zotero plugin keeps a local, read-only index of the user's Zotero library. For any question about scholarly literature, a specific paper, or the user's own highlights and notes, search the library before the web. The tools never change Zotero.

## Search

1. Call `zotero_search` with 2-4 distinctive keywords, not a sentence: `SCD1 ferroptosis`, not "what does SCD1 do in ferroptosis". Use scientific names, not brand names (`tirzepatide`, not Mounjaro). A hit with `match: all` has one passage holding every word; `match: any` hits hold only some and are weaker evidence.
2. Check `terms` in the result: stop words and words like the "a" in Lp(a) are dropped. If the key word is missing, rephrase.
3. When the user names a collection, tag, year range or group, pass `collection`, `tag`, `year_from`, `year_to` or `library`. Filters also narrow the coverage counts, so judge gaps from a search without them. To check one paper, pass `doi` and read `doi_check.held`.
4. Let `coverage.verdict` decide where to look:
   - `strong`: answer from the library.
   - `thin`: answer from the library, then use the web only for what is missing; say which source is which.
   - `none` with a `hint`: no passage holds every word. Retry with fewer or broader words before treating it as a gap.
   - `none` without a hint: the library has nothing on it. Say so, then use the web.

## Read before citing

A snippet is a search hit, not evidence. For the 3-5 best papers, call `zotero_read` with `key` and `query`: it starts at the best-matching passage. Page on with `offset` = `next_offset` for later parts. Ask for what the question needs (`max_chars` 1500-4000), never a whole paper.

- Cite with the `citation` field. `approximate: true` means it was built from the index, not by Zotero: check the details before giving a formatted reference.
- Flags `body_not_read` or `scanned_or_empty`: the body is not in the index (title and abstract only). `truncated`: only the first pages are. Do not report results you have not read.
- Flag `ocr`: the text was read from a scan, so digits and symbols may be wrong. Say so when you quote numbers from it.
- Flag `text_damaged`: words run together or letters are missing in the body. Rely on the title and abstract, quote no damaged words; searches can miss such a paper.
- `mode` = `annotations` returns the user's highlights, comments and notes on the paper. `author: user` marks the user's own words; quote them as theirs. Any other author is a group member or the PDF's creator.

## Numbers and tables

For numbers (baseline values, effect sizes, doses), use the papers' tables, which are kept as pipe rows:

- `zotero_search` with `in_tables` = true searches table cells only. Its coverage then counts tables only: never judge a gap from it.
- A passage with `kind: table` names its `table`. `zotero_read` with `mode` = `tables` and that `table` returns the whole table; without `table` it lists the paper's tables.
- Cells are the PDF's own strings; a long table comes in pieces that repeat the header. Check header and units before quoting a number.

## Keep the index fresh

- Error `no_index`: ask the user to run `hermes zotero sync` once in a terminal (a few minutes for a large library).
- Error `index_outdated` (after a plugin update): call `zotero_sync` until it returns `done: true`.
- `zotero_status` says whether the index is `ready` and gives a `hint` when Zotero has changed since the last sync.
- When the user has added papers, or the hint says so, call `zotero_sync`. While it returns `done: false`, call it again.

## Limits

- Use these tools, not other ways of opening Zotero's database or the plugin's index.
- Quote short passages with their citation; do not paste whole papers into the answer.
```
<!-- /file -->

## Acceptance tests — `tests/test_13_text_damage.py`

<!-- file: tests/test_13_text_damage.py -->
```python
import json
import re
import sqlite3
from pathlib import Path

import pytest

from tests.zfixture import ZoteroFixture
from zotcore import tools
from zotcore.index import SCHEMA_VERSION, Index, sync
from zotcore.settings import Settings
from zotcore.textquality import damage
from zotcore.textsource import MarkdownCorpus

ROOT = Path(__file__).resolve().parents[1]
SENTENCE = "The metabolic response of adipose tissue to prolonged fasting was measured in twelve healthy volunteers. "
CLEAN = SENTENCE * 60                                        # 900 words
RUN_ONS = ["themetabolicresponseofadiposetissue", "wasmeasuredintwelvehealthyvolunteers",
           "toprolongedfastinginhealthyvolunteers", "Onestudyofadultshadahighsecondaryattackrate",
           "carbohydrateoxidationandfatstorage", "Thisisconsistentwithourresultsand"]


def with_words(extra, base=CLEAN):
    return base + " ".join(extra) + "\n"


# ---------- the detector --------------------------------------------------------------------------------

def test_clean_text_has_no_sign_of_damage():
    assert damage(CLEAN) is None
    assert damage("# Title\n\n## Results\n\n" + CLEAN + "\n\n| a | b |\n|---|---|\n| 1 | 2 |\n") is None


def test_words_run_together():
    assert damage(with_words(RUN_ONS[:5])) == "run_together"          # 5 distinct long words in about 900
    assert damage(with_words(RUN_ONS[:4])) is None                    # four are not enough
    assert damage(with_words(RUN_ONS[:5], base=CLEAN * 3)) is None    # 5 in about 2,700 words: under 2 per 1,000
    assert damage(with_words(RUN_ONS[:1] * 40)) is None               # the same long word again and again
    jama = " ".join("".join(w.capitalize() for w in SENTENCE.split()[n:n + 6]) + str(n) for n in range(10)) * 90
    assert damage(jama) == "run_together"


def test_long_names_and_sequences_are_not_damage():
    chemistry = ["glycosylphosphatidylinositol", "lysophosphatidylethanolamine", "methylenetetrahydrofolate"] * 30
    assert damage(with_words(chemistry)) is None                       # few distinct words, however often
    dna = ["GAGGCTTCTTCGCGGGCGGCGCTTGGCGATTACA", "accatcatcagagattatcatgtctcagtttgat", "ttagaactggctttgaagtatattcactggtagc",
           "IAIPTNFTISVTTEILPVSMTKTSVDCTMYICGDSTECSNLLLQYG", "acagtttaaacagcaaacaattcaaacaaaagcagg"]
    assert damage(with_words(dna)) is None


def test_fragments_unreadable_and_lost_ligatures():
    fragments = "a e hi i e b idi g addi i a i f a i i he b ief e ai h he i e i a icab e e e a f d " * 40
    assert damage(fragments) == "fragments"
    cipher = "XWLOL]LQJ KRVW SLQRF\\WRVLV PDFKLQHU\\ ORFDWHG LQ OLSLG UDIWV LQWHJULW\\ RI WKH KRVW " * 60
    assert damage(cipher) == "unreadable"
    lost = CLEAN + "A signicant eect was identied in dierent groups with sucient power. "
    assert damage(lost) == "ligatures"
    assert damage(CLEAN + "A signicant eect was seen. ") is None       # fewer than five such words


def test_short_and_non_latin_texts_are_not_judged():
    assert damage("") is None and damage(" ".join(RUN_ONS)) is None
    assert damage(with_words(RUN_ONS, base=SENTENCE * 20)) is None      # under 500 words
    russian = "Влияние длительного голодания на метаболизм жировой ткани изучали у двенадцати здоровых добровольцев. " * 60
    assert damage(russian + " ".join(RUN_ONS)) is None
    czech = "Parametr vyjadřuje pokles hmotnosti dosažené po bariatrické intervenci jako procento z nadměrné hmotnosti. " * 60
    german = "Die Wirkung des Fastens auf den Stoffwechsel des Fettgewebes wurde bei zwölf gesunden Probanden gemessen. " * 60
    assert damage(czech) is None and damage(german) is None


def test_only_the_start_of_a_long_text_is_examined():
    assert len(CLEAN * 10) > 60_000
    many = [RUN_ONS[n % 6] + word for n, word in enumerate(SENTENCE.lower().replace(".", "").split() * 2)]
    assert len(set(many)) == 30
    assert damage(CLEAN * 10 + " ".join(many)) is None                  # damage after the first 60,000 characters
    assert damage(" ".join(many) + " " + CLEAN * 10) == "run_together"


# ---------- through the index ---------------------------------------------------------------------------

DAMAGED = "# Run together\n\n" + with_words(RUN_ONS)
TABLES = ("## Tables (structured)\n\nNote.\n\n### Table 1\n\n<table>\n<tr><th>e n i t i n r a c</th></tr>\n"
          + "".join(f"<tr><td>{' '.join('abcdefghij')} {n}</td></tr>\n" for n in range(400)) + "</table>\n")


def make_library(tmp):
    z = ZoteroFixture(tmp / "Zotero")
    md = tmp / "md"
    md.mkdir()
    papers = {"DAMAGED1": ("10.1000/dam.1", DAMAGED),
              "OCRDAMAG": ("10.1000/dam.2", "---\nspec: 1\nocr: true\n---\n" + DAMAGED),
              "CLEANMD1": ("10.1000/clean.1", "# Clean\n\n" + CLEAN),
              "CLEANTAB": ("10.1000/clean.2", "# Clean with letter-spaced table cells\n\n" + CLEAN + "\n" + TABLES)}
    for key, (doi, text) in papers.items():
        i = z.add_item(key, fields={"title": f"Paper {key}", "DOI": doi})
        z.add_attachment(i, "A" + key[1:])
        (md / ("doi_" + doi.replace("/", "_") + ".md")).write_text(text, encoding="utf-8")
    i = z.add_item("CACHEDAM", fields={"title": "Damaged cache paper"})
    z.add_attachment(i, "PDFCACHD", ft_text=with_words(RUN_ONS), indexed_pages=2, total_pages=9)
    i = z.add_item("METAONLY", fields={"title": "Metadata only", "abstractNote": " ".join(RUN_ONS * 200)})
    z.add_attachment(i, "PDFMETA1")
    return z, md


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lib13")
    z, md = make_library(tmp)
    root = tmp / "pd"
    index = Index(root / "index.sqlite")
    assert sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md)).indexed == 6
    index.close()
    z.close()
    return root


def call(root, name, **args):
    settings = Settings()
    specs = {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root)}
    return json.loads(specs[name].handler(args))


def test_flag_is_set_per_paper(lib):
    con = sqlite3.connect(lib / "index.sqlite")
    flags = {key: json.loads(raw) for key, raw in con.execute("SELECT item_key, flags FROM items")}
    con.close()
    assert flags == {"DAMAGED1": ["text_damaged"], "OCRDAMAG": ["ocr", "text_damaged"], "CLEANMD1": [], "CLEANTAB": [],
                     "CACHEDAM": ["truncated", "text_damaged"], "METAONLY": ["body_not_read", "scanned_or_empty"]}
    assert call(lib, "zotero_status")["index"]["flags"] == {"text_damaged": 3, "ocr": 1, "truncated": 1,
                                                            "body_not_read": 1, "scanned_or_empty": 1}


def test_flag_is_on_hits_and_reads(lib):
    hits = {h["key"]: h for h in call(lib, "zotero_search", query="adipose fasting volunteers", limit=25)["hits"]}
    assert hits["DAMAGED1"]["flags"] == ["text_damaged"] and hits["OCRDAMAG"]["flags"] == ["ocr", "text_damaged"]
    assert "flags" not in hits["CLEANMD1"] and "flags" not in hits["CLEANTAB"]
    assert call(lib, "zotero_read", key="CACHEDAM")["flags"] == ["truncated", "text_damaged"]
    assert call(lib, "zotero_read", key="CLEANTAB", mode="tables")["flags"] == []


def test_an_index_from_task_11_is_rebuilt_once(tmp_path):
    z, md = make_library(tmp_path)
    index = Index(tmp_path / "pd" / "index.sqlite")
    try:
        assert sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md)).indexed == 6
        assert SCHEMA_VERSION == 3 and index.schema_version() == 3
        index.set_state("schema", "2")
        index.con.execute("UPDATE items SET flags = '[]'")
        rep = sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md))
        assert rep.indexed == 6 and any("rebuilt" in w for w in rep.warnings) and index.schema_version() == 3
        assert index.counts()["flags"]["text_damaged"] == 3
        rep = sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md))
        assert rep.indexed == 0 and rep.warnings == ()
    finally:
        index.close()
        z.close()


def test_skill_explains_the_flag():
    text = (ROOT / "skills" / "zotero-library" / "SKILL.md").read_text(encoding="utf-8")
    assert re.search(r"`text_damaged`[^\n]*abstract", text) and len(text) <= 4000
```
<!-- /file -->

## Live check (Gábor, on the Mac; not for the executor)

After the commit. Paste the outputs into `tasks/13-report.md` under `## Live check`.

```bash
cd ~/Developer/hermes-zotero
time hermes zotero sync
hermes gateway restart
.venv/bin/python - <<'EOF'
import json
from pathlib import Path
from zotcore import tools
from zotcore.settings import Settings

root = Path.home() / ".hermes" / "plugin-data" / "hermes-zotero"
settings = Settings(libraries=("user", "4805701"))
h = {t.name: t.handler for t in tools.tool_specs(lambda: settings, data_root=lambda: root)}
st = json.loads(h["zotero_status"]({}))
print("schema", st["index"]["schema"], "| items", st["index"]["items"], "| flags", st["index"]["flags"])
for doi in ["10.1001/jamanetworkopen.2021.14741", "10.5772/intechopen.76375", "10.1194/jlr.tr119000391",
            "10.1016/j.cmet.2019.05.003"]:
    d = json.loads(h["zotero_search"]({"doi": doi}))["doi_check"]
    print(doi, "| held:", d["held"], "| flags:", [i.get("flags", []) for i in d["items"]])
EOF
```

| Line | Expected |
| --- | --- |
| sync | one "rebuilt from scratch" warning, then a full re-index: about 2 minutes |
| status | schema 3; `text_damaged` close to 412 (somewhat more if group-library copies or papers read from Zotero's text cache are damaged too); no `ocr` until local task L1 |
| the first three DOIs | held, each with `text_damaged` (run-together words; lost ligatures; unreadable encoding) |
| the fourth DOI | held, without `text_damaged` (a clean paper that contains long DNA sequences) |

## Out of scope

Repairing damaged text: no converter is part of this plugin. The reviewer's list of the 412 flagged corpus files is in `review/local/` (not committed), for Gábor's own pipeline. README and the corpus guide (task 14).
