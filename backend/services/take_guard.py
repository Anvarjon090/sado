"""Keep a cloned voice itself from one take to the next.

OmniVoice is stochastic: the same reference and text can come back half an
octave away — a woman's reference rendered in a man's range, or a short line
collapsing into an unvoiced buzz. Measured on 2026-11-10 with a designed
female voice cloned from its own 7 s sample, two of seven benchmark lines
flipped like that (F0 111 and 155 Hz against the voice's 250 Hz).

A studio takes another take. This module does the same, deterministically:
``TakeGuard`` knows the reference's median pitch and judges each rendered
chunk — more than :data:`MAX_DEVIATION_ST` semitones off, or no harmonic
structure at all, means "re-render with the retake seed", and the better of
the two takes is kept. One retake at most; the request never fails because
of the guard, and a reference whose pitch cannot be measured disables it.
"""
from __future__ import annotations

import logging
import math
import os
from functools import lru_cache

import numpy as np

logger = logging.getLogger("omnivoice.take_guard")

#: A take whose median pitch sits further than this from the reference's is
#: another voice. Sentence-to-sentence variation of one speaker stays within
#: about ±3 st; a sex flip is 8–10 st.
MAX_DEVIATION_ST = 6.0
#: Below this harmonics-to-noise ratio the take is a buzz, not a voice.
MIN_HNR_DB = 2.0
#: Added to the chunk's seed for the retake, so it is deterministic yet distinct.
RETAKE_SEED_OFFSET = 7919
#: Takes shorter than this carry too little voiced speech to judge.
MIN_SPEECH_S = 0.4


def reference_pitch_hz(path: str | None) -> float | None:
    """Median F0 of a reference clip, cached per file identity; ``None`` when
    it cannot be read or holds too little voiced speech to measure."""
    if not path:
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return _reference_pitch_cached(os.fspath(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=64)
def _reference_pitch_cached(path: str, _mtime_ns: int, _size: int) -> float | None:
    try:
        from services.speech_metrics import analyze_file

        metrics = analyze_file(path)
        if metrics.speech_s < MIN_SPEECH_S or metrics.voiced_ratio < 0.2:
            return None
        return metrics.f0_median_hz
    except Exception:  # noqa: BLE001 — a measurement must never break synthesis
        logger.debug("reference pitch measurement failed", exc_info=True)
        return None


def take_deviation(audio, sample_rate: int, reference_hz: float) -> tuple[float | None, float | None]:
    """``(semitones off the reference, HNR dB)`` of a rendered take; the first
    is ``None`` when the take has no measurable voiced speech."""
    from services.speech_metrics import analyze_speech

    arr = audio.detach().cpu().float().numpy() if hasattr(audio, "detach") else np.asarray(audio, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.mean(axis=0) if arr.shape[0] < arr.shape[-1] else arr.mean(axis=-1)
    metrics = analyze_speech(arr, sample_rate)
    if metrics.speech_s < MIN_SPEECH_S or metrics.f0_median_hz is None:
        return None, metrics.hnr_db
    return abs(12.0 * math.log2(metrics.f0_median_hz / reference_hz)), metrics.hnr_db


class TakeGuard:
    """Judge rendered chunks against a reference pitch; see module docstring."""

    def __init__(self, reference_hz: float, sample_rate: int):
        self.reference_hz = float(reference_hz)
        self.sample_rate = int(sample_rate)
        self.retakes = 0

    def score(self, audio) -> float:
        """Lower is better: semitones off the reference, plus a penalty for a
        missing or buzzing voice."""
        deviation, hnr = take_deviation(audio, self.sample_rate, self.reference_hz)
        if deviation is None:
            return 24.0
        if hnr is not None and hnr < MIN_HNR_DB:
            return deviation + 12.0
        return deviation

    def accepts(self, audio) -> bool:
        return self.score(audio) <= MAX_DEVIATION_ST

    def render(self, render_chunk, chunk_text: str, index: int, duration):
        """``render_chunk(text, index, duration)`` once; a second time with the
        retake seed when the first take is another voice, keeping the better."""
        first = render_chunk(chunk_text, index, duration)
        first_score = self.score(first)
        if first_score <= MAX_DEVIATION_ST:
            return first
        self.retakes += 1
        logger.info(
            "take guard: chunk %d sits %.1f st / flagged off its reference — rendering a retake",
            index, first_score,
        )
        second = render_chunk(chunk_text, index + RETAKE_SEED_OFFSET, duration)
        return second if self.score(second) < first_score else first
