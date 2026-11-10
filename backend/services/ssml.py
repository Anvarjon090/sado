"""SSML for Sado — a documented subset, mapped onto what the engine can do.

A request whose text is an SSML document (``<speak>…</speak>``) is parsed
into ordered *spans* — text, the pause after it and how it is delivered —
and rendered through the same span stitcher that serves ``[pause]`` markers
and paragraph breaks. Whatever the engine cannot honour is reported in
``warnings`` (and the ``X-SSML-Warnings`` response header), never dropped
silently: a caller learns that ``<prosody pitch>`` did nothing.

Element → effect:

* ``<speak>`` — the root; the SSML namespace is accepted and ignored.
* ``<p>`` — a 650 ms breath after the paragraph (``chunked_tts.PARAGRAPH_PAUSE_MS``).
* ``<s>`` — a sentence; terminal punctuation is added when missing so the
  engine phrases it as one.
* ``<break time="500ms" | strength="strong"/>`` — silence after the text
  before it (``none``/``x-weak``/``weak``/``medium``/``strong``/``x-strong`` =
  0/100/200/350/650/1000 ms; no attribute = medium).
* ``<prosody rate volume>`` — per-span speed (``x-slow``…``x-fast``, ``80%``,
  ``1.2``, ``+10%``) and gain (``x-soft``…``x-loud``, ``+3dB``, ``50%``).
  ``pitch``, ``range`` and ``contour`` are not controllable on a cloned voice
  and produce a warning.
* ``<emphasis level>`` — a touch slower (−8 %) and louder (+1.5 dB); ``none``
  leaves the text alone. The engine has no emphasis input of its own.
* ``<say-as interpret-as>`` — ``characters``/``spell-out`` spell the text
  letter by letter; the other kinds (date, cardinal, telephone, …) are left to
  the text normalizer, which already reads them in the span's language.
* ``<sub alias>`` — the alias is spoken.
* ``<lang xml:lang>`` — the span's language, for the engine and the number
  reader (``ru``, ``en-US`` → ``en``).
* ``<voice name>`` — a saved voice's id or name; the route resolves it.
* ``<phoneme>``, ``<audio>``, ``<mark>`` — not supported: the text inside
  ``<phoneme>`` and ``<audio>`` is spoken plainly, ``<mark>`` is ignored, and
  each kind warns once.

Security: documents with a ``DOCTYPE`` or entity declaration are refused
before parsing (no entity expansion, no external references).
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field, replace

from omnivoice.utils.text import PAUSE_MAX_MS
from services.chunked_tts import PARAGRAPH_PAUSE_MS

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
BREAK_STRENGTH_MS = {"none": 0, "x-weak": 100, "weak": 200, "medium": 350, "strong": 650, "x-strong": 1000}
RATE_WORDS = {"x-slow": 0.6, "slow": 0.8, "medium": 1.0, "default": 1.0, "fast": 1.25, "x-fast": 1.5}
VOLUME_WORDS_DB = {"silent": -40.0, "x-soft": -12.0, "soft": -6.0, "medium": 0.0, "default": 0.0,
                   "loud": 6.0, "x-loud": 9.0}
SPEED_RANGE = (0.5, 2.0)
GAIN_RANGE = (-40.0, 12.0)
EMPHASIS_SPEED = 0.92
EMPHASIS_GAIN_DB = 1.5

# A document may open with an XML declaration or a DOCTYPE before <speak>;
# parse_ssml then refuses the DOCTYPE, so such input is a 400, not plain text.
_SPEAK_RE = re.compile(r"^\s*(?:<\?xml[^>]*\?>\s*)?(?:<!DOCTYPE[^>]*>\s*)?<speak[\s>]", re.IGNORECASE)
_DECLARATION_RE = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_TIME_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*(ms|s)\s*$", re.IGNORECASE)
_PERCENT_RE = re.compile(r"^\s*([+-]?)(\d+(?:\.\d+)?)\s*%\s*$")
_NUMBER_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*$")
_DB_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*dB\s*$", re.IGNORECASE)
_SENTENCE_END = ".!?…。！？"


class SsmlError(ValueError):
    """The document is not SSML Sado can speak; the message says why."""


@dataclass(frozen=True)
class Delivery:
    speed: float = 1.0
    gain_db: float = 0.0
    language: str | None = None
    voice: str | None = None


@dataclass
class Span:
    text: str
    pause_ms: int = 0
    delivery: Delivery = field(default_factory=Delivery)

    def to_wire(self) -> dict:
        wire = asdict(self.delivery)
        wire["speed_factor"] = wire.pop("speed")  # relative to the request's speed
        return {"text": self.text, "pause_ms": self.pause_ms, **wire}


@dataclass
class SsmlDocument:
    spans: list[Span]
    warnings: list[str]

    def plain_text(self) -> str:
        return " ".join(s.text for s in self.spans if s.text).strip()

    def voices(self) -> list[str]:
        seen: list[str] = []
        for s in self.spans:
            if s.delivery.voice and s.delivery.voice not in seen:
                seen.append(s.delivery.voice)
        return seen


def is_ssml(text: str | None) -> bool:
    return bool(text) and _SPEAK_RE.match(text) is not None


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return max(bounds[0], min(bounds[1], value))


def parse_break_ms(time: str | None, strength: str | None) -> int:
    if time:
        m = _TIME_RE.match(time)
        if m:
            ms = float(m.group(1)) * (1000.0 if m.group(2).lower() == "s" else 1.0)
            return int(max(0, min(round(ms), PAUSE_MAX_MS)))
    if strength and strength.strip().lower() in BREAK_STRENGTH_MS:
        return BREAK_STRENGTH_MS[strength.strip().lower()]
    return BREAK_STRENGTH_MS["medium"]


def parse_rate(value: str | None, current: float) -> float | None:
    """A new speed from a ``rate`` attribute, or None when it cannot be read."""
    if value is None:
        return None
    v = value.strip().lower()
    if v in RATE_WORDS:
        return _clamp(RATE_WORDS[v], SPEED_RANGE)
    m = _PERCENT_RE.match(v)
    if m:
        pct = float(m.group(2))
        if m.group(1):  # relative: "+10%" / "-20%"
            factor = 1.0 + (pct if m.group(1) == "+" else -pct) / 100.0
            return _clamp(current * factor, SPEED_RANGE)
        return _clamp(pct / 100.0, SPEED_RANGE)
    m = _NUMBER_RE.match(v)
    if m:
        return _clamp(float(m.group(1)), SPEED_RANGE)
    return None


def parse_volume_db(value: str | None, current: float) -> float | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v in VOLUME_WORDS_DB:
        return _clamp(VOLUME_WORDS_DB[v], GAIN_RANGE)
    m = _DB_RE.match(v)
    if m:
        delta = float(m.group(1))
        return _clamp(current + delta if v[0] in "+-" else delta, GAIN_RANGE)
    m = _PERCENT_RE.match(v)
    if m:
        pct = float(m.group(2))
        if m.group(1):
            pct = 100.0 + (pct if m.group(1) == "+" else -pct)
        return _clamp(20.0 * math.log10(max(pct, 0.1) / 100.0), GAIN_RANGE)
    m = _NUMBER_RE.match(v)
    if m:
        return _clamp(float(m.group(1)), GAIN_RANGE)
    return None


def language_code(xml_lang: str | None) -> str | None:
    if not xml_lang or not xml_lang.strip():
        return None
    return xml_lang.strip().split("-")[0].split("_")[0].lower()


class _Builder:
    def __init__(self) -> None:
        self.events: list[tuple[str, object, Delivery | None]] = []
        self.warnings: list[str] = []

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def text(self, raw: str | None, delivery: Delivery) -> None:
        if raw is None:
            return
        piece = _WS_RE.sub(" ", raw)
        if piece.strip():
            self.events.append(("text", piece.strip(), delivery))

    def pause(self, ms: int) -> None:
        if ms > 0:
            self.events.append(("pause", ms, None))

    def children(self, el, delivery: Delivery) -> None:
        self.text(el.text, delivery)
        for child in el:
            self.handle(child, delivery)
            self.text(child.tail, delivery)

    def handle(self, el, delivery: Delivery) -> None:  # noqa: C901 — one branch per element
        tag = _local(el.tag)
        if tag == "break":
            self.pause(parse_break_ms(el.get("time"), el.get("strength")))
        elif tag == "p":
            self.children(el, delivery)
            self.pause(PARAGRAPH_PAUSE_MS)
        elif tag == "s":
            start = len(self.events)
            self.children(el, delivery)
            for i in range(len(self.events) - 1, start - 1, -1):
                kind, value, d = self.events[i]
                if kind == "text":
                    if value and value[-1] not in _SENTENCE_END:
                        self.events[i] = (kind, value + ".", d)
                    break
        elif tag == "prosody":
            new = delivery
            rate = parse_rate(el.get("rate"), delivery.speed)
            if el.get("rate") is not None and rate is None:
                self.warn(f"prosody rate {el.get('rate')!r} was not understood; the current speed was kept")
            elif rate is not None:
                new = replace(new, speed=rate)
            volume = parse_volume_db(el.get("volume"), delivery.gain_db)
            if el.get("volume") is not None and volume is None:
                self.warn(f"prosody volume {el.get('volume')!r} was not understood; the current level was kept")
            elif volume is not None:
                new = replace(new, gain_db=volume)
            for attr in ("pitch", "range", "contour"):
                if el.get(attr) is not None:
                    self.warn(f"prosody {attr} is not controllable on this engine; the voice's own pitch was kept")
            self.children(el, new)
        elif tag == "emphasis":
            level = (el.get("level") or "moderate").strip().lower()
            if level == "none":
                self.children(el, delivery)
            else:
                self.children(el, replace(
                    delivery,
                    speed=_clamp(delivery.speed * EMPHASIS_SPEED, SPEED_RANGE),
                    gain_db=_clamp(delivery.gain_db + EMPHASIS_GAIN_DB, GAIN_RANGE),
                ))
        elif tag == "say-as":
            kind = (el.get("interpret-as") or "").strip().lower()
            if kind in ("characters", "spell-out"):
                letters = " ".join(ch for ch in "".join(el.itertext()) if not ch.isspace())
                self.text(letters, delivery)
            else:
                self.children(el, delivery)
        elif tag == "sub":
            alias = el.get("alias")
            if alias and alias.strip():
                self.text(alias, delivery)
            else:
                self.children(el, delivery)
        elif tag == "lang":
            code = language_code(el.get(XML_LANG) or el.get("xml:lang") or el.get("lang"))
            self.children(el, replace(delivery, language=code) if code else delivery)
        elif tag == "voice":
            name = (el.get("name") or "").strip()
            if not name:
                self.warn("<voice> without a name was ignored")
                self.children(el, delivery)
            else:
                self.children(el, replace(delivery, voice=name))
        elif tag == "phoneme":
            self.warn("<phoneme> is not supported: the engine takes no phonetic input, so the text was spoken plainly")
            self.children(el, delivery)
        elif tag == "audio":
            self.warn("<audio> is not supported: the clip was skipped and the fallback text spoken")
            self.children(el, delivery)
        elif tag == "mark":
            self.warn("<mark> is ignored: no timing marks are returned")
            self.children(el, delivery)
        elif tag in ("w", "token", "speak"):
            self.children(el, delivery)
        else:
            self.warn(f"<{tag}> is not supported; its text was spoken plainly")
            self.children(el, delivery)

    def finish(self) -> SsmlDocument:
        spans: list[Span] = []
        for kind, value, delivery in self.events:
            if kind == "text":
                assert delivery is not None
                if spans and spans[-1].pause_ms == 0 and spans[-1].text and spans[-1].delivery == delivery:
                    spans[-1].text = f"{spans[-1].text} {value}"
                elif spans and not spans[-1].text and spans[-1].pause_ms == 0:
                    spans[-1] = Span(str(value), 0, delivery)
                else:
                    spans.append(Span(str(value), 0, delivery))
            else:
                ms = int(value)
                if spans:
                    spans[-1].pause_ms = min(spans[-1].pause_ms + ms, PAUSE_MAX_MS)
                else:
                    spans.append(Span("", ms, Delivery()))
        spans = [s for s in spans if s.text or s.pause_ms]
        if not any(s.text for s in spans):
            raise SsmlError("The SSML document has no text to speak.")
        return SsmlDocument(spans, self.warnings)


def parse_ssml(text: str) -> SsmlDocument:
    """Parse an SSML document into spans; raises :class:`SsmlError` with a
    message fit for a 400 when it cannot be spoken."""
    if _DECLARATION_RE.search(text):
        raise SsmlError("SSML with a DOCTYPE or entity declaration is not accepted.")
    try:
        root = ET.fromstring(text.strip())
    except ET.ParseError as exc:
        raise SsmlError(f"The SSML could not be parsed: {exc}") from None
    if _local(root.tag) != "speak":
        raise SsmlError("An SSML document must have <speak> as its root element.")
    builder = _Builder()
    builder.children(root, Delivery())
    return builder.finish()
