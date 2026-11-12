import re
import tomllib
from pathlib import Path

from zotcore import __version__, tools
from zotcore.frontmatter import is_true, split_front_matter
from zotcore.settings import Settings
from zotcore.textsource import build_passages

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "CORPUS.md"


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def fenced(text):
    return re.findall(r"^```markdown\n(.*?)\n```$", text, re.S | re.M)


def test_version_is_0_2_0_everywhere():
    assert __version__ == "0.2.0"
    assert re.search(r'^version: "0\.2\.0"$', read("plugin.yaml"), re.M)
    assert tomllib.loads(read("pyproject.toml"))["project"]["version"] == "0.2.0"
    assert re.search(r"^version: 0\.2\.0$", read("skills/zotero-library/SKILL.md"), re.M)


def test_readme_covers_the_new_features_and_links_the_guide():
    text = read("README.md")
    assert "(docs/CORPUS.md)" in text and GUIDE.is_file()
    for word in ("`in_tables`", "`mode` = `tables`", "`table`", "`ocr`", "`text_damaged`", "`index_outdated`", "Updating from 0.1.0"):
        assert word in text, word
    specs = {s.name: s for s in tools.tool_specs(lambda: Settings(), data_root=lambda: Path("unused"))}
    assert "in_tables" in specs["zotero_search"].schema["parameters"]["properties"]
    assert {"mode", "table"} <= set(specs["zotero_read"].schema["parameters"]["properties"])


def test_guide_states_the_spec():
    text = read("docs/CORPUS.md")
    assert text.startswith("# The Markdown corpus (spec v1)\n")
    for word in ("`markdown_path`", "`doi_<slug>.md`", "`K:<key>.md`", "200 bytes", "`spec`", "`ocr`", "`text_tool`", "`tables`",
                 "`## Tables (structured)`", "`### Table N`", "`in_tables`", "`text_damaged`", "`truncated`", "no converter"):
        assert word in text, word
    links = re.findall(r"\]\(([^)#]+)\)", text)
    assert links and all(link.startswith("https://") for link in links)


def test_the_guide_examples_work_with_the_plugin():
    blocks = fenced(read("docs/CORPUS.md"))
    header = next(b for b in blocks if b.startswith("---\n"))
    values, body = split_front_matter(header + "\n")
    assert values == {"spec": "1", "ocr": "true", "text_tool": "docling 2.94", "tables": "structured"}
    assert is_true(values["ocr"]) and body == "# Title of the paper\n"
    section = next(b for b in blocks if b.startswith("## Tables (structured)"))
    text, passages, tables = build_passages("# Paper\n\nBody text.\n\n" + section + "\n", "markdown")
    assert [(t.number, t.caption, t.rows, t.cols) for t in tables] == [(1, "Table 1. Baseline characteristics", 3, 3), (2, "", 2, 2)]
    assert "| Age (yr) | 59 ± 11 | 58 ± 11 |" in text and "| Leptin | high |" in text
    assert "It is not indexed" not in text and "<td>" not in text
    assert [p.kind for p in passages] == ["text", "table", "table"]


def test_guide_has_nothing_to_run():
    text = read("docs/CORPUS.md")
    assert not re.search(r"^```(?:bash|sh|shell|zsh|python|console)\b", text, re.M)
    assert "$(" not in text and "!`" not in text and "\t" not in text
