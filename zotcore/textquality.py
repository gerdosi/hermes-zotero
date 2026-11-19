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
SYMBOLS_MIN = 1_000         # letters and symbols together; shorter texts are not judged for symbols
LETTER_SHARE = 0.65         # below this share of letters among letters and symbols, the text is mostly symbols
_NOT_SYMBOLS = ".|-"        # dot leaders, table rules and dashes; digits are not counted either

_WORD = re.compile(r"[^\W\d_]+")
_VOWELS = frozenset("aeiouyàáâãäåæèéêëìíîïòóôõöøùúûüýÿāăąēęěīıōőœūůűų")
_SEQUENCE = frozenset("acgtun")
_LIGATURE = re.compile(
    r"\b(?:signicant|signicantly|specic|specically|eect|eects|eective|dierent|dierence|dierences|identied|"
    r"dened|inammation|inammatory|ecient|ecacy|coecient|sucient|insucient|deciency|decient|dicult|conrmed|"
    r"inuence|classied|modied|puried|quantied|uorescence|uorescent)\b")


def damage(text: str) -> str | None:
    """Kind of damage found in the text, or None: 'symbols', 'run_together', 'fragments', 'unreadable', 'ligatures'.

    None means no sign was found, not that the text is intact. Texts that are short or mostly
    in a non-Latin script are not judged.
    """
    sample = text[:SAMPLE_CHARS]
    words = _WORD.findall(sample)
    letters = sum(map(len, words))
    if _mostly_symbols(sample, letters):
        return "symbols"
    if len(words) < MIN_WORDS:
        return None
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


def _mostly_symbols(sample: str, letters: int) -> bool:
    """True when letters are under LETTER_SHARE of letters and symbols (white space, digits and .|- left out)."""
    shown = len(sample) - sum(map(str.isspace, sample))
    if letters >= LETTER_SHARE * shown:
        return False            # the usual case, decided without counting symbols
    symbols = (shown - letters - sum(map(str.isdecimal, sample))
               - sum(sample.count(c) for c in _NOT_SYMBOLS))
    return letters + symbols >= SYMBOLS_MIN and letters < LETTER_SHARE * (letters + symbols)
