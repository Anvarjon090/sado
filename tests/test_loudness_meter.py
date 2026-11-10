"""BS.1770-4 meter (services/loudness_meter.py): the natural output preset is
only as honest as this measurement, so it is pinned against the standard's
own numbers and against ffmpeg's ebur128 where ffmpeg is available."""
from __future__ import annotations

import math

import numpy as np
import pytest

from services import loudness_meter as lm

SR = 24_000


def _sine(seconds: float, amp: float, freq: float = 1000.0, sr: int = SR) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_k_weighting_reproduces_the_standards_48k_coefficients():
    (b_shelf, a_shelf), (b_hp, a_hp) = lm.k_weighting_coefficients(48_000)
    # ITU-R BS.1770-4, Table 1 (pre-filter) and Table 2 (RLB), 48 kHz.
    assert b_shelf == pytest.approx([1.53512485958697, -2.69169618940638, 1.19839281085285], abs=1e-6)
    assert a_shelf == pytest.approx([1.0, -1.69065929318241, 0.73248077421585], abs=1e-6)
    assert b_hp == pytest.approx([1.0, -2.0, 1.0])
    assert a_hp == pytest.approx([1.0, -1.99004745483398, 0.99007225036621], abs=1e-6)


def test_a_minus_20_dbfs_1khz_sine_reads_about_minus_23_lufs():
    # 1 kHz sits in the flat part of the K curve: LUFS = RMS dBFS − 0.691.
    tone = _sine(5.0, 0.1)
    assert lm.integrated_loudness(tone, SR) == pytest.approx(-23.0, abs=0.3)
    assert lm.true_peak_dbtp(tone, SR) == pytest.approx(-20.0, abs=0.1)


def test_silence_and_empty_input_have_no_loudness():
    assert lm.integrated_loudness(np.zeros(SR), SR) is None
    assert lm.integrated_loudness(np.zeros(0), SR) is None
    assert lm.true_peak_dbtp(np.zeros(0), SR) == -math.inf


def test_gating_ignores_long_quiet_stretches():
    # 2 s of tone surrounded by 6 s of near-silence: the relative gate keeps
    # the integrated value on the tone, not on the average with the silence.
    quiet = np.full(3 * SR, 1e-5, dtype=np.float32)
    clip = np.concatenate([quiet, _sine(2.0, 0.1), quiet])
    # Blocks straddling the tone's edges pull it a few tenths under −23; the
    # ungated average with the silence would sit near −29.
    assert lm.integrated_loudness(clip, SR) == pytest.approx(-23.0, abs=0.8)


def test_channel_layouts_agree():
    mono = _sine(2.0, 0.1)
    stereo_cn = np.stack([mono, mono])
    assert lm.integrated_loudness(stereo_cn, SR) == pytest.approx(
        lm.integrated_loudness(mono, SR) + 3.01, abs=0.1
    )  # two coherent channels sum in power
    assert lm.integrated_loudness(stereo_cn.T, SR) == pytest.approx(
        lm.integrated_loudness(stereo_cn, SR), abs=1e-6
    )


def test_normalize_gain_is_a_single_constant_that_hits_the_target():
    tone = _sine(3.0, 0.05)  # about −29 LUFS
    out, info = lm.normalize_gain(tone, SR, target_lufs=-18.0, ceiling_dbtp=-1.5)
    assert info.input_lufs == pytest.approx(-29.0, abs=0.3)
    assert not info.peak_limited
    assert lm.integrated_loudness(out, SR) == pytest.approx(-18.0, abs=0.1)
    ratio = out[np.abs(tone) > 1e-3] / tone[np.abs(tone) > 1e-3]
    assert ratio.min() == pytest.approx(ratio.max(), rel=1e-5)  # gain only, no shaping
    assert out.dtype == np.float32


def test_normalize_gain_stops_at_the_true_peak_ceiling():
    # A crest factor of ~21 dB (a spike on a quiet tone): −18 LUFS would need
    # the spike past 0 dBTP, so the gain stops at the ceiling instead.
    tone = _sine(3.0, 0.02)
    tone[SR] = 0.5
    out, info = lm.normalize_gain(tone, SR, target_lufs=-18.0, ceiling_dbtp=-1.5)
    assert info.peak_limited
    assert lm.true_peak_dbtp(out, SR) == pytest.approx(-1.5, abs=0.05)
    assert lm.integrated_loudness(out, SR) < -18.0


def test_normalize_gain_leaves_silence_alone():
    silence = np.zeros(SR, dtype=np.float32)
    out, info = lm.normalize_gain(silence, SR)
    assert info.input_lufs is None and info.gain_db == 0.0
    assert np.array_equal(out, silence)


@pytest.mark.skipif(
    not __import__("services.ffmpeg_utils", fromlist=["find_ffmpeg"]).find_ffmpeg(),
    reason="ffmpeg not available",
)
def test_matches_ffmpeg_ebur128_on_speech_like_material(tmp_path):
    import re
    import subprocess

    import soundfile as sf

    from services.ffmpeg_utils import find_ffmpeg

    rng = np.random.default_rng(3)
    # Amplitude-modulated noise bursts: a spectrum and dynamics closer to
    # speech than a sine, so the gates and the K curve both matter.
    n = 6 * SR
    x = rng.standard_normal(n).astype(np.float32) * 0.05
    env = (np.sin(2 * np.pi * 3.0 * np.arange(n) / SR) > 0).astype(np.float32)
    x *= env
    path = tmp_path / "bursts.wav"
    sf.write(path, x, SR, subtype="PCM_16")
    out = subprocess.run(
        [find_ffmpeg(), "-nostats", "-i", str(path), "-filter_complex", "ebur128=peak=true",
         "-f", "null", "-"],
        capture_output=True, text=True, errors="replace", check=False,
    ).stderr
    tail = out[out.rfind("Summary:"):]
    ffmpeg_i = float(re.search(r"I:\s*(-?[\d.]+)", tail).group(1))
    assert lm.integrated_loudness(x, SR) == pytest.approx(ffmpeg_i, abs=0.2)
