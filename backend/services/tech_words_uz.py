"""Uzbek reading of technical tokens — file names, paths, addresses, versions.

The number rules in ``text_normalization`` read prices, dates and phone
numbers, but a file name, a folder path, a web or IP address, an e-mail, a
version string or a unit such as ``GB`` reached the engine as written, and the
engine chewed it: ``D:\\sado\\Ovoz.bat``, ``127.0.0.1:3955``, ``v0.5.8``,
``9,5 GB``. This module rewrites each of them the way a person dictates it:

  * ``index.html`` → index nuqta ha te em el; ``voice_casting.py`` → voice
    casting nuqta pay (``_`` and ``-`` are silent, the dot is spoken, an
    extension without a vowel is spelled);
  * ``D:\\papka\\fayl.bat`` → de disk, papka, fayl nuqta bat (each folder is
    its own phrase, so the listener hears where one ends);
  * ``https://sado.uz/yuklab-olish`` → sado nuqta uz slesh yuklab olish (the
    scheme and ``www.`` are dropped);
  * ``127.0.0.1:3955`` → … nuqta bir, port uch ming to'qqiz yuz ellik besh;
  * ``hi@sado.sh`` → hi kuchukcha sado nuqta es ha;
  * ``v0.5.8`` → versiya nol nuqta besh nuqta sakkiz;
  * ``16 kHz``, ``9,5 GB``, ``2,3 MB/s`` → the unit as a word, the number is
    left for the number rules;
  * ``1920x1080`` → … ga ….

Only shapes that cannot be ordinary prose are touched: a dotted name needs a
known extension or domain ending, a dotted number needs three parts (and is
not a date or a thousands-grouped amount), a unit needs a digit before it.
Output contains no digits and none of the matched shapes, so a second pass
changes nothing. Pure Python, no dependencies.
"""

from __future__ import annotations

import re

from services import number_words_uz as _num

DOT, SLASH, AT, PORT, DISK, VERSION = "nuqta", "slesh", "kuchukcha", "port", "disk", "versiya"

_LETTERS = {
    "a": "a", "b": "be", "c": "se", "d": "de", "e": "e", "f": "ef", "g": "ge", "h": "ha", "i": "i",
    "j": "je", "k": "ka", "l": "el", "m": "em", "n": "en", "o": "o", "p": "pe", "q": "qu", "r": "er",
    "s": "es", "t": "te", "u": "u", "v": "ve", "w": "dabl ve", "x": "iks", "y": "ye", "z": "zet",
}
_VOWELS = frozenset("aeiou")
# Names that are read as a word of their own rather than spelled or left as is.
_SPOKEN = {"py": "pay", "json": "jeyson", "exe": "ekze", "jpg": "jipeg", "jpeg": "jipeg", "js": "jey es",
           "yml": "yaml", "sql": "es kyu el", "wav": "vav", "gif": "gif", "ps1": "pe es bir"}
_SYMBOLS = {"?": "savol belgisi", "=": "teng", "&": "va", "#": "panjara", "%": "foiz", "~": "tilda",
            "+": "plyus", "@": AT, ":": "ikki nuqta"}

_FILE_EXTS = (
    "py|pyw|ipynb|js|jsx|ts|tsx|mjs|cjs|json|jsonl|html|htm|css|scss|md|txt|rtf|pdf|doc|docx|xls|xlsx|ppt|pptx|"
    "csv|tsv|xml|yml|yaml|toml|ini|cfg|conf|env|log|lock|bat|cmd|ps1|sh|exe|msi|dll|apk|dmg|deb|iso|zip|rar|"
    "tar|gz|7z|wav|mp3|mp4|m4a|flac|ogg|opus|mov|mkv|avi|webm|png|jpg|jpeg|gif|svg|webp|ico|bmp|psd|fig|"
    "db|sqlite|sql|bin|dat|onnx|pth|ckpt|safetensors|cpp|java|kt|php|rb|swift|vue|srt|vtt|ttf|otf|bak|tmp"
)
_DOMAIN_ENDS = "uz|com|org|net|ru|io|ai|dev|app|me|info|edu|gov|kz|tv|co|uk|de"
_NAME = r"[A-Za-z0-9_][A-Za-z0-9_-]*"
_TAIL_PUNCT = ".,;:!?)»”\"'"

_URL_RE = re.compile(r"(?<![\w@/.])(?:https?://|ftp://|www\.)[^\s<>\"«»]+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9][\w.+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![\w-])")
_WIN_PATH_RE = re.compile(r"(?<![\w\\/])(?:[A-Za-z]:\\|\\\\)?(?:[^\\\s<>\"|?*«»]+\\)+[^\\\s<>\"|?*«»]*"
                          r"|(?<![\w\\/])[A-Za-z]:\\[^\\\s<>\"|?*«»]*")
_IP_RE = re.compile(r"(?<![\w.,:/-])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?::(\d{2,5}))?(?![\w-])(?!\.\d)")
_HOST_PORT_RE = re.compile(r"(?<![\w.@/-])(localhost)(?::(\d{2,5}))?(?![\w-])(?![.:]\w)", re.IGNORECASE)
# "sado.uz/yuklab", "t.me/kanal": a bare domain, with or without a path.
_DOMAIN_RE = re.compile(
    r"(?<![\w@/.\\-])((?:[A-Za-z0-9-]+\.)+(?:" + _DOMAIN_ENDS + r"))(?::(\d{2,5}))?(/[^\s<>\"«»]*)?(?![\w-])"
)
# "/home/user/x.py", "./run.sh", "scripts/voice_casting.py", "a/b/c".
_UNIX_PATH_RE = re.compile(
    r"(?<![\w/.:\\-])(?:~|\.{1,2})?/(?:[\w.-]+/)*[\w.-]*[A-Za-z_][\w.-]*"
    r"|(?<![\w/.:\\-])(?:[\w.-]+/){2,}[\w.-]+"
    r"|(?<![\w/.:\\-])(?:[\w.-]+/)+" + _NAME + r"(?:\." + _NAME + r")*\.(?:" + _FILE_EXTS + r")(?![\w-])"
)
_FILE_RE = re.compile(
    r"(?<![\w@/.\\-])(" + _NAME + r"(?:\." + _NAME + r")*)\.(" + _FILE_EXTS + r")(?![\w-])(?!\.\w)"
)
_VERSION_RE = re.compile(
    r"(?<![\w.,:/-])(?:([vV])\.?(\d{1,4}(?:\.\d{1,4}){1,3})|(\d{1,4}(?:\.\d{1,4}){2,3}))(?![\w-])(?!\.\d)"
)
_RESOLUTION_RE = re.compile(r"(?<![\w.,:/-])(\d{2,5})\s?[x×х]\s?(\d{2,5})(?![\w:/-])(?![.,]\d)")

_UNITS = {
    "TB": "terabayt", "GB": "gigabayt", "MB": "megabayt", "KB": "kilobayt", "kB": "kilobayt",
    "Gb": "gigabayt", "Mb": "megabayt", "Kb": "kilobayt",
    "GB/s": "gigabayt sekundiga", "MB/s": "megabayt sekundiga", "KB/s": "kilobayt sekundiga",
    "Mbit/s": "megabit sekundiga", "Mbps": "megabit sekundiga", "Gbit/s": "gigabit sekundiga",
    "Kbit/s": "kilobit sekundiga", "kbps": "kilobit sekundiga",
    "GHz": "gigagers", "MHz": "megagers", "kHz": "kilogers", "Hz": "gers",
    "ms": "millisekund", "fps": "kadr sekundiga", "px": "piksel", "dB": "detsibel",
    "km/h": "kilometr soatiga", "km/soat": "kilometr soatiga", "m/s": "metr sekundiga",
    "mm": "millimetr", "sm": "santimetr", "ml": "millilitr", "kVt": "kilovatt", "Vt": "vatt",
    "mAh": "milliamper soat", "MP": "megapiksel",
}
_UNIT_RE = re.compile(
    r"(?<=\d)(\s?)(" + "|".join(re.escape(u) for u in sorted(_UNITS, key=len, reverse=True)) + r")(?![\w/'])"
)


def number(raw: str) -> str:
    """A digit run inside a name: a leading zero is read digit by digit."""
    if raw.startswith("0") or int(raw) > _num.MAX_CARDINAL:
        return _num.digits(raw)
    return _num.cardinal(int(raw))


def spell(letters: str) -> str:
    return " ".join(_LETTERS.get(c, c) for c in letters.lower())


def word(raw: str) -> str:
    """One name part (no separators): letters stay a word unless they cannot
    be pronounced (no vowel, four letters or fewer), digits become numbers."""
    if raw.lower() in _SPOKEN:
        return _SPOKEN[raw.lower()]
    out = []
    for run in re.findall(r"\d+|[^\W\d_]+|[^\w\s]", raw):
        if run.isdigit():
            out.append(number(run))
        elif run.lower() in _SPOKEN:
            out.append(_SPOKEN[run.lower()])
        elif run.isascii() and run.isalpha() and len(run) <= 4 and not (_VOWELS & set(run.lower())):
            out.append(spell(run))
        elif run in _SYMBOLS:
            out.append(_SYMBOLS[run])
        elif run.isalpha() or run == "'":
            out.append(run)
    return " ".join(out)


def name(raw: str) -> str:
    """A file or host name: dots are spoken, ``_`` and ``-`` are silent."""
    parts = [" ".join(word(w) for w in re.split(r"[_\-\s]+", part) if w) for part in raw.split(".")]
    return f" {DOT} ".join(p for p in parts if p)


def _join(parts: list[str], sep: str) -> str:
    return sep.join(p for p in parts if p)


def host(raw: str, port: str | None = None) -> str:
    ip = _IP_RE.fullmatch(raw)
    spoken = f" {DOT} ".join(number(g) for g in raw.split(".")) if ip else name(raw)
    return f"{spoken}, {PORT} {number(port)}" if port else spoken


def url(raw: str) -> str:
    """Host, then every path part after a spoken slash; the scheme is dropped."""
    body = re.sub(r"^(?:[a-z]+://)?(?:www\.)?", "", raw, flags=re.IGNORECASE)
    address, _, rest = body.partition("/")
    hostname, _, port = address.partition(":")
    pieces = [host(hostname, port if port.isdigit() else None)]
    for segment in re.split(r"/", rest):
        if segment:
            spoken = " ".join(name(p) if not re.fullmatch(r"[?=&#%~+@:]", p) else _SYMBOLS[p]
                              for p in re.split(r"([?=&#%~+@:])", segment) if p)
            pieces.append(spoken)
    return _join(pieces, f" {SLASH} ")


def email(raw: str) -> str:
    user, _, domain = raw.partition("@")
    return f"{name(user)} {AT} {name(domain)}"


def windows_path(raw: str) -> str:
    """Each folder is its own comma-separated phrase: de disk, papka, fayl."""
    parts = [p for p in raw.split("\\") if p]
    out = []
    for i, part in enumerate(parts):
        if i == 0 and re.fullmatch(r"[A-Za-z]:", part):
            out.append(f"{spell(part[0])} {DISK}")
        else:
            out.append(name(part))
    return _join(out, ", ")


def unix_path(raw: str) -> str:
    return _join([name(p) for p in raw.split("/") if p not in ("", ".", "~")], ", ")


def version(raw: str, prefixed: bool) -> str:
    spoken = f" {DOT} ".join(number(g) for g in raw.split("."))
    return f"{VERSION} {spoken}" if prefixed else spoken


def _looks_like_date_or_amount(raw: str) -> bool:
    groups = raw.split(".")
    if all(len(g) == 3 for g in groups[1:]):
        return True  # "1.500.000": thousands grouped by dots
    if len(groups) != 3 or not (int(groups[0]) <= 31 and 1 <= int(groups[1]) <= 12):
        return False
    if len(groups[2]) == 4:
        return len(groups[0]) <= 2 and len(groups[1]) <= 2  # 5.9.2025
    return [len(g) for g in groups] == [2, 2, 2]  # 05.09.25; "3.11.17" is a version


def _split_tail(raw: str) -> tuple[str, str]:
    """Sentence punctuation glued to the end of an address is not part of it."""
    body = raw.rstrip(_TAIL_PUNCT)
    return body, raw[len(body):]


def speak(text: str) -> str:
    """Rewrite every technical token in ``text``; prose is left untouched."""
    if not text:
        return text

    def with_tail(render):
        def repl(m: re.Match) -> str:
            body, tail = _split_tail(m.group(0))
            try:
                spoken = render(body)
            except Exception:  # noqa: BLE001 — conservative: never mangle
                return m.group(0)
            return (spoken + tail) if spoken else m.group(0)
        return repl

    def ip(m: re.Match) -> str:
        if any(int(g) > 255 for g in m.groups()[:4]):
            return m.group(0)
        return host(".".join(m.groups()[:4]), m.group(5))

    def domain(m: re.Match) -> str:
        path, tail = _split_tail(m.group(3) or "")
        return url(m.group(1) + (f":{m.group(2)}" if m.group(2) else "") + path) + tail

    def ver(m: re.Match) -> str:
        raw = m.group(2) or m.group(3)
        if not m.group(1) and _looks_like_date_or_amount(raw):
            return m.group(0)
        return version(raw, bool(m.group(1)))

    text = _URL_RE.sub(with_tail(url), text)
    text = _EMAIL_RE.sub(with_tail(email), text)
    text = _WIN_PATH_RE.sub(with_tail(windows_path), text)
    text = _IP_RE.sub(ip, text)
    text = _HOST_PORT_RE.sub(lambda m: host(m.group(1), m.group(2)), text)
    text = _DOMAIN_RE.sub(domain, text)
    text = _UNIX_PATH_RE.sub(with_tail(unix_path), text)
    text = _FILE_RE.sub(lambda m: name(m.group(0)), text)
    text = _VERSION_RE.sub(ver, text)
    text = _RESOLUTION_RE.sub(lambda m: f"{number(m.group(1))} ga {number(m.group(2))}", text)
    return _UNIT_RE.sub(lambda m: " " + _UNITS[m.group(2)], text)
