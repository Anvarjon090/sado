"""Uzbek (uz) number verbalization — a native backend for text_normalization.

``num2words`` has no Uzbek locale, so Uzbek text reached the TTS engine with
raw digits, which OmniVoice reads in another language or slurs. This module
renders numbers the way they are read aloud in Uzbek (Latin script):

  * cardinals are space-separated words: 2025 → ikki ming yigirma besh,
    1 500 000 → bir million besh yuz ming. A leading hundred is plain
    ``yuz`` (125 → yuz yigirma besh); a leading thousand is ``bir ming``;
  * ordinals append ``-inchi`` after a consonant and ``-nchi`` after a vowel
    to the last word (birinchi, ikkinchi, to'rtinchi, yigirmanchi); ``ellik``
    softens to ``elliginchi``;
  * decimals read as "<int> butun <denominator>dan <fraction>"
    (3.5 → uch butun o'ndan besh, 0.25 → nol butun yuzdan yigirma besh);
  * percentages read as "<number> foiz".

The ordinal form matters most: Uzbek writes ordinals as a digit glued to the
noun by a hyphen ("2025-yil", "5-sinf", "1-may"), which the generic integer
rule deliberately skips. :func:`ordinal_phrase` turns them into
"ikki ming yigirma beshinchi yil" and refuses case/plural endings
("3-ta", "5-ga", "1990-larda"), whose spoken form is a fused cardinal, so
those keep their digits (a false negative, never a mangled word).

Apostrophes in the output are ASCII ``'`` — the same form
``text_normalization`` folds Uzbek ``oʻ``/``g‘`` variants to.

Pure Python, no dependencies; output contains no digits.
"""

from __future__ import annotations

import re

# ── Tables ───────────────────────────────────────────────────────────────────

_UNITS = ["nol", "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz"]
_TENS = [
    None, "o'n", "yigirma", "o'ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to'qson",
]
HUNDRED = "yuz"
# (value, word), largest first.
_SCALES = [(10**9, "milliard"), (10**6, "million"), (10**3, "ming")]
MAX_CARDINAL = 10**12 - 1

DECIMAL_WORD = "butun"
PERCENT_WORD = "foiz"
# Fraction denominators by digit count: 0.5 → o'ndan besh, 0.05 → yuzdan besh.
# Three digits is omitted on purpose: "10.000" is a thousands group.
_DENOMINATORS = {1: "o'ndan", 2: "yuzdan", 4: "o'n mingdan", 5: "yuz mingdan", 6: "milliondan"}

_VOWELS = frozenset("aeiou")

# Hyphen suffixes that are ordinal markers themselves: "5-chi", "5-inchi".
_ORDINAL_MARKERS = ("inchi", "nchi", "ichi", "chi")

# A hyphen-attached token made only of case / plural / possessive endings
# ("3-ta", "5-ga", "1990-larda", "2-sini"): the spoken form fuses the
# ending onto the cardinal with sound changes, so these stay as digits.
_CASE_ENDING_RE = re.compile(
    r"(?:ta|lar|lik)?(?:i|si|imiz|ingiz|lari)?"
    r"(?:ni|ning|da|dan|ga|ka|qa|gacha|dagi|dek|day)?"
)


# ── Building blocks ──────────────────────────────────────────────────────────

def _below_thousand(n: int) -> list[str]:
    """1-999 as a word list (empty for 0)."""
    words: list[str] = []
    hundreds, rest = divmod(n, 100)
    if hundreds:
        if hundreds > 1:
            words.append(_UNITS[hundreds])
        words.append(HUNDRED)
    tens, unit = divmod(rest, 10)
    if tens:
        words.append(_TENS[tens])
    if unit:
        words.append(_UNITS[unit])
    return words


# ── Public API ───────────────────────────────────────────────────────────────

def cardinal(n: int) -> str:
    """Render an integer 0 ≤ n ≤ 999 999 999 999 as Uzbek words."""
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError("cardinal() expects an int")
    if n < 0 or n > MAX_CARDINAL:
        raise ValueError("cardinal() supports 0..999999999999")
    if n == 0:
        return _UNITS[0]
    words: list[str] = []
    for value, word in _SCALES:
        count, n = divmod(n, value)
        if count:
            # "bir ming", "bir million": the count is always spoken here,
            # unlike a leading hundred ("yuz").
            words.extend(_below_thousand(count) if count > 1 else [_UNITS[1]])
            words.append(word)
    words.extend(_below_thousand(n))
    return " ".join(words)


def ordinal(n: int) -> str:
    """5 → beshinchi, 2 → ikkinchi, 50 → elliginchi, 2025 → … yigirma beshinchi."""
    head, _, last = cardinal(n).rpartition(" ")
    if last == "ellik":
        last = "elligi"
    last += "nchi" if last[-1] in _VOWELS else "inchi"
    return f"{head} {last}" if head else last


def ordinal_phrase(n: int, word: str) -> str:
    """Speak a hyphenated ordinal: (2025, "yil") → "ikki ming yigirma beshinchi yil".

    ``word`` is the token after the hyphen. An ordinal marker ("chi",
    "inchi", optionally followed by case endings) merges into the ordinal
    ("5-chisi" → "beshinchisi"); a token made only of case endings raises
    ``ValueError`` so the caller keeps the digits.
    """
    lower = word.lower()
    for marker in _ORDINAL_MARKERS:
        if lower.startswith(marker) and _CASE_ENDING_RE.fullmatch(lower[len(marker):]):
            return ordinal(n) + word[len(marker):]
    if _CASE_ENDING_RE.fullmatch(lower):
        raise ValueError("case ending, not an ordinal")
    return f"{ordinal(n)} {word}"


def decimal(int_part: int, frac_digits: str) -> str:
    """3.5 → uch butun o'ndan besh; a 3-digit fraction is a thousands group."""
    denominator = _DENOMINATORS.get(len(frac_digits))
    if denominator is None:
        raise ValueError("unsupported fraction length")
    return f"{cardinal(int_part)} {DECIMAL_WORD} {denominator} {cardinal(int(frac_digits))}"


def percent(raw: str) -> str:
    """'50' → ellik foiz; '2.5' → ikki butun o'ndan besh foiz."""
    if "." in raw:
        a, b = raw.split(".", 1)
        body = decimal(int(a), b)
    else:
        body = cardinal(int(raw))
    return f"{body} {PERCENT_WORD}"


def grouped(raw: str) -> str:
    """Space-grouped thousands ("1 500 000") → cardinal."""
    return cardinal(int(re.sub(r"\s", "", raw)))
