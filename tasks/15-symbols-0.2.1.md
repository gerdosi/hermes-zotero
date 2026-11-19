# Task 15 — Text that is mostly symbols gets `text_damaged`; version 0.2.1

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code |
| Reasoning | **low** (one verbatim file and a small patch). Set it in the app's model picker before pasting the prompt. |
| Budget | ≤ 20 tool calls |
| Depends on | task 14 committed and pushed (229 tests pass) |
| Done when | `.venv/bin/python -m pytest` shows **236 passed** (229 old + 7 new), the checksums match, report committed |

## Goal

Some converters, faced with a PDF font that has no usable character map, write a page of spaces, tabs and punctuation instead of words. The damage check of task 13 skips any text with fewer than 500 words, so such a paper is never judged and is indexed as if it had a body. After this task a text whose characters are mostly symbols, not letters, carries `text_damaged` like the other kinds of damage, and release 0.2.1 ships it.

## Calibration (Gábor's corpus, 18 Nov 2026)

- **Found by a review of 375 re-OCR'd papers:** 12 bodies of 1-4% letters (whitespace and punctuation from a broken font layer). Task 13's check flagged 5 of them, and only by accident (500+ one-letter "words"); the other 7 were indexed as clean. The 12 files have since been re-converted locally.
- **The measure:** letters as a share of letters and symbols. White space, digits and the characters `.`, `|` and `-` are left out, so number-heavy tables, table rules and dot leaders in a book's contents do not count against a paper. The first version of the measure counted them and wrongly picked out a paper of number tables and a book's table of contents.
- **On all 18,408 corpus files** (the prose before the structured tables, first 60,000 characters): clean prose sits at 75-95% letters. Four files fall under 65%, and all four are damaged: two unreadable cover pages, a paper with control characters between its words (13%), and a paper in a shifted font encoding (60%). The next file up is clean, at 75%. The 12 junk bodies score 2-21%.
- **On the 436 papers the plugin reads from Zotero's text cache:** none under 81%.
- **Result:** 4 more papers flagged in the corpus (416 in all with the current files). Threshold 65%, judged only when letters and symbols together reach 1,000 characters.
- **Cost:** about 1.4 ms more per paper, so a full rebuild of 19,300 papers takes about 25 s longer. Most papers are cleared by one count of non-space characters; symbols are counted only when that count leaves doubt.

## Design in short

- `zotcore/textquality.py`: a new kind `symbols`, checked first, before the 500-word minimum. Constants `SYMBOLS_MIN` and `LETTER_SHARE`; helper `_mostly_symbols`. Letters are counted as before (the word pattern); scripts other than Latin count as letters.
- `zotcore/index.py`: `SCHEMA_VERSION` 3 to 4, so the next sync rebuilds the index once and every paper is checked again.
- Version 0.2.1 in `plugin.yaml`, `pyproject.toml`, `zotcore/__init__.py` and the bundled skill's front matter. The skill text does not change.
- `docs/CORPUS.md`: the `text_damaged` row names the new kind.
- Three one-line changes to earlier tests, written by the reviewer and included in the patch: task 11's skill test accepts any version number (the exact one is task 14's test), task 13's test compares with `SCHEMA_VERSION` instead of the number 3, and task 14's version test expects 0.2.1. Apply them as they are; they are not yours to change.

## Files

```
create  tests/test_15_symbols.py                  (verbatim, below)
modify  zotcore/textquality.py, zotcore/index.py, zotcore/__init__.py, plugin.yaml, pyproject.toml,
        skills/zotero-library/SKILL.md, docs/CORPUS.md,
        tests/test_11_tables.py, tests/test_13_text_damage.py, tests/test_14_release.py   (the patch below)
create  tasks/15-report.md
commit  tasks/15-symbols-0.2.1.md, tasks/README.md   (added or updated by the reviewer; commit them as they are)
```

Do not touch any other file.

## Steps

1. Run `.venv/bin/python -m pytest` first: 229 passed.
2. From the repo root, run this. It writes the verbatim file and puts the patch into the system's temporary folder, and prints a SHA-256 for each:

```python
import hashlib, pathlib, re, tempfile
md = pathlib.Path("tasks/15-symbols-0.2.1.md").read_text(encoding="utf-8")
for name, body in re.findall(r"<!-- file: (\S+) -->\n```\w*\n(.*?)\n```\n<!-- /file -->", md, re.S):
    out = pathlib.Path(tempfile.gettempdir()) / "task15.patch" if name == "PATCH" else pathlib.Path(name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body + "\n", encoding="utf-8", newline="\n")
    print(hashlib.sha256(out.read_bytes()).hexdigest(), out)
```

3. Compare the printed checksums with the table below. A mismatch means the copy went wrong: stop and fix it, do not edit the files.
4. Apply the patch from the repo root: `git apply --check <path printed for the patch>`, then `git apply <the same path>`. If it does not apply, stop and report `BLOCKED`; do not make the change by hand.
5. Run `.venv/bin/python -m pytest`: 236 passed.
6. Fill in the report `tasks/15-report.md` (the template is in the project rules file) and make one commit: `task 15: mostly-symbols check, version 0.2.1`.

### Checksums

| File | SHA-256 |
| --- | --- |
| `tests/test_15_symbols.py` | `92de3a30f7528046d02798bce64f81fc77e71da281b076910f7911a77078c180` |
| the patch file | `d9a1bf234f3497a3381017414504ad3496967dd0ae2a9e566973cb23ab32125b` |
| `zotcore/textquality.py` after the patch | `3cc113379ba411d42c72688af4698ee101eceac02e246e41e008280ee0963c63` |
| `zotcore/index.py` after the patch | `6841bface2df0d16b46eba5cbeb7446331f8e0a5072982d50fc2b7dcdb17f968` |
| `zotcore/__init__.py` after the patch | `b7efea5cc9a065f567c750670ba9817ffc7daf374f85f2fcc5e5bbeb8239ec7e` |
| `plugin.yaml` after the patch | `71b41aa8fdcb27271f1ac237d9477bb68be8cf3e7d4720d123c2f6d4509a45d2` |
| `pyproject.toml` after the patch | `17e7e491ac58355c5ecbfb4100faf4787abfd2fbf6ca9cc1cefd743db212b0b2` |
| `skills/zotero-library/SKILL.md` after the patch | `9a8bcaf38f8d21f107848f0e2f7294df868252065f5fb58587af2a1664d20b48` |
| `docs/CORPUS.md` after the patch | `7c94910484f0c72fda92288011e4703aeba480377e5d7b795d60eb43e2950b43` |
| `tests/test_11_tables.py` after the patch | `7fa829d34c9a6b6af290b02ab08156e57ad703f52e0fb642f95bcf83004a1dd5` |
| `tests/test_13_text_damage.py` after the patch | `1a20d1a9517c72d6b22eb356e6972dfa689e6e943004c55f4557174364c09cf9` |
| `tests/test_14_release.py` after the patch | `58c05841afc9371d769f137163a931d4e5dd483a993bd16ca00ce7181d1d3ce0` |

## Spec — the patch

<!-- file: PATCH -->
```diff
diff --git a/docs/CORPUS.md b/docs/CORPUS.md
index 298f7c6..8afe5c5 100644
--- a/docs/CORPUS.md
+++ b/docs/CORPUS.md
@@ -98,7 +98,7 @@ Credentials, anything that writes back to Zotero, and anything that is not deriv
 | Flag | Set when | What it tells the agent |
 | --- | --- | --- |
 | `ocr` | the front matter says `ocr: true` | Digits and symbols may be wrong; say so when quoting numbers. |
-| `text_damaged` | the text shows clear conversion damage: words run together, letters or ligatures missing, an unreadable font encoding | Rely on title and abstract; searches can miss the paper. |
+| `text_damaged` | the text shows clear conversion damage: words run together, letters or ligatures missing, an unreadable font encoding, mostly symbols instead of letters | Rely on title and abstract; searches can miss the paper. |
 | `truncated` | Zotero's text cache holds only the first pages | Results further on were not read. |
 | `body_not_read`, `scanned_or_empty` | no text was found for the item | Only title and abstract are in the index. |
 
diff --git a/plugin.yaml b/plugin.yaml
index 401daae..2890280 100644
--- a/plugin.yaml
+++ b/plugin.yaml
@@ -1,5 +1,5 @@
 name: hermes-zotero
-version: "0.2.0"
+version: "0.2.1"
 manifest_version: 2
 description: "Search and read the papers in your Zotero library before the web: a local, read-only full-text index that works with Zotero closed. No writes to Zotero, no telemetry; its only network call goes to Zotero on this computer, for citations."
 author: "Gábor Erdősi"
diff --git a/pyproject.toml b/pyproject.toml
index edb1a91..c936cb9 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -1,6 +1,6 @@
 [project]
 name = "hermes-zotero"
-version = "0.2.0"
+version = "0.2.1"
 description = "Read-only local Zotero index for Hermes Agent"
 requires-python = ">=3.11"
 license = "MIT"
diff --git a/skills/zotero-library/SKILL.md b/skills/zotero-library/SKILL.md
index 9a0589f..b2ab70d 100644
--- a/skills/zotero-library/SKILL.md
+++ b/skills/zotero-library/SKILL.md
@@ -1,7 +1,7 @@
 ---
 name: zotero-library
 description: "Research questions: check the user's Zotero library first"
-version: 0.2.0
+version: 0.2.1
 metadata:
   hermes:
     tags: [zotero, literature, research, citations, local-first]
diff --git a/tests/test_11_tables.py b/tests/test_11_tables.py
index b2eae41..8404346 100644
--- a/tests/test_11_tables.py
+++ b/tests/test_11_tables.py
@@ -455,6 +455,6 @@ def test_schemas_and_descriptions(plugin_module, fake_ctx):
 
 def test_skill_explains_the_table_route():
     text = (ROOT / "skills" / "zotero-library" / "SKILL.md").read_text(encoding="utf-8")
-    assert re.search(r"^version: 0\.2\.0$", text, re.M) and len(text) <= 4000
+    assert re.search(r"^version: \d+\.\d+\.\d+$", text, re.M) and len(text) <= 4000   # the exact version: test_14
     for word in ("`in_tables`", "`table`", "`tables`", "`kind: table`", "`index_outdated`"):
         assert word in text
diff --git a/tests/test_13_text_damage.py b/tests/test_13_text_damage.py
index c7aa875..c511337 100644
--- a/tests/test_13_text_damage.py
+++ b/tests/test_13_text_damage.py
@@ -143,11 +143,11 @@ def test_an_index_from_task_11_is_rebuilt_once(tmp_path):
     index = Index(tmp_path / "pd" / "index.sqlite")
     try:
         assert sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md)).indexed == 6
-        assert SCHEMA_VERSION == 3 and index.schema_version() == 3
+        assert index.schema_version() == SCHEMA_VERSION
         index.set_state("schema", "2")
         index.con.execute("UPDATE items SET flags = '[]'")
         rep = sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md))
-        assert rep.indexed == 6 and any("rebuilt" in w for w in rep.warnings) and index.schema_version() == 3
+        assert rep.indexed == 6 and any("rebuilt" in w for w in rep.warnings) and index.schema_version() == SCHEMA_VERSION
         assert index.counts()["flags"]["text_damaged"] == 3
         rep = sync(index, z.db_path, z.data_dir, corpus=MarkdownCorpus(md))
         assert rep.indexed == 0 and rep.warnings == ()
diff --git a/tests/test_14_release.py b/tests/test_14_release.py
index 7316710..893f202 100644
--- a/tests/test_14_release.py
+++ b/tests/test_14_release.py
@@ -19,11 +19,11 @@ def fenced(text):
     return re.findall(r"^```markdown\n(.*?)\n```$", text, re.S | re.M)
 
 
-def test_version_is_0_2_0_everywhere():
-    assert __version__ == "0.2.0"
-    assert re.search(r'^version: "0\.2\.0"$', read("plugin.yaml"), re.M)
-    assert tomllib.loads(read("pyproject.toml"))["project"]["version"] == "0.2.0"
-    assert re.search(r"^version: 0\.2\.0$", read("skills/zotero-library/SKILL.md"), re.M)
+def test_version_is_0_2_1_everywhere():
+    assert __version__ == "0.2.1"
+    assert re.search(r'^version: "0\.2\.1"$', read("plugin.yaml"), re.M)
+    assert tomllib.loads(read("pyproject.toml"))["project"]["version"] == "0.2.1"
+    assert re.search(r"^version: 0\.2\.1$", read("skills/zotero-library/SKILL.md"), re.M)
 
 
 def test_readme_covers_the_new_features_and_links_the_guide():
diff --git a/zotcore/__init__.py b/zotcore/__init__.py
index 4cf6823..997d8b2 100644
--- a/zotcore/__init__.py
+++ b/zotcore/__init__.py
@@ -1,3 +1,3 @@
 """hermes-zotero core logic (standard library only, no Hermes imports)."""
 
-__version__ = "0.2.0"
+__version__ = "0.2.1"
diff --git a/zotcore/index.py b/zotcore/index.py
index 74fbc4e..938e509 100644
--- a/zotcore/index.py
+++ b/zotcore/index.py
@@ -14,7 +14,7 @@ from .textsource import TextResult, build_passages, choose_text, text_signature
 from .zdb import list_items, libraries as zotero_libraries, load_items, open_snapshot
 
 CHUNK = 500
-SCHEMA_VERSION = 3   # 2: passage kinds and the table list; 3: every paper checked for damaged text (0.2.0)
+SCHEMA_VERSION = 4   # 2: passage kinds and the table list; 3: damaged-text check (0.2.0); 4: mostly-symbols check (0.2.1)
 MAX_ITEM_WARNINGS = 20
 
 SCHEMA = (
diff --git a/zotcore/textquality.py b/zotcore/textquality.py
index 5278dde..7a997b9 100644
--- a/zotcore/textquality.py
+++ b/zotcore/textquality.py
@@ -11,6 +11,9 @@ RUN_ON_MIN = 5              # ... and at least this many of them
 FRAGMENT_SHARE = 0.35       # share of one-letter words
 NO_VOWEL_SHARE = 0.15       # share of words of 4+ letters without a vowel
 LIGATURE_MIN = 5            # words that lost fi / fl / ff (English)
+SYMBOLS_MIN = 1_000         # letters and symbols together; shorter texts are not judged for symbols
+LETTER_SHARE = 0.65         # below this share of letters among letters and symbols, the text is mostly symbols
+_NOT_SYMBOLS = ".|-"        # dot leaders, table rules and dashes; digits are not counted either
 
 _WORD = re.compile(r"[^\W\d_]+")
 _VOWELS = frozenset("aeiouyàáâãäåæèéêëìíîïòóôõöøùúûüýÿāăąēęěīıōőœūůűų")
@@ -22,16 +25,18 @@ _LIGATURE = re.compile(
 
 
 def damage(text: str) -> str | None:
-    """Kind of damage found in the text, or None: 'run_together', 'fragments', 'unreadable', 'ligatures'.
+    """Kind of damage found in the text, or None: 'symbols', 'run_together', 'fragments', 'unreadable', 'ligatures'.
 
     None means no sign was found, not that the text is intact. Texts that are short or mostly
     in a non-Latin script are not judged.
     """
     sample = text[:SAMPLE_CHARS]
     words = _WORD.findall(sample)
+    letters = sum(map(len, words))
+    if _mostly_symbols(sample, letters):
+        return "symbols"
     if len(words) < MIN_WORDS:
         return None
-    letters = sum(map(len, words))
     if sum(len(w) for w in words if ord(w[0]) < 0x250) < 0.9 * letters:
         return None
     lower = [w.lower() for w in words]
@@ -47,3 +52,13 @@ def damage(text: str) -> str | None:
     if len(_LIGATURE.findall(sample.lower())) >= LIGATURE_MIN:
         return "ligatures"
     return None
+
+
+def _mostly_symbols(sample: str, letters: int) -> bool:
+    """True when letters are under LETTER_SHARE of letters and symbols (white space, digits and .|- left out)."""
+    shown = len(sample) - sum(map(str.isspace, sample))
+    if letters >= LETTER_SHARE * shown:
+        return False            # the usual case, decided without counting symbols
+    symbols = (shown - letters - sum(map(str.isdecimal, sample))
+               - sum(sample.count(c) for c in _NOT_SYMBOLS))
+    return letters + symbols >= SYMBOLS_MIN and letters < LETTER_SHARE * (letters + symbols)
```
<!-- /file -->

## Acceptance tests — `tests/test_15_symbols.py`

<!-- file: tests/test_15_symbols.py -->
```python
from zotcore.index import SCHEMA_VERSION
from zotcore.textquality import LETTER_SHARE, SYMBOLS_MIN, damage

SENTENCE = "The metabolic response of adipose tissue to prolonged fasting was measured in twelve healthy volunteers. "
CLEAN = SENTENCE * 60                                        # 900 words
HEADER = "# A paper\n\n- **Authors:** A. Author\n- **Year:** 2001\n\n---\n\n"
# What a converter writes when it reads a PDF font without a usable encoding: spaces, tabs and punctuation.
JUNK = "  ##%   - -  \t \"\t \t  ( -  ! ! \t\"\t \t-   \t-  ( \"\" -\t  \"-\t\t\t \"\t-\n" * 120


def test_text_that_is_mostly_symbols_is_damaged():
    assert damage(HEADER + JUNK) == "symbols"
    assert damage(JUNK) == "symbols"


def test_control_characters_between_words_count_as_symbols():
    broken = " ".join("\x05\x07" + w + "\x11\x18\x08" for w in SENTENCE.split()) * 20
    assert damage(broken) == "symbols"


def test_clean_text_and_text_with_numbers_tables_and_leaders_are_not():
    assert damage(CLEAN) is None
    table = "| Glucose (mmol/l) | 5.79 ± 0.44 | 6.15 ± 0.25* |\n|---|---|---|\n" * 80
    assert damage(CLEAN + table) is None
    leaders = "Chapter 3. Physical activity and health " + "." * 60 + " 117\n"
    assert damage(leaders * 40) is None


def test_short_texts_are_not_judged_for_symbols():
    assert len(JUNK[:600].split()) < SYMBOLS_MIN
    assert damage(JUNK[:600]) is None


def test_the_threshold():
    letters = 1300
    at = round(letters / LETTER_SHARE) - letters      # symbols that put the share right at the threshold
    assert damage("a" * letters + "!" * at) is None
    assert damage("a" * letters + "!" * (at + 30)) == "symbols"


def test_letters_of_other_scripts_count_as_letters():
    assert damage("脂肪组织对长期禁食的代谢反应。" * 200) is None


def test_the_index_is_rebuilt_once_for_the_new_check():
    assert SCHEMA_VERSION == 4
```
<!-- /file -->

## Live check and release (Gábor, on the Mac; not for the executor)

Paste the outputs into `tasks/15-report.md` under `## Live check`, then commit that file (`task 15: live check`).

**1. Rebuild and check the flags.**

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
for doi in ["10.1194/jlr.ra119000423", "10.1161/01.atv.15.3.320", "10.1007/s001250051540", "10.1016/j.cmet.2019.05.003"]:
    d = json.loads(h["zotero_search"]({"doi": doi}))["doi_check"]
    print(doi, "| held:", d["held"], "| flags:", [i.get("flags", []) for i in d["items"]])
EOF
```

| Line | Expected |
| --- | --- |
| sync | one "rebuilt from scratch" warning, then a full re-index: about 3 minutes |
| status | schema 4; `text_damaged` about 432 (433 before, minus 5 junk files repaired on 18 Nov, plus 4 new); `ocr` 358 (370 minus the 12 repaired files, which are no longer OCR text) |
| the first two DOIs | held, each with `text_damaged` (shifted font encoding; control characters) |
| the third DOI | held, no flags (one of the 12 repaired files) |
| the fourth DOI | held, without `text_damaged` |

**2. Validate a clean clone, then push.**

```bash
cd ~/Developer/hermes-zotero
git status --short
CLONE="$(mktemp -d)/hermes-zotero"
git clone --quiet . "$CLONE"
hermes plugins validate "$CLONE"
git push
git rev-parse HEAD
```

Expected: `git status` prints nothing; the validation ends with `Validation passed.` and the line `security scan — safe`; the last line is the 40-character ID of the release commit. Keep that ID for the catalog. If the scan says anything other than `safe`, do not push; bring the output to the review session.

**3. Update the demo profile.**

```bash
hermes -p zdemo plugins update hermes-zotero
hermes -p zdemo zotero doctor
```

Expected: `doctor` prints `hermes-zotero 0.2.1`. Your own Hermes uses the Git install in this folder and needs nothing more.

**4. The catalog entry.** The catalog pins a commit, so 0.2.1 reaches catalog users only through a pull request that changes the pin. A review session prepares it after steps 1-3, as for 0.2.0.

## Out of scope

Repairing damaged text (no converter is part of this plugin); the placeholder rule (treating a `_No extractable text._` body as no text), which stays on hold; README (its `text_damaged` sentence still holds).
