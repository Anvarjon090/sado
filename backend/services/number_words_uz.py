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
"ikki ming yigirma beshinchi yil" and refuses case endings ("3-ta",
"5-ga"), which :func:`fused` reads as a fused cardinal (uchta, beshga).
Plural "-lar" ("1990-larda") keeps its digits: it names a decade.

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


# ── Extended readings (2026-11) ──────────────────────────────────────────────
#
# Forms Uzbek prose writes with digits that the cardinal/ordinal rules above
# refused or never saw. Each helper returns a digit-free string or raises
# ``ValueError`` so the caller keeps the original text.

# Endings that fuse onto a cardinal: "3-ta" → uchta, "5-ga" → beshga,
# "10-dan" → o'ndan, "2-tasi" → ikkitasi. Plural "-lar" is not here on
# purpose: "1990-larda" is read as a decade ("to'qsoninchi yillarda").
_FUSED_ENDING_RE = re.compile(
    r"(?:ta(?:si|sini|sining|sida|sidan|siga|lab|dan|ga|da|ni|gacha)?"
    r"|ni|ning|da|dan|ga|gacha|dagi|dek|day)"
)


def fused(n: int, ending: str) -> str:
    """(3, "ta") → uchta; (50, "ga") → ellikka; (1, "ta") → bitta."""
    lower = ending.lower()
    if not _FUSED_ENDING_RE.fullmatch(lower):
        raise ValueError("not a fusing ending")
    head, _, last = cardinal(n).rpartition(" ")
    if last == "bir" and lower.startswith("ta"):
        last = "bit"  # bir + ta → bitta
    if lower.startswith("g"):
        if last.endswith("k"):
            ending = "k" + ending[1:]
        elif last.endswith("q"):
            ending = "q" + ending[1:]
    word = last + ending
    return f"{head} {word}" if head else word


def clock(h: int, m: int) -> str:
    """14:30 → o'n to'rt o'ttiz; 9:05 → to'qqiz nol besh; 14:00 → o'n to'rt nol nol."""
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("not a clock time")
    if m == 0:
        tail = f"{_UNITS[0]} {_UNITS[0]}"
    elif m < 10:
        tail = f"{_UNITS[0]} {cardinal(m)}"
    else:
        tail = cardinal(m)
    return f"{cardinal(h)} {tail}"


MONTHS = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]


def date(day: int, month: int, year: int) -> str:
    """(9, 11, 2026) → to'qqizinchi noyabr ikki ming yigirma oltinchi yil."""
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1000 <= year <= 2999):
        raise ValueError("not a date")
    return f"{ordinal(day)} {MONTHS[month - 1]} {ordinal(year)} yil"


def fraction(num: int, den: int) -> str:
    """1/2 → ikkidan bir; 3/4 → to'rtdan uch (the denominator leads)."""
    if not (0 < num < den <= 100):
        raise ValueError("not a simple fraction")
    return f"{cardinal(den)}dan {cardinal(num)}"


CURRENCIES = {
    "$": ("dollar", "sent"),
    "€": ("yevro", "sent"),
    "£": ("funt sterling", "pens"),
    "₽": ("rubl", "tiyin"),
    "₸": ("tenge", "tiyin"),
    "¥": ("yuan", None),
}


def money(symbol: str, whole: str, cents: str | None = None) -> str:
    """("$", "5", "50") → besh dollar ellik sent."""
    unit, minor = CURRENCIES[symbol]
    out = f"{cardinal(int(whole))} {unit}"
    if cents is not None:
        if minor is None or len(cents) != 2:
            raise ValueError("unsupported minor unit")
        if int(cents):
            out += f" {cardinal(int(cents))} {minor}"
    return out


def digits(raw: str) -> str:
    """Read a digit run one digit at a time: "1234567" → bir ikki uch ….

    Card and account numbers are spoken this way, and it is the only reading
    the TTS engines handle reliably: a raw run of seven or more digits makes
    Navoiy babble instead of speaking.
    """
    return " ".join(_UNITS[int(d)] for d in raw if d.isdigit())


def digit_group(raw: str) -> str:
    """A phone-number group: "05" → nol besh, "123" → bir yuz yigirma uch."""
    if raw.startswith("0"):
        return " ".join(_UNITS[int(d)] for d in raw)
    n = int(raw)
    words = cardinal(n)
    # Read "123" as "bir yuz yigirma uch" in a phone number: every group
    # stands alone, so the leading hundred is spoken in full.
    if 100 <= n < 200:
        words = f"{_UNITS[1]} {words}"
    return words


def phone(groups: list[str], plus: bool) -> str:
    """["998", "90", "123", "45", "67"] → to'qqiz yuz … , to'qson, bir yuz …"""
    spoken = ", ".join(digit_group(g) for g in groups)
    return f"plyus {spoken}" if plus else spoken


_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_ROMAN_RE = re.compile(r"^(?:C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$")


def roman(raw: str) -> int:
    """'XXI' → 21 (I–CCCXCIX, canonical spelling only)."""
    if not raw or not _ROMAN_RE.fullmatch(raw):
        raise ValueError("not a Roman numeral")
    total, prev = 0, 0
    for ch in reversed(raw):
        value = _ROMAN[ch]
        total += -value if value < prev else value
        prev = max(prev, value)
    return total


def signed(sign: str, body: str) -> str:
    """("-", "uch") → minus uch; ("+", …) → plyus …"""
    return f"{'minus' if sign in '-−' else 'plyus'} {body}"


DEGREE_WORD = "daraja"


# ── Script conversion (Uzbek Cyrillic) ───────────────────────────────────────
#
# Uzbek is still written in Cyrillic too. Numbers inside Cyrillic Uzbek text
# are verbalized with the Latin tables above and the generated words are
# transliterated, so the engine sees one script per word.

_LAT2CYR_DIGRAPHS = [
    ("o'", "ў"), ("O'", "Ў"), ("g'", "ғ"), ("G'", "Ғ"),
    ("sh", "ш"), ("Sh", "Ш"), ("ch", "ч"), ("Ch", "Ч"),
    ("yo", "ё"), ("Yo", "Ё"), ("yu", "ю"), ("Yu", "Ю"),
    ("ya", "я"), ("Ya", "Я"), ("ye", "е"), ("Ye", "Е"),
]
_LAT2CYR = dict(zip(
    "abdefghijklmnopqrstuvxyzABDEFGHIJKLMNOPQRSTUVXYZ'",
    "абдефгҳижклмнопқрстувхйзАБДЕФГҲИЖКЛМНОПҚРСТУВХЙЗъ",
))


def to_cyrillic(text: str) -> str:
    """Latin Uzbek (as produced here) → Cyrillic: "o'n to'rt" → "ўн тўрт"."""
    out: list[str] = []
    i = 0
    while i < len(text):
        pair = text[i:i + 2]
        hit = next((cyr for lat, cyr in _LAT2CYR_DIGRAPHS if pair == lat), None)
        if hit:
            out.append(hit)
            i += 2
            continue
        ch = text[i]
        word_start = i == 0 or not text[i - 1].isalpha()
        if ch in "eE" and word_start:
            out.append("э" if ch == "e" else "Э")
        else:
            out.append(_LAT2CYR.get(ch, ch))
        i += 1
    return "".join(out)


_CYR2LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "ъ": "'", "ь": "",
    "э": "e", "ю": "yu", "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}


def to_latin(text: str) -> str:
    """Cyrillic Uzbek → Latin, used only on the suffix glued to a number."""
    out = []
    for ch in text:
        lat = _CYR2LAT.get(ch.lower())
        if lat is None:
            out.append(ch)
        else:
            out.append(lat.capitalize() if ch.isupper() and lat else lat)
    return "".join(out)
