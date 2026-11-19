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
