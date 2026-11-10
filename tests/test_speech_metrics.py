"""services/speech_metrics.py on synthetic material whose answers are known:
pauses where pauses were put, a melody of the width that was synthesized, a
loudness range that shrinks when the signal is compressed."""
from __future__ import annotations

import numpy as np
import pytest

from services import speech_metrics as sm

SR = 24_000


def voiced(seconds: float, f0_from: float, f0_to: float, *, amp: float = 0.3, sr: int = SR) -> np.ndarray:
    """A harmonic complex whose F0 glides linearly — a sung vowel, roughly,
    with 10 ms ramps so its edges do not read as pause."""
    n = int(seconds * sr)
    f0 = np.linspace(f0_from, f0_to, n)
    phase = 2 * np.pi * np.cumsum(f0) / sr
    out = np.zeros(n)
    for h in range(1, 8):
        out += np.sin(h * phase) / h
    ramp = int(0.01 * sr)
    env = np.ones(n)
    env[:ramp] = np.linspace(0, 1, ramp)
    env[-ramp:] = np.linspace(1, 0, ramp)
    return (out * env / np.max(np.abs(out)) * amp).astype(np.float32)


def passage(gap_s: float, *, floor: float = 1e-4) -> np.ndarray:
    rng = np.random.default_rng(7)
    gap = rng.standard_normal(int(gap_s * SR)).astype(np.float32) * floor
    edge = rng.standard_normal(int(0.3 * SR)).astype(np.float32) * floor
    tones = [voiced(1.5, 180, 220) for _ in range(3)]
    return np.concatenate([edge, tones[0], gap, tones[1], gap, tones[2], edge])


def test_counts_the_pauses_that_were_synthesized():
    m = sm.analyze_speech(passage(0.4), SR)
    assert m.pauses == 2
    assert m.pause_mean_s == pytest.approx(0.4, abs=0.06)
    assert m.pause_floor_dbfs < -70  # the gap floor, not speech
    assert 4.3 < m.speech_s < 4.8


def test_short_articulation_gaps_are_not_pauses():
    assert sm.analyze_speech(passage(0.08), SR).pauses == 0


def test_f0_statistics_follow_the_synthesized_glide():
    m = sm.analyze_speech(passage(0.4), SR)
    assert 185 < m.f0_median_hz < 215
    # 180→220 Hz is 3.5 semitones; the 5–95 % range sits just inside that.
    assert 2.5 < m.f0_range_st < 3.6
    assert m.f0_std_st < 1.5
    assert m.voiced_ratio > 0.8


def test_dynamics_metrics_shrink_when_the_signal_is_compressed():
    x = passage(0.4)
    natural = sm.analyze_speech(x, SR)
    squashed = np.sign(x) * np.abs(x) ** 0.5 * 0.3  # a crude 2:1 compressor
    compressed = sm.analyze_speech(squashed.astype(np.float32), SR)
    assert compressed.crest_db < natural.crest_db
    assert compressed.level_std_db < natural.level_std_db


def test_spectral_tilt_tracks_high_frequency_content():
    dark = sm.analyze_speech(passage(0.4), SR)
    rng = np.random.default_rng(1)
    bright = passage(0.4) + rng.standard_normal(len(passage(0.4))).astype(np.float32) * 0.02
    bright_m = sm.analyze_speech(bright, SR)
    assert bright_m.tilt_db > dark.tilt_db
    assert bright_m.rolloff95_hz > dark.rolloff95_hz


def test_silence_yields_an_empty_but_valid_report():
    m = sm.analyze_speech(np.zeros(SR, dtype=np.float32), SR)
    assert m.speech_s == 0.0 and m.pauses == 0 and m.lufs is None
    assert m.to_dict()["f0_median_hz"] is None


def test_runs_and_summary_columns_exist():
    assert sm.runs(np.array([0, 1, 1, 0, 1], dtype=bool)) == [(1, 3), (4, 5)]
    assert "lra_lu" in sm.SUMMARY_COLUMNS and "tilt_db" in sm.SUMMARY_COLUMNS


def test_voice_texture_separates_smooth_from_noisy_phonation():
    clean = passage(0.4)
    rng = np.random.default_rng(5)
    noisy = (clean + rng.standard_normal(len(clean)).astype(np.float32) * 0.03).astype(np.float32)
    a, b = sm.analyze_speech(clean, SR), sm.analyze_speech(noisy, SR)
    assert a.hnr_db is not None and a.cpp_db is not None
    assert a.hnr_db > 15 and b.hnr_db < a.hnr_db - 5
    assert a.cpp_db > b.cpp_db
    assert b.presence_db > a.presence_db  # added broadband noise reads as harshness


def test_h1_h2_follows_the_harmonic_balance():
    n = int(2.0 * SR)
    t = np.arange(n) / SR
    bright = (np.sin(2 * np.pi * 200 * t) + 1.0 * np.sin(2 * np.pi * 400 * t)) * 0.2
    breathy = (np.sin(2 * np.pi * 200 * t) + 0.25 * np.sin(2 * np.pi * 400 * t)) * 0.2
    ramp = np.linspace(0, 1, int(0.02 * SR))
    for sig in (bright, breathy):
        sig[: len(ramp)] *= ramp
        sig[-len(ramp):] *= ramp[::-1]
    quiet = np.zeros(int(0.3 * SR), dtype=np.float32)
    mb = sm.analyze_speech(np.concatenate([quiet, bright.astype(np.float32), quiet]), SR)
    mr = sm.analyze_speech(np.concatenate([quiet, breathy.astype(np.float32), quiet]), SR)
    assert mb.h1_h2_db == pytest.approx(0.0, abs=1.5)
    assert mr.h1_h2_db == pytest.approx(12.0, abs=2.0)
