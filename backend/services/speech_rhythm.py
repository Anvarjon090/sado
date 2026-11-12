"""Rhythm of a take against its text: where it pauses and how its pace moves.

Loudness, pitch and CER can all look right on a take that still sounds wrong
for two reasons listeners name first: the voice stops where no punctuation
asked for a stop, and it speeds up as it goes. Both were measured on
2026-11-12 on a 29 s single-shot paragraph — fifteen silences for six
punctuation marks, and a syllable rate 15 % higher in the last third than in
the first — while the same voice on an 8 s line had neither.

Two tools live here, both text-aware and model-free:

* :func:`pause_site_counts` — how many places the *text* gives a reader to
  pause (sentence ends and clause marks that are followed by more text).
  ``audio_dsp.shape_pauses`` lengthens at most that many pauses, so the gaps
  an engine leaves inside a phrase are not stretched into breaks.
* :func:`rhythm` — what the *audio* did: pauses beyond the text's sites,
  overlong pauses, syllable rate and its drift across the take.

Numbers here are proxies of rhythm, not of naturalness; they exist so a
complaint ("it breaks", "it rushes") can be reproduced and a fix compared.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

import numpy as np

from services.speech_metrics import frame_levels, runs, speech_mask, to_mono

#: A silence at least this long is a pause; stop closures and geminates stay
#: under about 100 ms.
PAUSE_MIN_S = 0.12
#: From here a pause is heard as a break when no punctuation stands there.
BREAK_MIN_S = 0.20
#: A sentence-sized stop.
LONG_PAUSE_S = 0.60
#: Syllable nuclei closer than this are one syllable.
_NUCLEUS_MIN_GAP_S = 0.09
#: A nucleus stands at least this far above the dip before it.
_NUCLEUS_PROMINENCE_DB = 2.0
#: Speech shorter than this carries too few syllables for a tempo estimate.
_TEMPO_MIN_SPEECH_S = 3.0

_BRACKET_TAG = re.compile(r"\[[^\]]*\]")
# Marks count only when more text follows after whitespace: "3.5", "14:30" and
# the mark that ends the text give a reader no pause inside it.
_SENTENCE_SITE = re.compile(r"[.!?…]+[\"'”’»)]*(?=\s+\S)")
_CLAUSE_SITE = re.compile(r"[,;:]+(?=\s+\S)|(?<=\s)[—–](?=\s+\S)")


def pause_site_counts(text: str | Iterable[str] | None) -> tuple[int, int]:
    """``(sentence, clause)``: places inside the text where a reader pauses.

    ``text`` is one string or the spans of a request (paragraphs, ``[pause]``
    or SSML spans). The silence *between* spans is stitched in by the caller
    and is not the engine's to place, so each span is counted on its own and
    its final mark never counts. Bracket tags (``[laugh]``, ``[pause 300ms]``)
    are not text.
    """
    if text is None:
        return 0, 0
    spans = [text] if isinstance(text, str) else list(text)
    sentence = clause = 0
    for span in spans:
        core = _BRACKET_TAG.sub(" ", span or "").strip()
        if not core:
            continue
        sentence += len(_SENTENCE_SITE.findall(core))
        clause += len(_CLAUSE_SITE.findall(core))
    return sentence, clause


def inner_silences(samples: np.ndarray, sample_rate: int,
                   min_s: float = PAUSE_MIN_S) -> list[tuple[float, float]]:
    """``(start_s, end_s)`` of every silence of at least ``min_s`` between the
    first and the last speech frame."""
    mono = to_mono(np.asarray(samples, dtype=np.float32))
    levels, hop = frame_levels(mono, sample_rate)
    active = speech_mask(levels)
    idx = np.where(active)[0]
    if idx.size < 2:
        return []
    first, last = int(idx[0]), int(idx[-1])
    out = []
    for a, b in runs(~active[first:last + 1]):
        start, end = (a + first) * hop / sample_rate, (b + first) * hop / sample_rate
        if end - start >= min_s:
            out.append((float(start), float(end)))
    return out


def syllable_times(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Times (s) of syllable nuclei: peaks of the smoothed level contour that
    rise :data:`_NUCLEUS_PROMINENCE_DB` over the dip before them, at least
    :data:`_NUCLEUS_MIN_GAP_S` apart, inside speech."""
    mono = to_mono(np.asarray(samples, dtype=np.float32))
    levels, hop = frame_levels(mono, sample_rate)
    if levels.size < 5:
        return np.zeros(0)
    active = speech_mask(levels)
    smooth = np.convolve(levels, np.ones(5) / 5.0, mode="same")
    min_gap = max(1, round(_NUCLEUS_MIN_GAP_S * sample_rate / hop))
    peaks: list[int] = []
    dip = float(smooth[0])
    for i in range(1, len(smooth) - 1):
        value = float(smooth[i])
        dip = min(dip, value)
        if not active[i] or value < smooth[i - 1] or value <= smooth[i + 1]:
            continue
        if value - dip < _NUCLEUS_PROMINENCE_DB:
            continue
        if peaks and i - peaks[-1] < min_gap:
            if value > smooth[peaks[-1]]:
                peaks[-1] = i
        else:
            peaks.append(i)
        dip = value
    return np.asarray(peaks, dtype=np.float64) * hop / sample_rate


def _part_rates(samples: np.ndarray, sample_rate: int, parts: int) -> list[float] | None:
    """Syllables per second of speech in ``parts`` equal slices of the take's
    speech time (pauses are not time spent speaking)."""
    mono = to_mono(np.asarray(samples, dtype=np.float32))
    levels, hop = frame_levels(mono, sample_rate)
    active = speech_mask(levels)
    hop_s = hop / sample_rate
    speech_s = float(active.sum()) * hop_s
    if speech_s < _TEMPO_MIN_SPEECH_S:
        return None
    nuclei = np.round(syllable_times(mono, sample_rate) / hop_s).astype(int)
    spoken = np.cumsum(active)  # speech frames up to and including each frame
    total = int(spoken[-1])
    counts = [0] * parts
    for frame in nuclei:
        frame = min(max(int(frame), 0), len(spoken) - 1)
        part = min(parts - 1, int((spoken[frame] - 1) * parts / total))
        counts[part] += 1
    slice_s = speech_s / parts
    return [count / slice_s for count in counts]


@dataclass(frozen=True)
class Rhythm:
    """Pauses and pace of one take; see the module docstring."""

    pauses: int                      # inner silences >= PAUSE_MIN_S
    breaks: int                      # of those, >= BREAK_MIN_S
    long_pauses: int                 # of those, >= LONG_PAUSE_S
    sentence_sites: int              # sentence ends inside the text
    clause_sites: int                # clause marks inside the text
    extra_breaks: int                # breaks the text gave no site for
    extra_long_pauses: int           # sentence-sized stops beyond the sentence ends
    syllable_rate: float | None   # nuclei per second of speech
    tempo_drift_pct: float | None   # last third against the first third
    tempo_spread_pct: float | None  # (fastest - slowest) / mean over five slices

    def to_dict(self) -> dict:
        return asdict(self)


def rhythm(samples: np.ndarray, sample_rate: int,
           text: str | Sequence[str] | None = None) -> Rhythm:
    """Measure a take's pauses and pace; ``text`` (or its spans) supplies the
    pause sites the pauses are compared with."""
    silences = inner_silences(samples, sample_rate)
    durations = [end - start for start, end in silences]
    breaks = sum(1 for d in durations if d >= BREAK_MIN_S)
    long_pauses = sum(1 for d in durations if d >= LONG_PAUSE_S)
    sentence, clause = pause_site_counts(text)
    thirds = _part_rates(samples, sample_rate, 3)
    fifths = _part_rates(samples, sample_rate, 5)
    rate = drift = spread = None
    if thirds:
        rate = round(sum(thirds) / 3.0, 2)
        if thirds[0] > 0:
            drift = round((thirds[2] / thirds[0] - 1.0) * 100.0, 1)
    if fifths and sum(fifths) > 0:
        spread = round((max(fifths) - min(fifths)) / (sum(fifths) / 5.0) * 100.0, 1)
    return Rhythm(
        pauses=len(durations), breaks=breaks, long_pauses=long_pauses,
        sentence_sites=sentence, clause_sites=clause,
        extra_breaks=max(0, breaks - sentence - clause),
        extra_long_pauses=max(0, long_pauses - sentence),
        syllable_rate=rate, tempo_drift_pct=drift, tempo_spread_pct=spread,
    )


def rhythm_file(path: str, text: str | Sequence[str] | None = None) -> Rhythm:
    import soundfile as sf

    samples, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    return rhythm(samples, sample_rate, text)
