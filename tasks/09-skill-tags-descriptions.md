# Task 09 — The bundled skill, a `tag` filter and Tool Search descriptions

| | |
| --- | --- |
| Executor | Claude Sonnet 5.5 in Claude Code |
| Reasoning | **medium** (most of it is copied verbatim; high is fine too). Set it in the app's model picker before pasting the prompt. |
| Budget | ≤ 40 tool calls |
| Depends on | task 08 committed (122 tests pass) |
| Done when | `.venv/bin/python -m pytest` shows **133 passed** (122 old + 11 new), both checksums match, report committed |

## Goal

Plan v3.1 promises "4 tools, 2 CLI commands, 1 skill". This task adds the skill and makes the tools easier for an agent to pick:

1. **A bundled skill**, `hermes-zotero:zotero-library`, registered with Hermes' `ctx.register_skill`. It tells the agent to search the user's library before the web, how to read the coverage verdict, to read before citing, and how to keep the index fresh. Its text is written by the reviewer and is copied verbatim.
2. **A `tag` filter** in `zotero_search` (Gábor's own skills filter by tag; the index already stores tags).
3. **Tool descriptions whose first sentence fits the Tool Search list**, and `zotero_status` reports `ready` and a `hint` instead of `stage: "scaffold"`.

## Facts (checked in the Hermes source at 90d6b98, v0.23.0+209, and on Gábor's index of 6 Nov 14:26 UTC)

- `ctx.register_skill(name, path, description="", frontmatter=None)` (`hermes_cli/plugins_content.py`) registers a read-only skill as `<plugin name>:<name>`, here `hermes-zotero:zotero-library`. It raises `FileNotFoundError` if the file is missing, so `register` checks the file first: a missing skill must never stop the tools from loading.
- Plugin skills are listed in the system prompt's `<available_skills>` block under the `plugin` category (`agent/prompt_builder.py`, `_plugin_skill_prompt_rows`). The listed text is the `description` argument cut to **60 characters** (`SKILL_PROMPT_DESC_LIMIT`). The Hermes docs page that says plugin skills are not listed is out of date; the code lists them. Checked by running Hermes' own `build_skills_system_prompt` with this plugin enabled: the line reads `- hermes-zotero:zotero-library: Research questions: check the user's Zotero library first`.
- No `requires_tools` gate in the skill: with Tool Search on, plugin tools are deferred and are not in the agent's tool list, so such a gate would hide the skill.
- `skill_view` returns the whole SKILL.md. Hermes runs `` !`command` `` snippets in a skill as shell commands, fills `${HERMES_*}` tokens and warns about prompt-injection phrases; the test checks the skill has none of them.
- Tool Search (`tools/tool_search_catalog.py`) lists each deferred tool as `- name: <first sentence, cut at 80 characters>`. Today two of the four lines are cut: `zotero_read` loses everything after "one paper from the user's…", so the list never mentions highlights, and `zotero_search` never says "before the web" there.
- Gábor's library: 8,572 of 19,290 items have tags, 12,126 distinct tags, and 293 tags exist in two or more letter cases (`Obesity` / `obesity`, `Adipose Tissue` / `adipose tissue`). Hence: whole-tag match, case-insensitive. A tag-filtered search on the real index takes 0.3–1.1 s.
- Filters narrow the coverage counts too (`ferroptosis`: 200 papers, strong; with `tag=Review`: 24 papers, 1 recent, thin). The skill says so, so the agent does not go to the web because a filtered search looked thin.

## Files

```
create  skills/zotero-library/SKILL.md     (verbatim, below)
create  zotcore/skill.py                   (verbatim, below)
modify  __init__.py                        (register the skill)
modify  zotcore/search.py                  (tag filter)
modify  zotcore/tools.py                   (descriptions, tag argument, status ready/hint)
create  tests/test_09_skill_and_tags.py    (verbatim, below)
create  tasks/09-report.md
commit  tasks/09-skill-tags-descriptions.md, tasks/README.md, AGENTS.md   (added or updated by the reviewer; commit them as they are)
```

Do not touch `plugin.yaml`, `zotcore/index.py`, `zotcore/annotations.py`, `zotcore/citation.py`, `zotcore/synctool.py`, `zotcore/cli.py`, `tests/conftest.py` or any existing test.

## Spec — `skills/zotero-library/SKILL.md`

Copy this byte-for-byte (it ends with one newline) and check its SHA-256 (table below). Do not reword it; if something in it looks wrong, say so in the report.

```markdown
---
name: zotero-library
description: "Research questions: check the user's Zotero library first"
version: 0.1.0
metadata:
  hermes:
    tags: [zotero, literature, research, citations, local-first]
---

# Zotero library first

The hermes-zotero plugin keeps a local, read-only index of the user's Zotero library. For any question about scientific or scholarly literature, a specific paper, or the user's own highlights and notes, search the library before the web. The tools never change Zotero.

## Search

1. Call `zotero_search` with 2-4 distinctive keywords, not a sentence: `SCD1 ferroptosis`, not "what does SCD1 do in ferroptosis". Use scientific names, not brand names (`tirzepatide`, not Mounjaro). A hit with `match: all` has one passage holding every word; `match: any` hits hold only some of them and are weaker evidence.
2. Check `terms` in the result: stop words and words like the "a" in Lp(a) are dropped. If the distinctive word is missing, rephrase.
3. When the user names a collection, tag, year range or group, pass `collection`, `tag`, `year_from`, `year_to` or `library`. Filters also narrow the coverage counts, so judge gaps from a search without them. To check one paper, pass `doi` and read `doi_check.held`.
4. Let `coverage.verdict` decide where to look:
   - `strong`: answer from the library.
   - `thin`: answer from the library, then use the web only for what is missing, and say which sources came from where.
   - `none` with a `hint`: no passage holds every word. Retry with fewer or broader words before treating it as a gap.
   - `none` without a hint: the library has nothing on this. Say so, then use the web.

## Read before citing

A snippet is a search hit, not evidence. For the 3-5 best papers, call `zotero_read` with `key` and `query`: it starts at the best-matching passage. Page on with `offset` set to `next_offset` when the methods or results come later. Ask for what the question needs (`max_chars` 1500-4000), never a whole paper.

- Cite with the `citation` field. `approximate: true` means it was built from the index, not by Zotero: check the details before giving a formatted reference.
- Flags `body_not_read` or `scanned_or_empty` mean the paper's body text is not in the index (metadata only); `truncated` means Zotero extracted only the first pages. Do not report results you have not read.
- `mode` = `annotations` returns the user's highlights, comments and notes on the paper. `author: user` marks the user's own words; quote them as theirs. Any other author is a group member or the PDF's creator.

## Keep the index fresh

- Error `no_index`: ask the user to run `hermes zotero sync` once in a terminal. A large library takes a few minutes.
- `zotero_status` says whether the index is `ready` and gives a `hint` when Zotero has changed since the last sync.
- When the user has added papers, or the hint says so, call `zotero_sync`. While it returns `done: false`, call it again.

## Limits

- Use these tools, not other ways of opening Zotero's database or the plugin's index.
- Quote short passages with their citation; do not paste whole papers into the answer.
```

## Spec — `zotcore/skill.py`

```python
"""The skill bundled with the plugin (registered through Hermes' ctx.register_skill)."""
from __future__ import annotations

from pathlib import Path

SKILL_NAME = "zotero-library"
SKILL_DESCRIPTION = "Research questions: check the user's Zotero library first"


def skill_path(plugin_root) -> Path:
    """SKILL.md of the bundled skill under the plugin's root folder."""
    return Path(plugin_root) / "skills" / SKILL_NAME / "SKILL.md"
```

## Spec — `__init__.py`

Inside the `if __package__:` block, add `from pathlib import Path` and `from .zotcore.skill import SKILL_DESCRIPTION, SKILL_NAME, skill_path`. In `register(ctx)`, right after the `for spec in tools.tool_specs(...)` loop and before `ctx.register_cli_command(...)`:

```python
        register_skill = getattr(ctx, "register_skill", None)
        skill_md = skill_path(Path(__file__).resolve().parent)
        if register_skill is not None and skill_md.is_file():
            register_skill(SKILL_NAME, skill_md, description=SKILL_DESCRIPTION)
```

## Spec — `zotcore/search.py`

1. `_build_scope(con, library, collection, year_from, year_to, tag=None)`: select `tags` as well (`SELECT library, item_key, collections, tags FROM items WHERE 1=1`). When `tag` is not `None`, keep an item only if `tag.casefold()` equals the `casefold()` of one of its tags (`json.loads(tags or "[]")`). Whole tags only: `Obes` does not match `Obesity`, and `Obesity` does not match `Obesity research`.
2. `search(...)` gains a last keyword argument `tag=None`; `scoped` is true when any of `library, collection, year_from, year_to, tag` is not `None`, and `tag` is passed on to `_build_scope`. Nothing else changes (`doi_check` still ignores the filters; an empty scope still gives the warning `no indexed items match the filters`).

## Spec — `zotcore/tools.py`

1. Replace the four description constants with exactly these (each first sentence is at most 80 characters, so the Tool Search list shows it whole):

```python
STATUS_DESC = ("Zotero index status: whether the local library index is ready and up to date. "
               "Returns what the index holds, the snapshot age and a hint for what to do next.")
SEARCH_DESC = ("Zotero library search: find papers the user already owns, before using the web. "
               "Full text, offline, ranked by passage. Returns short snippets and a coverage verdict "
               "(strong / thin / none) for the topic. Filters: collection, tag, year, library; "
               "doi= checks whether one paper is held.")
READ_DESC = ("Zotero paper reader: read part of one paper, or the user's highlights on it. "
             "Give a key from zotero_search and a query (starts at the best match) or an offset "
             "(next_offset pages on); every result carries a citation line. "
             "mode=annotations returns the user's own highlights, comments and notes instead of the text.")
SYNC_DESC = ("Zotero index update: add new and changed papers from Zotero to the local index. "
             "Each call stops after budget_seconds and the next call resumes; it reports progress and "
             "how many items remain. Use it when the user has added papers or zotero_status says Zotero changed.")
```

2. `SEARCH_SCHEMA["properties"]` gains, right after `collection`:

```python
    "tag": {"type": "string", "description": "Only papers with this Zotero tag (any letter case)."},
```

   and `zsearch` passes `tag=_str_arg(args, "tag")` to `search(...)` (so `" review "` becomes `review`, an empty string means no filter, and a list is `invalid_argument`).

3. Add this module-level helper (above `class ToolSpec`):

```python
def _status_hint(ready: bool, data_dir, snapshot) -> str | None:
    """What the agent should do next, as one sentence, or None."""
    if not ready and data_dir is None:
        return "Zotero's data directory was not found: ask the user to run `hermes zotero doctor` in a terminal."
    if not ready:
        return "The index is empty: ask the user to run `hermes zotero sync` in a terminal once."
    if snapshot is not None and snapshot["stale"]:
        return "Zotero has changed since the last sync: call zotero_sync to add the changes."
    return None
```

4. In `status`, drop `stage="scaffold"`. Compute `ready = bool(index and index["items"] > 0)` and return `ok(plugin_version=__version__, ready=ready, hint=_status_hint(ready, found.path, snapshot), settings=..., warnings=..., data_dir=..., snapshot=..., index=...)` (the other fields as today).

## Acceptance test (copy verbatim, then verify both checksums)

| File | SHA-256 |
| --- | --- |
| `tests/test_09_skill_and_tags.py` | `af68739225d3c42a0d25f6c11e38d88898cda0b921a30cc17f08bfe403a836b8` |
| `skills/zotero-library/SKILL.md` | `b4bfdc9a601643fa36a91c31ba0d5a07ea9a9bcc4b5102f9bd6b5f18faaee723` |

The tests check the skill's registration and its text (frontmatter, size, no shell snippets, only real tool and argument names, every result field it mentions exists), the tag filter on a small library with tags in several letter cases, the description lengths, and `ready`/`hint` before and after a sync.

### `tests/test_09_skill_and_tags.py`

```python
import json
import re
from pathlib import Path

import pytest

from tests.zfixture import ZoteroFixture
from zotcore import tools
from zotcore.search import open_index, search
from zotcore.settings import Settings
from zotcore.skill import SKILL_DESCRIPTION, SKILL_NAME, skill_path
from zotcore.synctool import sync_step

ROOT = Path(__file__).resolve().parents[1]
SKILL_MD = ROOT / "skills" / "zotero-library" / "SKILL.md"
TOOLS = {"zotero_status", "zotero_search", "zotero_read", "zotero_sync"}
# Hermes (tools/tool_search_catalog.py): the deferred-tool catalog shows a tool's first sentence, cut at 80 characters.
SENTENCE_END = re.compile(r"(?<!\be\.g)(?<!\bi\.e)(?<!\betc)[.!?](?=\s|$)")
# Hermes (tools/skills_tool_plugin.py) logs a prompt-injection warning for a skill containing any of these.
INJECTION = ["ignore previous instructions", "ignore all previous", "you are now", "disregard your",
             "forget your instructions", "new instructions:", "system prompt:", "<system>", "]]>"]
FERRO = "Ferroptosis is an iron-dependent cell death driven by lipid peroxidation.\n\n" * 6


def call(handler, **args):
    out = handler(args)
    assert isinstance(out, str)
    return json.loads(out)


def specs(settings, root):
    return {s.name: s for s in tools.tool_specs(lambda: settings, data_root=lambda: root)}


def skill_text():
    return SKILL_MD.read_text(encoding="utf-8")


def frontmatter(text):
    assert text.startswith("---\n")
    head, sep, body = text[4:].partition("\n---\n")
    assert sep, "frontmatter must end with a line '---'"
    return head, body


# ---------- the bundled skill -------------------------------------------------------------------------

def test_skill_is_registered_with_a_short_description(plugin_module, fake_ctx):
    plugin_module.register(fake_ctx)
    assert set(fake_ctx.skills) == {"zotero-library"} == {SKILL_NAME}
    entry = fake_ctx.skills["zotero-library"]
    assert entry["path"].resolve() == SKILL_MD and entry["path"].is_file()
    assert skill_path(ROOT) == SKILL_MD
    # Hermes lists plugin skills in the system prompt with the description cut to 60 characters.
    assert entry["description"] == SKILL_DESCRIPTION and 20 <= len(SKILL_DESCRIPTION) <= 60
    assert "Zotero" in SKILL_DESCRIPTION
    assert TOOLS == set(fake_ctx.tools)


def test_register_works_without_skill_support(plugin_module, fake_ctx):
    fake_ctx.register_skill = None  # a Hermes build without ctx.register_skill
    plugin_module.register(fake_ctx)
    assert TOOLS == set(fake_ctx.tools) and fake_ctx.skills == {}


def test_skill_frontmatter_and_size():
    text = skill_text()
    head, body = frontmatter(text)
    assert re.search(r"^name: zotero-library$", head, re.M)
    assert re.search(r'^description: "' + re.escape(SKILL_DESCRIPTION) + r'"$', head, re.M)
    assert len(text) <= 4000  # loading the skill costs about 1k tokens per question
    assert body.lstrip().startswith("# ")


def test_skill_is_safe_for_hermes_to_load():
    text = skill_text()
    low = text.lower()
    assert [p for p in INJECTION if p in low] == []
    assert "!`" not in text  # Hermes runs !`command` snippets in a skill as shell commands
    assert "${HERMES_" not in text  # and fills in ${HERMES_*} template tokens
    assert "\t" not in text and "\r" not in text


def test_skill_names_only_real_tools_and_arguments():
    body = frontmatter(skill_text())[1]
    all_specs = specs(Settings(), Path("unused"))
    assert set(re.findall(r"\bzotero_[a-z_]+", body)) == TOOLS == set(all_specs)
    search_args = set(all_specs["zotero_search"].schema["parameters"]["properties"])
    read_args = set(all_specs["zotero_read"].schema["parameters"]["properties"])
    for arg in ("collection", "tag", "year_from", "year_to", "library", "doi"):
        assert arg in search_args and f"`{arg}`" in body
    for arg in ("key", "query", "offset", "max_chars", "mode"):
        assert arg in read_args and f"`{arg}`" in body
    for word in ("strong", "thin", "none", "no_index", "hermes zotero sync"):
        assert f"`{word}`" in body


def test_tool_descriptions_fit_tool_search():
    all_specs = specs(Settings(), Path("unused"))
    for name, spec in all_specs.items():
        desc = spec.schema["description"]
        assert desc == spec.description and desc.startswith("Zotero ")
        assert 80 <= len(desc) <= 400 and "\n" not in desc
        first = SENTENCE_END.search(desc)
        assert first is not None and first.end() <= 80, f"{name}: first sentence is cut in the Tool Search list"
    assert "web" in all_specs["zotero_search"].schema["description"][:80]
    assert "tag" in all_specs["zotero_search"].schema["description"]
    read = all_specs["zotero_read"].schema["description"]
    assert "highlights" in read[:80] and "annotations" in read and "citation" in read
    assert "budget_seconds" in all_specs["zotero_sync"].schema["description"]


# ---------- tag filter --------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tagged(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lib09")
    z = ZoteroFixture(tmp / "Zotero")
    group = z.add_group(4805701, "Ancestralize")
    rows = [("TAG00001", 1, ("Obesity", "Review")), ("TAG00002", 1, ("obesity",)), ("TAG00003", 1, ()),
            ("TAG00004", 1, ("Obesity research",)), ("TAG00005", 1, ("Ünïcode Tag",)), ("GTAG0001", group, ("OBESITY",))]
    for n, (key, lib, tags) in enumerate(rows):
        i = z.add_item(key, library_id=lib, tags=tags,
                       fields={"title": f"Ferroptosis paper {n}", "DOI": f"10.1000/tag.{n}", "date": f"{2020 + n}-00-00 {2020 + n}"})
        z.add_attachment(i, f"PDFT{n:04d}", ft_text=FERRO)
    settings = Settings(zotero_data_dir=str(z.data_dir), libraries=("user", "4805701"))
    root = tmp / "pd"
    assert sync_step(settings, root, budget_seconds=30)["done"] is True
    z.close()
    return settings, root


def hit_keys(data):
    return sorted(h["key"] for h in data["hits"])


def test_tag_filter_matches_whole_tags_in_any_case(tagged):
    settings, root = tagged
    run = specs(settings, root)["zotero_search"].handler
    data = call(run, query="ferroptosis", tag="OBESITY")
    assert data["ok"] is True and hit_keys(data) == ["GTAG0001", "TAG00001", "TAG00002"]
    assert data["coverage"]["matches_all"] == 3 and data["warnings"] == []
    assert hit_keys(call(run, query="ferroptosis", tag=" review ")) == ["TAG00001"]
    assert hit_keys(call(run, query="ferroptosis", tag="ünïcode tag")) == ["TAG00005"]
    assert hit_keys(call(run, query="ferroptosis", tag="obesity", library="user")) == ["TAG00001", "TAG00002"]
    assert hit_keys(call(run, query="ferroptosis", tag="obesity", year_from=2021)) == ["GTAG0001", "TAG00002"]
    assert len(call(run, query="ferroptosis", tag="")["hits"]) == 6  # empty = no filter
    data = call(run, query="ferroptosis", tag="Obes")  # no partial matches
    assert data["hits"] == [] and data["coverage"]["verdict"] == "none"
    assert "no indexed items match the filters" in data["warnings"]
    assert call(run, query="ferroptosis", tag=["Obesity"])["error"]["code"] == "invalid_argument"
    data = call(run, query="ferroptosis", tag="Review", doi="10.1000/tag.1")  # doi_check ignores filters
    assert data["doi_check"]["held"] is True and hit_keys(data) == ["TAG00001"]


def test_search_function_takes_tag(tagged):
    settings, root = tagged
    con = open_index(root / "index.sqlite")
    try:
        data = search(con, settings, query="ferroptosis", tag="obesity research")
        assert [h["key"] for h in data["hits"]] == ["TAG00004"]
        assert len(search(con, settings, query="ferroptosis")["hits"]) == 6
    finally:
        con.close()


def test_search_schema_has_tag():
    schema = specs(Settings(), Path("unused"))["zotero_search"].schema["parameters"]["properties"]
    assert schema["tag"]["type"] == "string"


# ---------- zotero_status: ready and hint -------------------------------------------------------------

def test_status_ready_and_hint(tmp_path):
    root = tmp_path / "pd"
    data = call(specs(Settings(zotero_data_dir=str(tmp_path / "nope")), root)["zotero_status"].handler)
    assert data["ok"] is True and data["ready"] is False and "doctor" in data["hint"]
    assert "stage" not in data

    z = ZoteroFixture(tmp_path / "Zotero")
    i = z.add_item("STAT0001", fields={"title": "Status paper"})
    z.add_attachment(i, "PDFS0001", ft_text=FERRO)
    settings = Settings(zotero_data_dir=str(z.data_dir))
    status = specs(settings, root)["zotero_status"].handler
    data = call(status)
    assert data["ready"] is False and "hermes zotero sync" in data["hint"]

    assert sync_step(settings, root, budget_seconds=30)["done"] is True
    data = call(status)
    assert data["ready"] is True and data["hint"] is None and data["index"]["items"] == 1

    i = z.add_item("STAT0002", fields={"title": "A paper added after the sync"})
    z.add_attachment(i, "PDFS0002", ft_text=FERRO)
    data = call(status)
    assert data["ready"] is True and data["snapshot"]["stale"] is True and "zotero_sync" in data["hint"]
    z.close()


# ---------- every field the skill tells the agent to read exists -----------------------------------------

def test_fields_named_in_the_skill_exist(tagged):
    settings, root = tagged
    s = specs(settings, root)
    data = call(s["zotero_search"].handler, query="ferroptosis", doi="10.1000/tag.0")
    assert {"verdict", "matches_all"} <= set(data["coverage"]) and "held" in data["doi_check"]
    assert data["terms"] == ["ferroptosis"]
    assert {h["match"] for h in data["hits"]} == {"all"}
    hint = call(s["zotero_search"].handler, query="ferroptosis zeaxanthinmarker")["coverage"]
    assert hint["verdict"] == "none" and "hint" in hint
    data = call(s["zotero_read"].handler, key="TAG00001", query="lipid", max_chars=200)
    assert {"next_offset", "citation", "flags"} <= set(data) and "approximate" in data["citation"]
    data = call(s["zotero_read"].handler, key="TAG00001", mode="annotations")
    assert data["ok"] is True and "annotations" in data
    assert {"ready", "hint"} <= set(call(s["zotero_status"].handler))
    assert "done" in call(s["zotero_sync"].handler, budget_seconds=5)
    body = frontmatter(skill_text())[1]
    for field in ("`terms`", "coverage.verdict", "doi_check.held", "next_offset", "citation", "approximate: true",
                  "body_not_read", "scanned_or_empty", "truncated", "author: user", "ready", "hint", "done: false",
                  "match: all", "match: any"):
        assert field in body
```

## Commands

```bash
.venv/bin/python -m pytest                          # expect: 133 passed
shasum -a 256 tests/test_09_skill_and_tags.py skills/zotero-library/SKILL.md
```

Finish with `tasks/09-report.md` (paste both checksums) and one commit: `task 09: bundled skill, tag filter, tool descriptions`.

## Live check (Gábor, in the same or a new Claude Code session, after the commit)

Expected values come from the reference implementation on your index of 6 Nov, 14:26 UTC. Small differences are fine if you synced since.

**1. Direct check.** Zotero open or closed. Run this from the repo and paste the output into the report under `## Live check`. It only reads your index.

```bash
.venv/bin/python - <<'EOF'
import json, time
from pathlib import Path
from zotcore import tools
from zotcore.settings import Settings
from zotcore.skill import skill_path
root = Path.home() / ".hermes/plugin-data/hermes-zotero"
S = Settings(libraries=("user", "4805701"))
h = {s.name: s for s in tools.tool_specs(lambda: S, data_root=lambda: root)}
def search(**a):
    t = time.time(); d = json.loads(h["zotero_search"].handler(a)); dt = time.time() - t
    c = d["coverage"]
    print(f"{a} {dt:.2f}s hits={len(d['hits'])} all={c['matches_all']} recent={c['recent']} "
          f"verdict={c['verdict']} first={d['hits'][0]['key'] if d['hits'] else None} warnings={d['warnings']}")
search(query="ferroptosis", tag="Review")
search(query="ferroptosis", tag="REVIEW")
search(query="insulin resistance", tag="Obesity")
search(query="insulin resistance", tag="obesity", library="user", year_from=2020)
search(query="microbiota", tag="Important")
search(query="ketone", tag="Favorite")
search(query="ferroptosis", tag="NoSuchTagAnywhere")
st = json.loads(h["zotero_status"].handler({}))
print("status: ready =", st["ready"], "| hint =", st["hint"], "| items =", st["index"]["items"], "| has stage:", "stage" in st)
for name, spec in h.items():
    first = spec.description.split(". ")[0] + "."
    print(f"{name}: {len(first)} chars: {first}")
print("skill:", skill_path(Path(".").resolve()).stat().st_size, "bytes")
print("\ncalibration (query | all | any | recent | verdict):")
for q in ["ferroptosis adipocytes", "time-restricted eating", "SCD1 ferroptosis", "menaquinone",
          "ketogenic diet epilepsy", "brown adipose cold exposure", "trimethylamine atherosclerosis", "tirzepatide",
          "retatrutide", "intermittent fasting autophagy", "fructose hepatic lipogenesis", "NAD precursors aging",
          "sarcopenic obesity resistance training", "ultra-processed food", "Akkermansia muciniphila",
          "creatine supplementation", "semaglutide alcohol use disorder", "PCSK9 base editing",
          "circadian clock liver", "mounjaro"]:
    c = json.loads(h["zotero_search"].handler({"query": q, "limit": 3}))["coverage"]
    print(f"{q} | {c['matches_all']} | {c['matches_any']} | {c['recent']} | {c['verdict']}")
EOF
```

| Call | Expected |
| --- | --- |
| ferroptosis, tag Review / REVIEW | identical: 10 hits, all 24, recent 1, **thin**, first SV9N8VKT |
| insulin resistance, tag Obesity | all 527, recent 219, strong, first XGRB6QRX |
| … + library user, year_from 2020 | all 288, strong, first AHESV4J8 |
| microbiota, tag Important | all 64, recent 0, thin |
| ketone, tag Favorite | 9 hits, all 9, thin |
| tag NoSuchTagAnywhere | 0 hits, none, warning `no indexed items match the filters` |
| each search | under about 1.5 s |
| status | `ready = True`, `has stage: False`; hint `None`, or "Zotero has changed since the last sync…" if Zotero wrote to its database since your last sync |
| descriptions | four lines, each ≤ 80 characters; skill about 3,100 bytes |

**Calibration (plan v3.1: "verdict matches you on 16 of 20").** The 20 queries print one verdict each. Mark each `agree` / `disagree` in the report from what you know of your library. Expected on 6 Nov: strong for all except **thin** for SCD1 ferroptosis (7 papers), semaglutide alcohol use disorder (5), PCSK9 base editing (5) and mounjaro (2; the brand name: tirzepatide gives 111, strong). If you disagree on more than 4, say which way (too strong / too thin); the thresholds are settings (`coverage_strong_min` 8, `coverage_recent_min` 2, `coverage_recent_years` 5), not code.

**2. Through Hermes, with your own skills as they are.** `hermes gateway restart` first. Then:

- `hermes -z "Which papers tagged Review in my Zotero library discuss ferroptosis? List three with their citations."`

Expected: `zotero_search` with `tag` = `Review` (or `review`), then `zotero_read` or the citations; no terminal, sqlite or curl.

**3. Through Hermes as a stranger would get it (your two Zotero skills switched off for a few minutes).** This shows whether the plugin's own skill and descriptions are enough. Ask Claude Code to do exactly this:

1. `cp ~/.hermes/config.yaml ~/.hermes/config.yaml.task09-backup`
2. In `~/.hermes/config.yaml`, add `local-literature` and `zotero` to the list `skills.disabled` (create `skills:` / `disabled:` if missing; keep every existing entry and every other line unchanged). `hermes gateway restart`.
3. Run each prompt as its own `hermes -z` call (a fresh session each):
   - `hermes -z "What does the literature say about SCD1 and ferroptosis? Cite the papers you use."`
   - `hermes -z "Is the retatrutide phase 3 trial in my Zotero library? If not, find it online."`
   - `hermes -z "What did I highlight in the NEJM paper 'Managing Obesity'? Quote my highlights with page numbers."`
4. `cp ~/.hermes/config.yaml.task09-backup ~/.hermes/config.yaml`, then `cmp` the two files (no output = restored), then `hermes gateway restart`.

For each prompt paste, in order, the tool calls with their arguments (from `~/.hermes/state.db`, as in task 07), whether `skill_view` loaded `hermes-zotero:zotero-library`, any web calls, and the total time; plus the `tool … completed` lines from `~/.hermes/logs/agent.log`. **Pass:** every session calls `zotero_search` before any web tool, and none opens `zotero.sqlite`, the plugin's `index.sqlite` or `~/Zotero-Markdown/index.sqlite` with terminal, sqlite or Python. Expected: SCD1 → coverage thin (7 papers), reads 2–5 of them, web only for the gap if at all; retatrutide → library first (12 papers mention it), then the web only if the phase 3 trial is not among them; highlights → `zotero_read` with `mode: annotations` on Q3K5IWZH (19 highlights).

## Out of scope

README, disclosures, the `plugin.yaml` description ("No network" needs the loopback wording) and the `homepage` placeholder (task 10). The OCR flag stays in your own skill. Searching by tag without a query (a list of all papers with a tag) is not supported: `query` or `doi` is still required.
