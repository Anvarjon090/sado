"""Which language a number is spoken in, judged from the words around it.

A request carries one language, but real text mixes them: an Uzbek script
quotes an English sentence or a Russian price list, and every digit in it was
read in Uzbek ("I have 5 apples" → "besh"). The Navoiy engine then turned any
digit left over into Uzbek too. This module decides the language of each
number from its own clause, so the normalizer can verbalize it in the
language the sentence is actually written in.

How a number is judged:

  1. The text is cut into clauses at sentence punctuation and line breaks; a
     number only listens to its own clause.
  2. Every word in the clause votes for the languages it looks like —
     a function-word lexicon hit counts 1.0, a script or spelling cue
     (``ў қ ғ ҳ`` for Cyrillic Uzbek, ``ы щ`` for Russian, ``o'``/``g'`` and a
     bare ``q`` for Latin Uzbek, ``w``/``th``/a ``c`` outside ``ch`` and
     contractions for English) counts less. A word that matches nothing votes
     for nobody, so brand names and loanwords stay neutral.
  3. A vote is weighted by 1/distance (in words) to the number: the
     neighbours decide, the rest of the clause breaks ties.
  4. The suffix glued to the number is the strongest evidence: "5th" is
     English, "5-й" Russian, "5-sinf" Uzbek, "5-та" Cyrillic Uzbek.
  5. The request language gets a small prior, so a clause with no evidence
     (or only neutral words) keeps today's behaviour.

Pure Python, no model download, linear in the input length.
"""

from __future__ import annotations

import re
from collections import defaultdict

#: Languages this module can tell apart. ``uzc`` is Uzbek in Cyrillic script.
CONTEXT_LANGS = ("en", "ru", "uz", "uzc")

_PRIOR = 0.75          # request language, when nothing else speaks
_SUFFIX_WEIGHT = 3.0   # "5th", "5-й", "5-sinf"

_EN_WORDS = frozenset(["a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "by", "for", "with", "from", "as", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "can", "could", "should", "may", "might", "must", "not", "no", "yes", "this", "that", "these", "those", "it", "its", "i", "you", "he", "she", "we", "they", "me", "him", "her", "us", "them", "my", "your", "his", "our", "their", "what", "which", "who", "whom", "when", "where", "why", "how", "all", "any", "some", "more", "most", "many", "much", "about", "after", "before", "than", "then", "there", "here", "only", "just", "also", "over", "under", "up", "down", "out", "new", "old", "first", "last", "next", "get", "got", "make", "made", "see", "said", "say", "says", "per", "percent", "cent", "minutes", "minute", "hours", "hour", "seconds", "second", "dollars", "dollar", "pounds", "euros", "people", "year", "years", "day", "days", "week", "weeks", "month", "months", "time", "times", "price", "costs", "cost", "around", "nearly", "almost", "each", "every", "other", "into", "between", "because", "while", "during", "since", "until", "if", "so", "very", "please", "thank", "thanks", "today", "tomorrow", "yesterday", "morning", "evening", "night", "am", "pm", "o'clock"])

_UZ_WORDS = frozenset(["va", "bu", "u", "men", "sen", "biz", "siz", "ular", "bilan", "uchun", "emas", "edi", "ekan", "bor", "yo'q", "ham", "yoki", "lekin", "ammo", "keyin", "oldin", "hozir", "bugun", "kecha", "ertaga", "yil", "yili", "yilda", "yilning", "oy", "oyi", "kun", "kuni", "soat", "daqiqa", "soniya", "narx", "narxi", "so'm", "sum", "ta", "dona", "kishi", "nafar", "marta", "foiz", "qancha", "necha", "nechta", "juda", "eng", "har", "hamma", "barcha", "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz", "o'n", "yigirma", "o'ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to'qson", "yuz", "ming", "qilib", "qildi", "bo'ldi", "bo'lib", "bo'ladi", "kerak", "mumkin", "shu", "o'sha", "mana", "endi", "faqat", "yana", "ichida", "gacha", "atrofida", "taxminan", "deyarli", "qariyb", "salom", "rahmat", "yaxshi", "katta", "kichik", "yangi", "eski", "sinf", "maktab", "uy", "bola", "odam", "pul", "shahar", "viloyat", "tuman", "respublika", "o'zbekiston", "toshkent", "asr", "bob", "qism", "sahifa", "raqam", "raqami"])

_RU_WORDS = frozenset(["и", "в", "во", "не", "на", "я", "он", "она", "оно", "они", "мы", "вы", "ты", "что", "это", "как", "так", "но", "а", "по", "с", "со", "к", "ко", "о", "об", "от", "до", "из", "за", "для", "при", "без", "над", "под", "про", "через", "же", "ли", "бы", "был", "была", "было", "были", "быть", "есть", "нет", "да", "все", "всё", "год", "года", "лет", "году", "рублей", "рубля", "рубль", "тысяч", "тысячи", "тысяча", "миллион", "миллиона", "миллионов", "процентов", "процента", "процент", "человек", "раз", "уже", "еще", "ещё", "очень", "только", "когда", "где", "если", "тоже", "этот", "эта", "эти", "тот", "те", "свой", "его", "ее", "её", "их", "мой", "твой", "наш", "ваш", "который", "которая", "которые", "сегодня", "вчера", "завтра", "около", "примерно", "более", "менее", "всего", "часов", "часа", "минут", "секунд", "день", "дня", "дней", "неделю", "месяц", "месяца", "цена", "стоит", "стоимость", "больше", "меньше"])

_RU_ORDINAL_ENDINGS = frozenset(
    ["й", "ый", "ий", "ой", "я", "ая", "яя", "е", "ое", "ее", "го", "ого", "его", "му", "ому", "ему", "м", "ым", "им", "х", "ых", "их", "ми"]
)


def _to_cyrillic(word: str) -> str:
    from services.number_words_uz import to_cyrillic

    return to_cyrillic(word)


_UZC_WORDS = frozenset(_to_cyrillic(w) for w in _UZ_WORDS) | frozenset(
    ["ва", "бу", "у", "мен", "сен", "биз", "сиз", "улар", "билан", "учун", "эмас", "эди", "экан", "бор", "йўқ", "ҳам", "ёки", "лекин"]
)

_WORD_RE = re.compile(r"[^\W\d_](?:[\w'ʻʼ‘’`-]*[^\W\d_])?")
_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_EN_CONTRACTION_RE = re.compile(r"(?:n't|'s|'m|'re|'ve|'ll|'d)$")
_UZ_SUFFIX_RE = re.compile(
    r"..(?:lar|larni|larda|lardan|larga|ning|dagi|imiz|ingiz|gan|moqda|yapti|"
    r"yapman|moqchi|ib|di|dim|dik|ga|da|dan|ni)$"
)
_RU_SUFFIX_RE = re.compile(r"..(?:ого|ему|ому|ая|ые|ый|ть|ться|ешь|ишь)$")


def word_votes(word: str) -> dict[str, float]:
    """How much ``word`` looks like each context language (empty = neutral)."""
    w = word.lower().replace("ʻ", "'").replace("ʼ", "'").replace("‘", "'").replace("’", "'")
    votes: dict[str, float] = {}
    if _CYRILLIC_RE.search(w):
        if re.search("[ўқғҳ]", w):
            votes["uzc"] = 1.0
        elif re.search("[ыщ]", w):
            votes["ru"] = 1.0
        if w in _UZC_WORDS:
            votes["uzc"] = max(votes.get("uzc", 0), 1.0)
        if w in _RU_WORDS:
            votes["ru"] = max(votes.get("ru", 0), 1.0)
        if not votes:
            if _RU_SUFFIX_RE.search(w):
                votes["ru"] = 0.5
            else:
                # Unmarked Cyrillic leans Russian: Uzbek Cyrillic prose is full
                # of ў/қ/ғ/ҳ, so a clause without any of them rarely is Uzbek.
                votes["ru"], votes["uzc"] = 0.3, 0.15
        return votes
    if not _LATIN_RE.search(w):
        return votes
    if w in _EN_WORDS or _EN_CONTRACTION_RE.search(w):
        votes["en"] = 1.0
    if w in _UZ_WORDS:
        votes["uz"] = 1.0
    if votes:
        return votes
    if re.search(r"[og]'[a-z]|[a-z]'[a-z]", w):
        votes["uz"] = 0.9
    elif re.search(r"q(?!u)", w):
        votes["uz"] = 0.8
    elif _UZ_SUFFIX_RE.search(w):
        votes["uz"] = 0.4
    if "w" in w or "th" in w or re.search(r"c(?!h)", w):
        votes["en"] = votes.get("en", 0) + 0.6
    return votes


def _suffix_vote(token: str) -> str | None:
    """Language named by the letters glued to a number token, if any."""
    letters = "".join(ch for ch in token if ch.isalpha())
    if not letters:
        return None
    lower = letters.lower()
    if _CYRILLIC_RE.search(lower):
        return "ru" if lower in _RU_ORDINAL_ENDINGS else "uzc"
    if lower in ("st", "nd", "rd", "th"):
        return "en"
    if re.search(r"\d-[^\W\d_]", token) or lower.startswith("ta"):
        return "uz"
    return None


# A clause ends at sentence punctuation followed by a space (so "3.5" and
# "09.11.2026" stay whole) or at a line break.
_CLAUSE_END_RE = re.compile(r"[.!?…;]+(?=\s|$)|\n")
_TOKEN_RE = re.compile(r"\S+")
# Tokens that belong to the number before them: units, signs, "5 ta".
_ATTACHED_RE = re.compile(r"^(?:[%°$€£₽₸¥°]+[CFС]?|ta(?:si|dan|ga|ni)?|та(?:си|дан|га|ни)?)[.,;:!?)]*$")


def _clause_segments(clause: str, offset: int, default: str) -> list[tuple[int, int, str]]:
    """(start, end, lang) for every number group in ``clause`` whose language
    differs from ``default``."""
    tokens = [(m.start(), m.end(), m.group(0)) for m in _TOKEN_RE.finditer(clause)]
    numeric = [any(ch.isdigit() for ch in tok) for _, _, tok in tokens]
    groups: list[tuple[int, int]] = []  # token index ranges [i, j]
    i = 0
    while i < len(tokens):
        if not numeric[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(tokens) and (
            numeric[j + 1] or _ATTACHED_RE.match(tokens[j + 1][2])
        ):
            j += 1
        groups.append((i, j))
        i = j + 1
    if not groups:
        return []
    word_votes_cache = [None if numeric[k] else word_votes(tokens[k][2]) for k in range(len(tokens))]
    out = []
    for gi, gj in groups:
        scores: dict[str, float] = defaultdict(float)
        scores[default] += _PRIOR
        for k in range(gi, gj + 1):
            lang = _suffix_vote(tokens[k][2])
            if lang:
                scores[lang] += _SUFFIX_WEIGHT
        for k, votes in enumerate(word_votes_cache):
            if not votes or gi <= k <= gj:
                continue
            distance = gi - k if k < gi else k - gj
            for lang, v in votes.items():
                scores[lang] += v / distance
        best = max(scores, key=scores.__getitem__)
        if best != default and scores[best] > scores[default]:
            out.append((offset + tokens[gi][0], offset + tokens[gj][1], best))
    return out


def split_by_number_language(text: str, default: str) -> list[tuple[str, str]]:
    """Cut ``text`` into consecutive (piece, lang) parts.

    Pieces holding a number written in another language than ``default`` get
    that language; everything else keeps ``default``. Joining the pieces gives
    back ``text`` exactly.
    """
    spans: list[tuple[int, int, str]] = []
    start = 0
    for m in _CLAUSE_END_RE.finditer(text):
        spans.extend(_clause_segments(text[start:m.end()], start, default))
        start = m.end()
    if start < len(text):
        spans.extend(_clause_segments(text[start:], start, default))
    if not spans:
        return [(text, default)]
    parts: list[tuple[str, str]] = []
    last = 0
    for start, end, lang in spans:
        if start > last:
            parts.append((text[last:start], default))
        parts.append((text[start:end], lang))
        last = end
    if last < len(text):
        parts.append((text[last:], default))
    return parts
