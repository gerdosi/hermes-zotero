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
