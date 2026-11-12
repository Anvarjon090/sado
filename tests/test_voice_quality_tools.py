"""The voice benchmark's STT clip and the human-likeness scorecard helpers.

The benchmark's CER lied on short takes: the Uzbek Whisper STT invented words
("salom. qalaysiz?" became three repetitions plus "uyoq") on the room-tone tail
of a 2 s take, and trimming 20 ms made it transcribe cleanly (2026-11-12). The
clip handed to the STT is therefore trimmed to speech and padded with digital
silence, and the scorecard's own helpers are pinned here.
"""
from __future__ import annotations

import importlib.util
import io
import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
SR = 24_000


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _voiced(seconds: float, f0: float) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = sum(np.sin(2 * np.pi * f0 * h * t) / h for h in range(1, 7))
    ramp = np.linspace(0, 1, int(0.02 * SR))
    env = np.ones(n)
    env[: len(ramp)] = ramp
    env[-len(ramp):] = ramp[::-1]
    return (out * env / np.max(np.abs(out)) * 0.3).astype(np.float32)


def _room_tone(seconds: float, seed: int = 3) -> np.ndarray:
    return (np.random.default_rng(seed).standard_normal(int(seconds * SR)) * 1e-3).astype(np.float32)


def test_stt_clip_is_trimmed_to_speech_and_padded_with_digital_silence(tmp_path):
    bench = _load("voice_bench")
    take = np.concatenate([_room_tone(0.6), _voiced(1.0, 180.0), _room_tone(0.8, seed=4)])
    path = tmp_path / "take.wav"
    sf.write(path, take, SR, subtype="PCM_16")

    clip, sr = sf.read(io.BytesIO(bench.stt_clip_bytes(path)), dtype="float32")

    assert sr == SR
    expected = 1.0 + 2 * bench.STT_TRIM_MARGIN_S + 2 * bench.STT_PAD_S
    assert len(clip) / sr == pytest.approx(expected, abs=0.08)
    pad = int(bench.STT_PAD_S * sr)
    assert np.all(clip[:pad] == 0) and np.all(clip[-pad:] == 0)  # true silence, not room tone
    assert np.abs(clip[pad + int(0.2 * sr): pad + int(0.8 * sr)]).max() > 0.1  # the speech survived


def test_stt_clip_leaves_a_silent_take_alone(tmp_path):
    bench = _load("voice_bench")
    path = tmp_path / "silent.wav"
    sf.write(path, np.zeros(SR, dtype=np.float32), SR, subtype="PCM_16")
    clip, sr = sf.read(io.BytesIO(bench.stt_clip_bytes(path)), dtype="float32")
    assert len(clip) / sr == pytest.approx(1.0 + 2 * bench.STT_PAD_S, abs=0.01)


def test_scorecard_helpers_measure_against_the_reference(tmp_path):
    hl = _load("human_likeness")

    assert hl.semitones(220.0, 110.0) == 12.0
    assert hl.semitones(None, 110.0) is None
    assert hl.delta(0.5, 0.33, 2) == 0.17

    # Word confusions name what the STT heard instead of the written word.
    assert hl.confusions("Qo'qon va Xo'jayli", "qokon va hojayli") == [("qo'qon", "qokon"), ("xo'jayli", "hojayli")]
    assert hl.confusions("Salom qalaysiz", "salom qalaysiz uyoq") == [("∅", "uyoq")]
    assert hl.confusions("Salom", None) == []

    # The download-free timbre signature: a clip equals itself, a different pitch is further away.
    same = tmp_path / "same.wav"
    other = tmp_path / "other.wav"
    sf.write(same, _voiced(1.5, 180.0), SR, subtype="PCM_16")
    sf.write(other, _voiced(1.5, 300.0), SR, subtype="PCM_16")
    a, b = hl.mfcc_signature(same), hl.mfcc_signature(other)
    assert hl.similarity(a, a) == pytest.approx(1.0, abs=1e-5)
    assert hl.similarity(a, b) < hl.similarity(a, a)
    assert math.isclose(float((a * a).sum()), 1.0, abs_tol=1e-5)
