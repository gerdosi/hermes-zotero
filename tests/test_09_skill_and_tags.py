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
