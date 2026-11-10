"""ITU-R BS.1770-4 integrated loudness and true peak, in numpy.

The ``natural`` output preset (``services.audio_dsp``) needs a loudness
measurement on every take, so this is a dependency-free port of the
standard rather than an ffmpeg ``ebur128`` subprocess per generate:

* K-weighting: the stage-1 high shelf and the stage-2 RLB high-pass, designed
  for the actual sample rate (the standard tabulates 48 kHz only; the
  design formulas reproduce those coefficients, which the tests check).
* Gating: 400 ms blocks with 75 % overlap, an absolute gate at −70 LUFS and
  a relative gate 10 LU under the ungated mean.
* True peak: 4× oversampled sample peak.

Everything here is a measurement or a plain gain; nothing shapes the
waveform. Accepts mono ``(n,)`` or ``(channels, n)`` arrays.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter, resample_poly

#: Below this, BS.1770 treats a block as silence (absolute gate).
ABSOLUTE_GATE_LUFS = -70.0
RELATIVE_GATE_LU = -10.0
BLOCK_S = 0.400
BLOCK_OVERLAP = 0.75


def k_weighting_coefficients(sample_rate: int) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]:
    """``((b_shelf, a_shelf), (b_hp, a_hp))`` of the two K-weighting stages.

    Stage 1 is the +4 dB high shelf above ~1.7 kHz the standard uses to model
    the head; stage 2 is the second-order RLB high-pass near 38 Hz.
    """
    fs = float(sample_rate)
    # Stage 1 — high shelf, in the bilinear form (De Man) that reproduces the
    # standard's tabulated 48 kHz coefficients to six decimals.
    gain_db, f0, q = 3.999843853973347, 1681.974450955533, 0.7071752369554196
    k = math.tan(math.pi * f0 / fs)
    vh = 10 ** (gain_db / 20.0)
    vb = vh ** 0.499666774155
    denom = 1.0 + k / q + k * k
    shelf = (
        np.array([(vh + vb * k / q + k * k) / denom, 2.0 * (k * k - vh) / denom,
                  (vh - vb * k / q + k * k) / denom]),
        np.array([1.0, 2.0 * (k * k - 1.0) / denom, (1.0 - k / q + k * k) / denom]),
    )
    # Stage 2 — RLB high-pass.
    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / fs)
    denom = 1.0 + k / q + k * k
    hp = (
        np.array([1.0, -2.0, 1.0]),
        np.array([1.0, 2.0 * (k * k - 1.0) / denom, (1.0 - k / q + k * k) / denom]),
    )
    return shelf, hp


def _as_channels(audio) -> np.ndarray:
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim == 1:
        x = x[None, :]
    elif x.ndim > 2:
        raise ValueError("audio must be (n,) or (channels, n)")
    if x.size == 0:
        return x.reshape(1, 0)
    if x.shape[0] > x.shape[1]:
        # (n, channels) is the other common layout; channels are few.
        x = x.T
    return x


def k_weight(audio, sample_rate: int) -> np.ndarray:
    """K-weighted copy of ``audio`` as ``(channels, n)``."""
    x = _as_channels(audio)
    (b1, a1), (b2, a2) = k_weighting_coefficients(sample_rate)
    y = lfilter(b1, a1, x, axis=-1)
    return lfilter(b2, a2, y, axis=-1)


def integrated_loudness(audio, sample_rate: int) -> float | None:
    """Gated integrated loudness in LUFS, or ``None`` when every block is
    under the absolute gate (silence / a dead render)."""
    x = _as_channels(audio)
    if x.shape[1] == 0:
        return None
    z = k_weight(x, sample_rate) ** 2
    block = round(BLOCK_S * sample_rate)
    hop = max(1, round(block * (1.0 - BLOCK_OVERLAP)))
    if z.shape[1] <= block:
        means = z.mean(axis=1, keepdims=True)  # one block: the whole clip
    else:
        starts = np.arange(0, z.shape[1] - block + 1, hop)
        cumsum = np.concatenate([np.zeros((z.shape[0], 1)), np.cumsum(z, axis=1)], axis=1)
        means = (cumsum[:, starts + block] - cumsum[:, starts]) / block
    # Channel weights G_i are 1 for mono / left / right (no surround here).
    power = means.sum(axis=0)
    with np.errstate(divide="ignore"):
        block_loudness = -0.691 + 10.0 * np.log10(power)
    above_abs = block_loudness > ABSOLUTE_GATE_LUFS
    if not above_abs.any():
        return None
    relative_gate = -0.691 + 10.0 * math.log10(power[above_abs].mean()) + RELATIVE_GATE_LU
    gated = above_abs & (block_loudness > relative_gate)
    if not gated.any():
        return None
    return float(-0.691 + 10.0 * math.log10(power[gated].mean()))


def true_peak_dbtp(audio, sample_rate: int, oversample: int = 4) -> float:
    """Inter-sample (true) peak in dBTP via ``oversample``× polyphase upsampling."""
    x = _as_channels(audio)
    if x.shape[1] == 0:
        return -math.inf
    up = resample_poly(x, oversample, 1, axis=-1) if oversample > 1 else x
    peak = float(np.max(np.abs(up)))
    return 20.0 * math.log10(peak) if peak > 0 else -math.inf


@dataclass(frozen=True)
class LoudnessNormalization:
    input_lufs: float | None
    input_true_peak_dbtp: float
    gain_db: float
    #: True when the true-peak ceiling, not the loudness target, set the gain.
    peak_limited: bool


def normalize_gain(
    audio,
    sample_rate: int,
    *,
    target_lufs: float = -18.0,
    ceiling_dbtp: float = -1.5,
) -> tuple[np.ndarray, LoudnessNormalization]:
    """Gain-only loudness normalization: scale ``audio`` so its integrated
    loudness lands on ``target_lufs`` unless that would push the true peak
    over ``ceiling_dbtp``, in which case the gain stops at the ceiling.

    No compression, limiting, EQ or clipping: the output is the input times a
    constant, so every dynamic contour of the voice survives. Silence (no
    block above the absolute gate) is returned untouched instead of being
    amplified into hiss.
    """
    x = np.asarray(audio, dtype=np.float32)
    lufs = integrated_loudness(x, sample_rate)
    peak = true_peak_dbtp(x, sample_rate)
    if lufs is None or not math.isfinite(peak):
        return x, LoudnessNormalization(lufs, peak, 0.0, False)
    gain_db = target_lufs - lufs
    limited = False
    if peak + gain_db > ceiling_dbtp:
        gain_db = ceiling_dbtp - peak
        limited = True
    return (x * (10.0 ** (gain_db / 20.0))).astype(np.float32), LoudnessNormalization(
        lufs, peak, float(gain_db), limited
    )
