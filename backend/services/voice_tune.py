"""Manual voice tuning: pitch, timbre and tempo of a clone's reference clip.

A cloned voice copies its reference's melody, timbre and pace, so tuning the
reference is how a user reshapes the voice for every engine at once: deeper or
lighter, male to female, calmer or brisker. The output is an ordinary clip the
profile editor previews and saves through the existing replace / create paths.

Rubber Band (through pedalboard, already a cross-platform dependency) does the
signal work. Rubber Band either keeps the formants where they are or moves
them with the pitch; it has no separate formant knob. Timbre is therefore a
first pass that moves pitch *and* formants by ``timbre`` semitones, and a
second, formant-preserving pass that brings the pitch to its own target and
applies the tempo. Pitch and timbre stay independent controls: ``timbre=3,
pitch=0`` changes the vocal tract and leaves the melody where it was.
"""

from __future__ import annotations

import numpy as np

PITCH_RANGE = (-12.0, 12.0)
TIMBRE_RANGE = (-6.0, 6.0)
TEMPO_RANGE = (0.75, 1.25)
_PEAK_CEILING = 0.99


def is_neutral(pitch: float, timbre: float, tempo: float) -> bool:
    return pitch == 0 and timbre == 0 and tempo == 1


def tune_audio(
    samples: np.ndarray,
    sample_rate: int,
    *,
    pitch: float = 0.0,
    timbre: float = 0.0,
    tempo: float = 1.0,
) -> np.ndarray:
    """Return ``samples`` (channels × frames, float32) with the voice retuned.

    ``pitch`` and ``timbre`` are semitones, ``tempo`` a speed factor (1.25 is
    25 % faster). Values outside the public ranges raise ``ValueError``; the
    API validates them first, this guards direct callers.
    """
    for name, value, (low, high) in (
        ("pitch", pitch, PITCH_RANGE),
        ("timbre", timbre, TIMBRE_RANGE),
        ("tempo", tempo, TEMPO_RANGE),
    ):
        if not (low <= value <= high):
            raise ValueError(f"{name}={value} is outside {low}..{high}")
    audio = np.ascontiguousarray(samples, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[np.newaxis, :]
    if is_neutral(pitch, timbre, tempo) or audio.shape[-1] == 0:
        return audio

    from pedalboard import time_stretch

    if timbre:
        audio = time_stretch(
            audio, float(sample_rate),
            pitch_shift_in_semitones=float(timbre), preserve_formants=False,
        )
    remaining_pitch = pitch - timbre
    if remaining_pitch or tempo != 1:
        audio = time_stretch(
            audio, float(sample_rate),
            stretch_factor=float(tempo),
            pitch_shift_in_semitones=float(remaining_pitch),
            preserve_formants=True,
        )
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > _PEAK_CEILING:
        audio = audio * (_PEAK_CEILING / peak)
    return np.ascontiguousarray(audio, dtype=np.float32)
