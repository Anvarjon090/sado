"""Engine-agnostic text normalization — a conservative pre-pass before TTS.

Raw user text trips TTS engines: digits, clock times, and title abbreviations
mispronounce; zero-width junk and pathological repeat runs cause hallucinations
and long dead air. This module cleans text *once*, at the point where each
pipeline hands text to an engine (single-shot /generate, dub segments,
longform chapters), so every engine benefits equally.

Design rules (load-bearing):

  * **Conservative.** A false negative (digits left alone) is fine; a false
    positive (mangled meaning) is not. Anything ambiguous — thousands-grouped
    numbers ("1,000"), ranges ("3-5"), version strings ("v2", "3.5.1"),
    leading-zero codes ("007"), 7+-digit IDs — is left unchanged. Roman
    numerals are out of scope entirely ("I" is a pronoun).
  * **Idempotent.** ``normalize_text(normalize_text(x)) == normalize_text(x)``:
    number/abbreviation output contains no digits or matchable tokens and the
    safety filters are fixed-point by construction, so an accidental second
    pass through a pipeline is harmless.
  * **Per-language.** Numbers go through ``num2words`` only for languages it
    supports (``_NUM2WORDS_LANGS``; the request's ``language`` is a full
    display name from electron/src/shared/languages.json or an ISO-ish code — both
    resolve via :func:`_num2words_lang`), or through a hand-written native
    verbalizer for languages num2words lacks (``_NATIVE_VERBALIZERS``, e.g.
    Malayalam, Uzbek). Everything else keeps its digits. Uzbek also folds its
    apostrophe variants (``oʻ``/``o‘``/``o’``) to ASCII ``'``.
    Clock times / ordinals / currency are English-only on the num2words path
    (their spoken form is language-specific), plus Russian times, percents and
    ordinals; Uzbek's native module also reads phones, dates, prices,
    temperatures, fractions, ranges and Roman centuries. Decimals only for
    locales whose num2words rendering was vetted.
  * **Per-clause language.** For en/ru/uz requests each number is read in the
    language of its own clause (``services/number_language.py``), so an
    English line inside an Uzbek script keeps English numbers. CJK scripts pass through the safety filters untouched — no
    CJK punctuation is stripped and no words are injected into unsegmented
    text.
  * **Markup-safe.** The single-bracket grammar (``[voice:…]``, ``[pause …]``,
    SSML-lite) and inline ``[[…]]`` pronunciation overrides are never touched:
    the language passes skip every ``[…]`` span (same shape as chunked_tts's
    ``_BRACKET_TAG_RE``), so ``[pause 300ms]`` / ``[rate 0.9]`` stay parseable.

Ordering vs. the pronunciation dictionary (audited 2026-07-10): normalization
runs **BEFORE** ``services.pronunciation.apply_pronunciation`` (and before the
audiobook ``apply_lexicon`` overlay). Rationale from the code:

  1. Dictionary respellings are the user's explicit, final say. If
     normalization ran second it would re-process them — a respelling that
     deliberately contains digits or an abbreviation must reach the engine
     verbatim.
  2. Users already write lexicon entries against display text (the lexicon
     docstring's own example is ``{"Dr": "Doctor"}``); entries keyed on
     normalized words keep firing, and the dictionary stays the override for
     anything the normalizer produced.
  3. Inline ``[[…]]`` overrides resolve last inside ``apply_pronunciation``
     (and their bracketed content is masked here), so the user retains a
     per-occurrence override over any normalizer output.

Pinned by ``tests/test_text_normalization.py`` (dictionary-order test).

Gate: default ON; the ``OMNIVOICE_TEXT_NORMALIZATION`` env var disables it,
the same contract as ``OMNIVOICE_PRONUNCIATION`` ("0"/"false"/"no"/"off").
:func:`normalize_for_tts` is the gated entry point every pipeline calls; it
never raises — normalization is never allowed to break synthesis.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Callable, Optional

logger = logging.getLogger("omnivoice.text_normalization")

ENV_VAR = "OMNIVOICE_TEXT_NORMALIZATION"


# ── Language resolution ───────────────────────────────────────────────────────
#
# The `language` kwarg across the app is normally a full display name from
# electron/src/shared/languages.json ("English", "German", …) — see
# resolve_kokoro_lang_code in services/tts_backend.py — but ISO-ish codes
# ("en", "pt-BR") also flow through dub/API callers. Map both to a num2words
# locale; anything unmapped keeps its digits (false negatives are fine).

_FULL_NAME_TO_CODE = {
    "english": "en",
    "malayalam": "ml",
    "uzbek": "uz",
    "northern uzbek": "uz",
    "german": "de",
    "spanish": "es",
    "french": "fr",
    "italian": "it",
    "portuguese": "pt",
    "dutch": "nl",
    "russian": "ru",
    "ukrainian": "uk",
    "polish": "pl",
    "turkish": "tr",
    "czech": "cs",
    "danish": "da",
    "finnish": "fi",
    "swedish": "sv",
    "norwegian": "no",
    "norwegian bokmål": "no",
    "norwegian nynorsk": "no",
    "romanian": "ro",
    "hungarian": "hu",
    "indonesian": "id",
    "lithuanian": "lt",
    "latvian": "lv",
    "slovenian": "sl",
    "serbian": "sr",
    "hebrew": "he",
    "persian": "fa",
    "azerbaijani": "az",
    # "vietnamese" → "vi" kept for documentation, but vi is deliberately
    # absent from _NUM2WORDS_LANGS (see the note there): the membership gate
    # in _num2words_lang makes this entry inert, so Vietnamese keeps digits.
    "vietnamese": "vi",
    "kazakh": "kz",
    "standard arabic": "ar",
    # Below: inert for num2words (absent from _NUM2WORDS_LANGS, which reads
    # digits natively for these scripts), present so _plain_lang_code can
    # resolve them for the digit-range rule.
    "korean": "ko",
    "japanese": "ja",
    "chinese": "zh",
    "mandarin chinese": "zh",
}

# ISO codes whose num2words locale name differs.
_ISO_ALIASES = {"kk": "kz", "uzn": "uz"}

# Locales verified against the pinned num2words (cardinal + basic rendering).
# zh/ja/ko/th are deliberately absent: unsegmented scripts where injecting
# space-delimited words is wrong, and their engines read digits natively.
# vi is absent too (#1139): num2words' Vietnamese cardinals misuse "lẻ" for
# 2001-2099 ("hai nghìn lẻ hai mươi bốn" for 2024 — "lẻ" is only valid before
# a lone units digit) and there is no to="year" form, so years read wrong;
# the engine pronounces Vietnamese digits natively, so digits pass through —
# the same conservative rule that already excludes vi from _DECIMAL_LANGS.
_NUM2WORDS_LANGS = frozenset({
    "en", "de", "es", "fr", "it", "pt", "nl", "ru", "uk", "pl", "tr", "cs",
    "da", "fi", "sv", "no", "ro", "hu", "id", "lt", "lv", "sl", "sr", "ar",
    "he", "fa", "az", "kz",
})

# Locales whose num2words decimal rendering was vetted ("drei Komma fünf",
# "три целых пять десятых", …). tr/vi are excluded on purpose: their 0.5
# renders as "fifty" (wrong), so decimals keep their digits there.
_DECIMAL_LANGS = frozenset({
    "en", "de", "es", "fr", "it", "pt", "nl", "ru", "uk", "pl", "cs", "da",
    "no", "sv", "fi", "ro", "hu", "id",
})

# Every vetted locale except English writes decimals with a comma and groups
# thousands with a period: "1.000" is one thousand there, not 1.0.
_COMMA_DECIMAL_LANGS = _DECIMAL_LANGS - {"en"}


def _thousands_group(lang: str, fraction: str) -> bool:
    """True when a period-separated ``fraction`` is a thousands group for
    ``lang`` ("10.000" in German), which keeps its digits like "1,000" in
    English does. English keeps "3.500" as a decimal."""
    return lang in _COMMA_DECIMAL_LANGS and len(fraction) == 3


# "50%" → "fifty <word>" only where the spoken percent word is unambiguous.
_PERCENT_WORD = {
    "en": "percent",
    "de": "Prozent",
    "es": "por ciento",
    "fr": "pour cent",
    "it": "per cento",
    "pt": "por cento",
    "nl": "procent",
}

_ISO_CODE_RE = re.compile(r"^([a-z]{2,3})(?:[-_]|$)")


def _num2words_lang(language: Optional[str]) -> Optional[str]:
    """Resolve a request language (display name or ISO-ish code) to a
    num2words locale, or ``None`` when digits should be left alone.

    Both lookup paths gate on ``_NUM2WORDS_LANGS`` — the vetted set is the
    single authority. Display names used to bypass it (#1139: "Vietnamese"
    reached num2words while "vi" wouldn't have), so an unvetted locale could
    mangle numbers depending on how the caller spelled the language.
    """
    if not language:
        return None
    s = str(language).strip().lower()
    if not s or s == "auto":
        return None
    code = _FULL_NAME_TO_CODE.get(s)
    if code:
        return code if code in _NUM2WORDS_LANGS else None
    m = _ISO_CODE_RE.match(s)
    if m:
        c = _ISO_ALIASES.get(m.group(1), m.group(1))
        if c in _NUM2WORDS_LANGS:
            return c
    return None


def _plain_lang_code(language: Optional[str]) -> Optional[str]:
    """Resolve a request language to a bare ISO code, with no num2words gate.

    :func:`_num2words_lang` answers "may I call num2words for this?" and so
    returns ``None`` for ko/ja/zh/th/vi. Rules that are not num2words-backed
    need the code itself, which is what this returns.
    """
    if not language:
        return None
    s = str(language).strip().lower()
    if not s or s == "auto":
        return None
    code = _FULL_NAME_TO_CODE.get(s)
    if code:
        return code
    m = _ISO_CODE_RE.match(s)
    if m:
        return _ISO_ALIASES.get(m.group(1), m.group(1))
    return None


# ── Digit ranges ─────────────────────────────────────────────────────────────
# "20~30" loses its separator at the engine and reads as ONE number: OmniVoice
# says "이십삼" (23) for "20~30초". Speak the separator instead. Verified by
# rendering each form and transcribing it back (ko, OmniVoice):
#     "20~30초"        → heard "23초"          ✗
#     "20에서 30초"     → heard "20에서 30초"    ✓
# Only the tilde family is rewritten — those are unambiguously range marks
# between digits. An ASCII hyphen is left alone on purpose: it also spells
# dates, phone numbers and product codes, where "to" would be wrong.
#: Spacing is part of the form, not decoration: a Korean postposition binds to
#: the numeral ("20에서 30"), Japanese and Chinese set no spaces at all, and
#: English needs them on both sides.
_RANGE_FORM = {
    "ko": "{a}에서 {b}",
    "ja": "{a}から{b}",
    "zh": "{a}到{b}",
    "en": "{a} to {b}",
}

#: ASCII tilde, wave dash, fullwidth tilde — Japanese and Korean IMEs emit the
#: latter two, so all three have to match.
#:
#: Match complete signed/decimal endpoints; reject partial numbers and product
#: codes while allowing adjacent CJK units. Guard all tilde forms so malformed
#: chains cannot be partially rewritten, including when their separators have
#: whitespace around them.
_RANGE_MARKS = "~\u301c\uff5e"
_RANGE_ENDPOINT = r"[+-]?(?:\d{1,6}(?:\.\d{1,6})?|\.\d{1,6})"
_NUM_RANGE_RE = re.compile(
    rf"(?<![\d.,A-Za-z+{_RANGE_MARKS}-])({_RANGE_ENDPOINT})"
    rf"\s*[{_RANGE_MARKS}]\s*({_RANGE_ENDPOINT})"
    rf"(?![\d.,A-Za-z+{_RANGE_MARKS}-])"
)


def _speak_number_ranges(text: str, lang: str) -> str:
    """Speak complete tilde ranges only for languages with a verified form."""
    form = _RANGE_FORM.get(lang)
    if not form:
        return text

    def replace(match: re.Match) -> str:
        before, after = match.start() - 1, match.end()
        while before >= 0 and text[before].isspace():
            before -= 1
        while after < len(text) and text[after].isspace():
            after += 1
        if ((before >= 0 and text[before] in _RANGE_MARKS)
                or (after < len(text) and text[after] in _RANGE_MARKS)):
            return match.group(0)
        return form.format(a=match.group(1), b=match.group(2))

    return _NUM_RANGE_RE.sub(replace, text)


# ── Universal safety filters (all languages) ─────────────────────────────────

# Zero-width & bidi controls, C0/C1 controls (except \t \n \r), BOM, U+FFFD.
# Keep the set explicit rather than encoding it as regex character ranges: the
# latter is easy to widen accidentally and obscures the intentionally preserved
# whitespace controls at the C0 boundaries.
_UNSAFE_CONTROL_CODEPOINTS = frozenset(
    (
        *range(0x00, 0x09),
        0x0B,
        0x0C,
        *range(0x0E, 0x20),
        *range(0x7F, 0xA0),
        *range(0x200B, 0x2010),
        *range(0x202A, 0x202F),
        *range(0x2060, 0x2065),
        0xFEFF,
        0xFFFD,
    )
)
_UNSAFE_CONTROL_TRANSLATION = dict.fromkeys(_UNSAFE_CONTROL_CODEPOINTS)


def _strip_unsafe_controls(text: str) -> str:
    """Delete only the explicitly enumerated unsafe Unicode controls."""
    return text.translate(_UNSAFE_CONTROL_TRANSLATION)

# A tiny, unambiguous HTML-entity leftover set. `&amp;` is decoded only when
# NOT followed by a letter/`#` — so double-encoded junk ("&amp;nbsp;") is left
# alone rather than decoded one layer per pass (idempotency).
_ENTITIES = {
    "&nbsp;": " ",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
    "&hellip;": "…",
    "&mdash;": "—",
    "&ndash;": "–",
}
_ENTITY_RE = re.compile(
    "(?:" + "|".join(re.escape(k) for k in _ENTITIES) + "|&amp;(?![a-zA-Z#]))"
)

# Same ASCII punctuation char repeated more than 3 times → capped at 3
# ("!!!!!!!!" / "........." cause dead air and babble). CJK punctuation and
# letters are deliberately untouched ("Nooooo" is expressive).
_REPEAT_RE = re.compile(r"([!?.,;:~_*#=-])\1{3,}")

_HSPACE_RE = re.compile(r"[^\S\n]+")   # horizontal whitespace runs → one space
_NEWLINE_RE = re.compile(r"\n{3,}")    # blank-line floods → one blank line


def _safety_filters(text: str) -> str:
    out = _strip_unsafe_controls(text)
    out = _ENTITY_RE.sub(lambda m: _ENTITIES.get(m.group(0), "&"), out)
    out = _REPEAT_RE.sub(lambda m: m.group(1) * 3, out)
    out = _HSPACE_RE.sub(" ", out)
    out = _NEWLINE_RE.sub("\n\n", out)
    return out.strip()


# ── Bracket masking ──────────────────────────────────────────────────────────
#
# Language passes must never rewrite `[…]` spans: `[pause 300ms]` /
# `[rate 0.9]` / `[voice:NAME]` are grammar, and `[[term|replacement]]`
# belongs to the pronunciation layer. Bounded repetition keeps it linear.

_BRACKET_SPAN_RE = re.compile(r"\[[^\][\n]{0,128}\]")


def _outside_brackets(text: str, fn: Callable[[str], str]) -> str:
    if "[" not in text:
        return fn(text)
    parts: list[str] = []
    last = 0
    for m in _BRACKET_SPAN_RE.finditer(text):
        parts.append(fn(text[last:m.start()]))
        parts.append(m.group(0))
        last = m.end()
    parts.append(fn(text[last:]))
    return "".join(parts)


# ── Abbreviation expansion ────────────────────────────────────────────────────
#
# Per-language (key, expansion, guard) triples. Matching is case-sensitive
# (a lowercase "st." is NOT the title "St."); lowercase connective keys
# ("e.g.") get an auto-added sentence-initial variant. Guards:
#   "cap"   — only before a capitalized word (titles precede names; leaves
#             street-suffix "Elm St." / "Elm Dr." untouched).
#   "digit" — only before a number ("No. 5"; leaves the word "No." alone).

_ABBREVIATIONS: dict[str, list[tuple[str, str, Optional[str]]]] = {
    "en": [
        ("Dr.", "Doctor", "cap"),
        ("Mr.", "Mister", "cap"),
        ("Mrs.", "Missus", "cap"),
        ("Prof.", "Professor", "cap"),
        ("St.", "Saint", "cap"),
        ("Mt.", "Mount", "cap"),
        ("Jr.", "Junior", None),
        ("Sr.", "Senior", None),
        ("vs.", "versus", None),
        ("etc.", "et cetera", None),
        ("e.g.", "for example", None),
        ("i.e.", "that is", None),
        ("approx.", "approximately", None),
        ("No.", "number", "digit"),
    ],
    "de": [
        ("Dr.", "Doktor", "cap"),
        ("Prof.", "Professor", "cap"),
        ("Nr.", "Nummer", "digit"),
        ("z.B.", "zum Beispiel", None),
        ("z. B.", "zum Beispiel", None),
        ("d.h.", "das heißt", None),
        ("d. h.", "das heißt", None),
        ("usw.", "und so weiter", None),
        ("bzw.", "beziehungsweise", None),
        ("ca.", "circa", None),
    ],
    "es": [
        ("Sr.", "Señor", "cap"),
        ("Sra.", "Señora", "cap"),
        ("Srta.", "Señorita", "cap"),
        ("Dr.", "Doctor", "cap"),
        ("Dra.", "Doctora", "cap"),
        ("Ud.", "usted", None),
        ("Uds.", "ustedes", None),
        ("etc.", "etcétera", None),
        ("núm.", "número", "digit"),
    ],
    "fr": [
        # "M." is deliberately absent: indistinguishable from a middle initial.
        ("Mme", "Madame", "cap"),
        ("Mmes", "Mesdames", "cap"),
        ("Mlle", "Mademoiselle", "cap"),
        ("Mlles", "Mesdemoiselles", "cap"),
        ("etc.", "et cetera", None),
        ("n°", "numéro", "digit"),
        ("N°", "Numéro", "digit"),
    ],
    "uz": [
        # Unit and list abbreviations that are unambiguous in Uzbek prose.
        ("h.k.", "hokazo", None),
        ("mln", "million", None),
        ("mlrd", "milliard", None),
        ("km", "kilometr", None),
        ("kg", "kilogramm", None),
    ],
}

_GUARD_LOOKAHEAD = {
    None: "",
    "cap": r"(?=\s+[A-ZÀ-ÖØ-Þ])",
    "digit": r"(?=\s*\d)",
}


def _compile_abbreviations() -> dict[str, tuple[re.Pattern, dict[str, str]]]:
    compiled: dict[str, tuple[re.Pattern, dict[str, str]]] = {}
    for lang, entries in _ABBREVIATIONS.items():
        entries = list(entries)
        # Sentence-initial variants for lowercase connectives ("E.g." → …).
        for key, expansion, guard in list(entries):
            if key[:1].islower():
                cap_key = key[0].upper() + key[1:]
                if not any(k == cap_key for k, _, _ in entries):
                    entries.append((cap_key, expansion[0].upper() + expansion[1:], guard))
        entries.sort(key=lambda e: len(e[0]), reverse=True)  # longest key wins
        lookup = {key: expansion for key, expansion, _ in entries}
        alts = []
        for key, _, guard in entries:
            suffix = r"(?!\w)" if key[-1:].isalnum() else ""
            alts.append(f"{re.escape(key)}{suffix}{_GUARD_LOOKAHEAD[guard]}")
        # Literal alternation with per-key guards; no nested quantifiers.
        pattern = re.compile(r"(?<![\w.])(?:" + "|".join(alts) + ")")
        compiled[lang] = (pattern, lookup)
    return compiled


_ABBREV_COMPILED = _compile_abbreviations()


def _expand_abbreviations(text: str, lang: str) -> str:
    entry = _ABBREV_COMPILED.get(lang)
    if entry is None:
        return text
    pattern, lookup = entry

    def _repl(m: re.Match) -> str:
        return lookup.get(m.group(0), m.group(0))

    return pattern.sub(_repl, text)


# ── Numbers → words ──────────────────────────────────────────────────────────
#
# Every pattern requires clean word boundaries: digits glued to letters
# ("MP3", "v2"), separators ("1,000", "3-5", "1/2", "12:34:56"), leading
# zeros ("007") or 7+ digits (IDs, phone numbers) are all left alone.

# EN-only clock time: H:MM, 0-23 hours. Rejects H:MM:SS (durations).
_TIME_RE = re.compile(r"(?<![\w:.,/$%+-])([01]?\d|2[0-3]):([0-5]\d)(?![\w:/%+-])(?![.,]\d)")

# EN-only ordinal, suffix verified in the callback ("2th" stays as-is).
_ORDINAL_RE = re.compile(r"(?<![\w.,:/$%+-])(\d{1,4})(st|nd|rd|th)(?![\w:/%+-])(?![.,]\d)")

# EN-only dollars: $N or $N.CC. "$1,000" and "$5.5" are blocked by the
# lookahead; a period or comma that ends the sentence or clause is not, the
# same guard the integer and decimal rules use ("It costs $5." is spoken).
_CURRENCY_RE = re.compile(r"(?<![\w.,:/$%+-])\$(\d{1,6})(?:\.(\d{2}))?(?![\w:/%+-])(?![.,]\d)")

_PERCENT_RE = re.compile(r"(?<![\w.,:/$%+-])(\d{1,6}(?:\.\d{1,4})?)\s?%(?![\w:/%+-])(?![.,]\d)")

_DECIMAL_RE = re.compile(
    r"(?<![\w.,:/$%-])(\d{1,6})\.(\d{1,6})(?![\w:/%-])(?![.,]\d)"
)

_INTEGER_RE = re.compile(
    r"(?<![\w.,:/$%-])(?!0\d)(\d{1,6})(?![\w:/%-])(?![.,]\d)"
)

_ORDINAL_SUFFIX = {1: "st", 2: "nd", 3: "rd"}


def _glued_to_mark(m: re.Match) -> bool:
    """True when the match touches a combining mark (``ാ``, ``്``, …).

    Python's ``\\w`` excludes Unicode marks, so the regex boundaries above
    treat "10ാം" or "ക്ലാസ്10" as isolated numbers and splice words into the
    middle of a syllable. A mark belongs to the word it attaches to: leave it.
    """
    s, start, end = m.string, m.start(), m.end()
    return any(
        unicodedata.category(ch).startswith("M")
        for ch in (s[start - 1:start], s[end:end + 1]) if ch
    )


def _leading_zero(raw: str) -> bool:
    """``(?!0\\d)`` only sees ASCII zero; ``\\d`` also matches native digits
    (൦൦൭, ٠٠٧), which must stay codes just like "007"."""
    return len(raw) > 1 and unicodedata.digit(raw[0], -1) == 0


def _correct_ordinal_suffix(n: int) -> str:
    if 10 <= n % 100 <= 13:
        return "th"
    return _ORDINAL_SUFFIX.get(n % 10, "th")


# ── Russian: forms the generic rules leave as digits ────────────────────────
#
# Russian is verbalized for Russian requests and, since mixed-language text is
# judged per clause, for Russian sentences inside Uzbek scripts — where any
# digit left over would be read in Uzbek by the Navoiy engine.

_RU_ORDINAL_RE = re.compile(
    r"(?<![\w.,:/$%+-])(\d{1,4})-(й|ый|ий|ой|я|ая|е|ое|го|ого|му|ому)(?![\w-])"
)
_RU_COMMA_DECIMAL_RE = re.compile(r"(?<![\w.,:/$%-])(\d{1,6}),(\d{1,2})(?![\w:/-])(?![.,]\d)")


def _ru_percent_word(raw: str) -> str:
    if "." in raw:
        return "процента"
    n = int(raw)
    if n % 10 == 1 and n % 100 != 11:
        return "процент"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "процента"
    return "процентов"


def _ru_inflect_ordinal(words: str, ending: str) -> str:
    """'пятый' + 'го' → 'пятого'; only the last word of a compound inflects."""
    head, _, last = words.rpartition(" ")
    if last.endswith("ий"):  # третий
        stem = last[:-2] + "ь"
        forms = {"я": stem + "я", "е": stem + "е", "го": stem + "его", "му": stem + "ему"}
    else:
        stem = last[:-2]
        forms = {"я": stem + "ая", "е": stem + "ое", "го": stem + "ого", "му": stem + "ому"}
    key = {"ая": "я", "ое": "е", "ого": "го", "ому": "му"}.get(ending, ending)
    if key in ("й", "ый", "ий", "ой"):
        return words
    last = forms[key]
    return f"{head} {last}" if head else last


def _russian_forms(text: str, num2words, safe) -> str:
    def clock(m: re.Match) -> str:
        h, mm = int(m.group(1)), int(m.group(2))
        tail = "ноль ноль" if mm == 0 else (
            f"ноль {num2words(mm, lang='ru')}" if mm < 10 else num2words(mm, lang="ru")
        )
        return f"{num2words(h, lang='ru')} {tail}"

    def ordinal(m: re.Match) -> str:
        words = num2words(int(m.group(1)), lang="ru", to="ordinal")
        return _ru_inflect_ordinal(words, m.group(2))

    def percent(m: re.Match) -> str:
        raw = m.group(1)
        value: object = float(raw) if "." in raw else int(raw)
        return f"{num2words(value, lang='ru')} {_ru_percent_word(raw)}"

    text = _TIME_RE.sub(lambda m: safe(m, clock, clock=True), text)
    text = _RU_ORDINAL_RE.sub(lambda m: safe(m, ordinal), text)
    text = _RU_COMMA_DECIMAL_RE.sub(lambda m: f"{m.group(1)}.{m.group(2)}", text)
    text = _PERCENT_RE.sub(lambda m: safe(m, percent), text)
    return text


def _numbers_to_words(text: str, lang: str) -> str:
    try:
        from num2words import num2words
    except ImportError:  # pragma: no cover — direct dependency; belt & braces
        return text

    def _safe(m: re.Match, render: Callable[[re.Match], str], *, clock: bool = False) -> str:
        # Any num2words hiccup leaves this occurrence untouched.
        if _glued_to_mark(m) or (not clock and _leading_zero(m.group(1).partition(".")[0])):
            return m.group(0)
        try:
            return render(m)
        except Exception:  # noqa: BLE001 — conservative: never mangle
            return m.group(0)

    if lang == "en":
        def _time(m: re.Match) -> str:
            h, mm = int(m.group(1)), int(m.group(2))
            hw = num2words(h, lang="en")
            if mm == 0:
                return f"{hw} o'clock"
            if mm < 10:
                return f"{hw} oh {num2words(mm, lang='en')}"
            return f"{hw} {num2words(mm, lang='en')}"

        text = _TIME_RE.sub(lambda m: _safe(m, _time, clock=True), text)

        def _ordinal(m: re.Match) -> str:
            n = int(m.group(1))
            if m.group(2) != _correct_ordinal_suffix(n):
                return m.group(0)
            return num2words(n, lang="en", to="ordinal")

        text = _ORDINAL_RE.sub(lambda m: _safe(m, _ordinal), text)

        def _currency(m: re.Match) -> str:
            dollars = int(m.group(1))
            if m.group(2) is not None:
                amount = float(f"{m.group(1)}.{m.group(2)}")
                return num2words(amount, lang="en", to="currency", currency="USD")
            unit = "dollar" if dollars == 1 else "dollars"
            return f"{num2words(dollars, lang='en')} {unit}"

        text = _CURRENCY_RE.sub(lambda m: _safe(m, _currency), text)

    if lang == "ru":
        text = _russian_forms(text, num2words, _safe)

    percent_word = _PERCENT_WORD.get(lang)
    if percent_word:
        def _percent(m: re.Match) -> str:
            raw = m.group(1)
            if "." in raw:
                fraction = raw.split(".", 1)[1]
                if lang not in _DECIMAL_LANGS or _thousands_group(lang, fraction):
                    return m.group(0)
                value: object = float(raw)
            else:
                value = int(raw)
            return f"{num2words(value, lang=lang)} {percent_word}"

        text = _PERCENT_RE.sub(lambda m: _safe(m, _percent), text)

    if lang in _DECIMAL_LANGS:
        def _decimal(m: re.Match) -> str:
            if _thousands_group(lang, m.group(2)):
                return m.group(0)
            return num2words(float(f"{m.group(1)}.{m.group(2)}"), lang=lang)

        text = _DECIMAL_RE.sub(lambda m: _safe(m, _decimal), text)

    def _integer(m: re.Match) -> str:
        raw = m.group(1)
        if _leading_zero(raw):
            return m.group(0)
        n = int(raw)
        if len(raw) == 4 and 1500 <= n <= 2099:
            # Bare 4-digit numbers in this range read as years
            # ("nineteen eighty-four"); fall back to cardinal where the
            # locale has no year form (sv).
            try:
                return num2words(n, lang=lang, to="year")
            except Exception:  # noqa: BLE001
                pass
        return num2words(n, lang=lang)

    return _INTEGER_RE.sub(lambda m: _safe(m, _integer), text)


# ── Native verbalizers (languages num2words lacks) ──────────────────────────
#
# Same conservative regexes and bracket masking as the num2words path, but the
# rendering is a hand-written module. Malayalam (ml) is the first: num2words
# ships bn/kn/te but no ml, so Malayalam dubs reached the engine with raw
# digits. Uzbek (uz) is the second. Each module exposes ``cardinal(int)``,
# ``decimal(int, str)`` and ``percent(str)``, and optionally
# ``ordinal_phrase(int, str)`` (hyphenated ordinals, "5-sinf") and
# ``grouped(str)`` (space-grouped thousands, "1 500 000"); any exception
# leaves that occurrence untouched.

_NATIVE_VERBALIZERS = {"ml": "services.number_words_ml", "uz": "services.number_words_uz"}

# "5-sinf", "2025-yil": a number glued by a hyphen to a following word. The
# lookbehind rejects ranges and chains ("2024-2025-yil" keeps its digits).
_HYPHEN_ORDINAL_RE = re.compile(
    r"(?<![\w.,:/$%+'-])(\d{1,6})-((?:[^\W\d_]|')+)"
)

# "1 500 000": thousands grouped by spaces. Neighbouring digit groups are
# rejected on both sides so phone numbers ("+998 90 123 45 67") stay intact.
_SPACE_GROUPED_RE = re.compile(
    r"(?<![\w.,:/$%+-])(?<!\d )(\d{1,3}(?: \d{3})+)(?![\w:/%-])(?![.,]\d)(?! \d)"
)


def _native_lang(language: Optional[str]) -> Optional[str]:
    """Resolve a request language to a native-verbalizer code, or ``None``."""
    plain = _plain_lang_code(language)
    return plain if plain in _NATIVE_VERBALIZERS else None


def _numbers_to_words_native(text: str, lang: str) -> str:
    """Verbalize percent, decimal and integer tokens via the native module
    for ``lang``; any failure leaves the input untouched."""
    import importlib

    try:
        mod = importlib.import_module(_NATIVE_VERBALIZERS[lang])
    except Exception:  # noqa: BLE001 — never break synthesis
        return text

    def _safe(m: re.Match, render: Callable[[re.Match], str]) -> str:
        """Render one match; on any error return the original text."""
        if _glued_to_mark(m) or _leading_zero(m.group(1).partition(".")[0]):
            return m.group(0)
        try:
            return render(m)
        except Exception:  # noqa: BLE001 — conservative: never mangle
            return m.group(0)

    if lang == "uz":
        text = _uzbek_extended_forms(text, mod)
    if hasattr(mod, "ordinal_phrase"):
        def _hyphenated(m: re.Match) -> str:
            n, word = int(m.group(1)), m.group(2)
            try:
                return mod.ordinal_phrase(n, word)
            except ValueError:
                if not hasattr(mod, "fused"):
                    raise
                return mod.fused(n, word)  # "3-ta" → uchta, "5-ga" → beshga

        text = _HYPHEN_ORDINAL_RE.sub(lambda m: _safe(m, _hyphenated), text)
    if hasattr(mod, "grouped"):
        text = _SPACE_GROUPED_RE.sub(lambda m: _safe(m, lambda m: mod.grouped(m.group(1))), text)
    text = _PERCENT_RE.sub(lambda m: _safe(m, lambda m: mod.percent(m.group(1))), text)
    text = _DECIMAL_RE.sub(
        lambda m: _safe(m, lambda m: mod.decimal(int(m.group(1)), m.group(2))), text
    )
    def _integer(m: re.Match) -> str:
        raw = m.group(1)
        return m.group(0) if _leading_zero(raw) else mod.cardinal(int(raw))

    return _INTEGER_RE.sub(lambda m: _safe(m, _integer), text)


# ── Uzbek: forms beyond plain numbers ────────────────────────────────────────
#
# Written Uzbek puts digits in phone numbers, dates, clock times, prices,
# temperatures, fractions, ranges and Roman-numbered centuries. Each rule
# below is anchored on the shape that makes it unambiguous and runs before
# the generic integer rule would split it apart.

_UZ_PHONE_RE = re.compile(
    r"(?<![\w+])(\+)?(998)[\s-]?\(?(\d{2})\)?[\s-]?(\d{3})[\s-]?(\d{2})[\s-]?(\d{2})(?![\w-])"
    r"|(?<![\w+])(?<!\d )\(?(\d{2})\)?[\s-](\d{3})[\s-](\d{2})[\s-](\d{2})(?![\w-])(?! \d)"
)
_UZ_DATE_RE = re.compile(
    r"(?<![\w.,:/-])(\d{1,2})\.(\d{1,2})\.(\d{4})(?![\w-])(?!\.\d)"
    r"|(?<![\w.,:/-])(\d{4})-(\d{2})-(\d{2})(?![\w-])"
)
_UZ_RANGE_RE = re.compile(
    r"(?<![\w.,:/$%+-])(\d{1,4})[-–](\d{1,4})(?:-((?:[^\W\d_]|')+)|(?=\s+[^\W\d_]))"
)
_UZ_MONEY_RE = re.compile(
    r"(?<![\w.,])([$€£₽₸¥])\s?(\d{1,9})(?:[.,](\d{2}))?(?![\w:/%-])(?![.,]\d)"
    r"|(?<![\w.,:/$%+-])(\d{1,9})(?:[.,](\d{2}))?\s?([$€£₽₸¥])(?!\w)"
)
_UZ_DEGREE_RE = re.compile(
    r"(?<![\w.,:/$%])([+\-−])?(\d{1,3})(?:[.,](\d))?\s?°\s?(?:[CFС]\b)?"
)
_UZ_SIGNED_RE = re.compile(r"(?:(?<=^)|(?<=[\s(]))([−-])(\d{1,6})(?![\w:/%.,-])(?![.,]\d)")
_UZ_FRACTION_RE = re.compile(r"(?<![\w./-])(\d{1,2})/(\d{1,3})(?![\w./-])")
_UZ_COMMA_DECIMAL_RE = re.compile(r"(?<![\w.,:/$%-])(\d{1,6}),(\d{1,2})(?![\w:/-])(?![.,]\d)")
_UZ_GLUED_TA_RE = re.compile(r"(?<![\w.,:/$%+-])(\d{1,6}) ?(ta(?:si|sini|sida|sidan|siga|lab|dan|ga|da|ni|gacha)?)(?![\w'])")
_UZ_ROMAN_RE = re.compile(
    r"(?<![\w'-])([IVXLC]{1,8})[- ]((?:asr|bob|qism|bo'lim|sinf|kurs|chorak|ming yillik|"
    r"jild|tom|bosqich|daraja|guruh)(?:[^\W\d_]|')*)"
)
# 7–12 digit amounts are read only in front of a word that counts something;
# anything else that long is an ID, an account or a card number.
_UZ_LONG_AMOUNT_RE = re.compile(
    r"(?<![\w.,:/$%+#№-])([1-9]\d{6,})(?=\s+(?:so'm|sum|dollar|rubl|yevro|tenge|"
    r"kishi|nafar|ta\b|dona|tonna|gektar|kilometr|km\b|metr|litr|kilogramm|kg\b|marta|"
    r"yil|aholi|tomoshabin|foydalanuvchi))"
)
# A bare 7–12 digit run (a price, a population, a year span) reads as a
# cardinal, and so does a longer bare run up to 10**36 ("kvadrillion",
# "septillion", …). Two lengths are identifiers by convention and read the
# way clerks dictate them: 16 digits is a bank card (two digits at a time)
# and 20 digits is a bank account (blocks of four). Raw digits are not an
# option for Uzbek: Navoiy-TTS babbles instead of speaking them, so every
# long run must leave this module as words.
# An identifier named by its keyword ("hisob raqami", "karta", "INN", "MFO",
# "№") reads block by block even when short or spaced: "MFO 00014" must not
# drop its zeros, and "INN 302456789" is not three hundred million.
_UZ_CARD_WORDS = r"karta\w*|kartochka\w*|humo|uzcard|visa|mastercard|maestro"
_UZ_ACCOUNT_WORDS = r"hisob\s+raqam\w*|[hx]/r|inn|stir|mfo|jshshir|pinfl|pasport\w*"
_UZ_ID_KEYWORD_RE = re.compile(
    r"(?i)(?<![\w'])((?:" + _UZ_CARD_WORDS + r"|" + _UZ_ACCOUNT_WORDS + r"|id|kod\w*|"
    r"raqam\w*)(?:\s+raqam\w*)?\s*[:№#-]?\s*|[№#]\s*)"
    r"(\d{2,}(?:[ -]\d{2,})*)(?![\w%:/-])(?![.,]\d)"
)
_UZ_CARD_WORD_RE = re.compile(r"(?i)^(?:" + _UZ_CARD_WORDS + r")")
_UZ_ACCOUNT_WORD_RE = re.compile(r"(?i)^(?:" + _UZ_ACCOUNT_WORDS + r")")
# Space- or hyphen-grouped digits with no keyword: "8600 1234 5678 9012".
_UZ_GROUPED_CODE_RE = re.compile(
    r"(?<![\w.,:/+-])(\d{4}(?:[ -]\d{4}){2,4}(?:[ -]\d{1,4})?)(?![\w%:/-])(?![.,]\d)"
)
_UZ_LONG_NUMBER_RE = re.compile(
    r"(?<![\w.,:/$%+#№-])(\d{7,12})(?![\w:/%.,-])(?![.,]\d)"
)
_UZ_ID_RUN_RE = re.compile(
    r"(?<![\w.,:/$%+#№-])(\d{13,})(?![\w:/%.,-])(?![.,]\d)"
)


def _uzbek_extended_forms(text: str, mod) -> str:
    def phone(m: re.Match) -> str:
        if m.group(2):
            return mod.phone([m.group(i) for i in range(2, 7)], plus=bool(m.group(1)))
        return mod.phone([m.group(i) for i in range(7, 11)], plus=False)

    def date(m: re.Match) -> str:
        if m.group(1):
            return mod.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return mod.date(int(m.group(6)), int(m.group(5)), int(m.group(4)))

    def range_(m: re.Match) -> str:
        a, b, word = int(m.group(1)), int(m.group(2)), m.group(3)
        if a >= b:
            raise ValueError("not an ascending range")
        if word:
            return f"{mod.ordinal(a)} – {mod.ordinal_phrase(b, word)}"
        return f"{mod.cardinal(a)}-{mod.cardinal(b)}"

    def money(m: re.Match) -> str:
        if m.group(1):
            return mod.money(m.group(1), m.group(2), m.group(3))
        return mod.money(m.group(6), m.group(4), m.group(5))

    def degree(m: re.Match) -> str:
        body = mod.cardinal(int(m.group(2)))
        if m.group(3):
            body = mod.decimal(int(m.group(2)), m.group(3))
        if m.group(1):
            body = mod.signed(m.group(1), body)
        return f"{body} {mod.DEGREE_WORD}"

    def roman(m: re.Match) -> str:
        raw = m.group(1)
        if len(raw) == 1 and raw not in "VX":
            raise ValueError("a lone I/L/C is a letter")
        return mod.ordinal_phrase(mod.roman(raw), m.group(2))

    def keep_safe(pattern: re.Pattern, render) -> None:
        nonlocal text
        text = pattern.sub(lambda m: _safe_any(m, render), text)

    def _safe_any(m: re.Match, render) -> str:
        if _glued_to_mark(m):
            return m.group(0)
        try:
            return render(m)
        except Exception:  # noqa: BLE001 — conservative: never mangle
            return m.group(0)

    def keyword_code(m: re.Match) -> str:
        if sum(c.isdigit() for c in m.group(2)) < 5:
            raise ValueError("a short house/room number stays a cardinal")
        head = m.group(1).strip()
        if _UZ_CARD_WORD_RE.match(head):
            return m.group(1) + mod.card(m.group(2))
        if _UZ_ACCOUNT_WORD_RE.match(head):
            return m.group(1) + mod.code(m.group(2))
        return m.group(1) + bare_code(m.group(2))

    def bare_code(raw: str) -> str:
        # Under a generic "raqam"/"ID"/"№" or no keyword at all, sixteen
        # digits is a bank card and anything else an account-style code.
        if sum(c.isdigit() for c in raw) == 16:
            return mod.card(raw)
        return mod.code(raw)

    def long_run(m: re.Match) -> str:
        raw = m.group(1)
        if len(raw) == 16:
            return mod.card(raw)
        if len(raw) == 20 or raw.startswith("0") or int(raw) > mod.MAX_CARDINAL:
            return mod.code(raw)
        return mod.cardinal(int(raw))

    keep_safe(_UZ_PHONE_RE, phone)
    keep_safe(_UZ_DATE_RE, date)
    keep_safe(_TIME_RE, lambda m: mod.clock(int(m.group(1)), int(m.group(2))))
    keep_safe(_UZ_ID_KEYWORD_RE, keyword_code)
    keep_safe(_UZ_GROUPED_CODE_RE, lambda m: bare_code(m.group(1)))
    keep_safe(_UZ_MONEY_RE, money)
    keep_safe(_UZ_DEGREE_RE, degree)
    keep_safe(_UZ_RANGE_RE, range_)
    keep_safe(_UZ_ROMAN_RE, roman)
    keep_safe(_UZ_FRACTION_RE, lambda m: mod.fraction(int(m.group(1)), int(m.group(2))))
    # "3,5" is the official Uzbek decimal; hand it to the decimal rule.
    text = _UZ_COMMA_DECIMAL_RE.sub(lambda m: f"{m.group(1)}.{m.group(2)}", text)
    keep_safe(_UZ_GLUED_TA_RE, lambda m: mod.fused(int(m.group(1)), m.group(2)))
    keep_safe(_UZ_SIGNED_RE, lambda m: mod.signed(m.group(1), mod.cardinal(int(m.group(2)))))
    keep_safe(_UZ_LONG_AMOUNT_RE, lambda m: mod.cardinal(int(m.group(1))))
    keep_safe(_UZ_LONG_NUMBER_RE, lambda m: mod.cardinal(int(m.group(1))))
    keep_safe(_UZ_ID_RUN_RE, long_run)
    return text


# ── Uzbek apostrophes ────────────────────────────────────────────────────────
#
# Uzbek Latin spells o‘/g‘ and the tutuq belgisi (ma’no) with whichever
# apostrophe the keyboard produced: U+02BB (official), U+02BC, curly quotes,
# a backtick or an acute accent. The engine sees each as a different token,
# so the same word reads differently from sentence to sentence. Fold every
# variant between two Latin letters to ASCII ``'`` — quotes around a word
# have a space or punctuation on one side and are left alone.
_UZ_APOSTROPHE_RE = re.compile(
    "(?<=[A-Za-z])[ʻʼʿʾ‘’`´](?=[A-Za-z])"
)


def _fold_uzbek_apostrophes(text: str) -> str:
    return _UZ_APOSTROPHE_RE.sub("'", text)


# ── Public API ───────────────────────────────────────────────────────────────

def _normalize_language(text: str, language: Optional[str]) -> str:
    """The language passes (ranges, abbreviations, numbers) for one language."""
    if language == "uzc":
        return _normalize_uzbek_cyrillic(text)
    out = text
    plain = _plain_lang_code(language)
    if plain:
        # Runs outside the num2words gate below: ko/ja/zh keep their digits
        # (that gate returns None for them) but still need the range mark.
        out = _outside_brackets(out, lambda t: _speak_number_ranges(t, plain))
    lang = _num2words_lang(language)
    if lang:
        if lang in _ABBREV_COMPILED:
            out = _outside_brackets(out, lambda t: _expand_abbreviations(t, lang))
        out = _outside_brackets(out, lambda t: _numbers_to_words(t, lang))
    else:
        native = _native_lang(language)
        if native == "uz":
            out = _outside_brackets(out, _fold_uzbek_apostrophes)
        if native in _ABBREV_COMPILED:
            out = _outside_brackets(out, lambda t: _expand_abbreviations(t, native))
        if native:
            out = _outside_brackets(out, lambda t: _numbers_to_words_native(t, native))
    return out


# ── Mixed-language text ──────────────────────────────────────────────────────
#
# Requests in these languages often quote the others (an Uzbek script with an
# English line, a Russian price). Each number is verbalized in the language of
# its own clause (services/number_language.py), not the request's.
_CONTEXT_REQUEST_LANGS = frozenset({"en", "ru", "uz"})


def _normalize_uzbek_cyrillic(text: str) -> str:
    """A number group written in Cyrillic Uzbek ("2025-йил", "5 та"): read it
    with the Latin Uzbek rules and write the words back in Cyrillic."""
    from services.number_words_uz import to_cyrillic, to_latin

    spoken = _numbers_to_words_native(_fold_uzbek_apostrophes(to_latin(text)), "uz")
    return to_cyrillic(spoken)


def normalize_text(text: str, language: Optional[str] = None) -> str:
    """Pure, idempotent normalization pass (no pref gate — see
    :func:`normalize_for_tts` for the gated entry point pipelines call)."""
    if not text:
        return text or ""
    out = _safety_filters(text)
    plain = _plain_lang_code(language)
    if plain not in _CONTEXT_REQUEST_LANGS:
        return _normalize_language(out, language)
    from services.number_language import split_by_number_language

    parts = split_by_number_language(out, plain)
    if len(parts) == 1:
        return _normalize_language(out, language)
    return "".join(
        _normalize_language(piece, language if lang == plain else lang)
        for piece, lang in parts
    )


def normalization_enabled() -> bool:
    """Default ON; the env var is the power-user off switch. (A prefs key was
    once read here too, but nothing ever wrote it.)"""
    env = os.environ.get(ENV_VAR)
    if env is None:
        return True
    return env.strip().lower() not in ("0", "false", "no", "off", "")


def normalize_for_tts(text: str, language: Optional[str] = None) -> str:
    """Gated + hardened entry point: pref/env toggle, never raises.

    Every TTS pipeline calls this exactly once, at its text→engine choke
    point, BEFORE the pronunciation dictionary (see module docstring).
    """
    if not text:
        return text or ""
    if not normalization_enabled():
        return text
    try:
        return normalize_text(text, language)
    except Exception:  # noqa: BLE001 — normalization must never break synth
        logger.warning("text normalization failed; using raw text", exc_info=True)
        return text
