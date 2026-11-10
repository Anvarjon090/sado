"""Objective proxies for how a speech clip will be heard — never a naturalness score.

What a machine can say about a recording or a synthesis, measured the same
way for both so a human reference and a generated take are comparable:

* loudness and dynamics: integrated LUFS, loudness range (LRA), crest factor,
  frame-level speech-intensity spread;
* pacing: speech seconds, pauses (count, mean, max), pause floor (room tone
  against digital silence);
* melody: F0 median, semitone spread and 5–95 % range, frame-to-frame
  micro-variation, voiced ratio;
* spectrum: band balance, 95 % roll-off, 4–8 kHz vs 1–4 kHz tilt.

These numbers catch the things that *make* a take sound synthetic — a
compressed dynamic range, a brightened spectrum, a flattened melody, no
breathing room between sentences — and they let an A/B say which direction a
change moved. They do not rank voices by beauty; ``scripts/voice_bench.py``
prints them next to an STT check and still asks the owner to listen.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
from scipy.signal import stft

from services.loudness_meter import integrated_loudness, k_weight

FRAME_S = 0.025
HOP_S = 0.010
#: An internal gap counts as a pause from here; shorter gaps are articulation.
MIN_PAUSE_S = 0.15


@dataclass
class SpeechMetrics:
    duration_s: float
    speech_s: float
    peak_dbfs: float
    rms_dbfs: float
    crest_db: float
    lufs: float | None
    lra_lu: float | None
    floor_dbfs: float
    level_std_db: float
    level_spread_db: float
    pauses: int
    pause_mean_s: float | None
    pause_max_s: float | None
    pause_floor_dbfs: float | None
    f0_median_hz: float | None
    f0_std_st: float | None
    f0_range_st: float | None
    f0_micro_st: float | None
    voiced_ratio: float
    band_db: dict = field(default_factory=dict)
    centroid_hz: float = 0.0
    rolloff95_hz: float = 0.0
    tilt_db: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _db(x: float) -> float:
    return 20.0 * float(np.log10(max(float(x), 1e-9)))


def to_mono(samples: np.ndarray) -> np.ndarray:
    x = np.asarray(samples, dtype=np.float32)
    if x.ndim == 2:
        x = x.mean(axis=1 if x.shape[1] < x.shape[0] else 0)
    return x


def frame_levels(x: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    """RMS level in dBFS per 25 ms frame at a 10 ms hop; returns (levels, hop)."""
    n, hop = int(sr * FRAME_S), int(sr * HOP_S)
    if len(x) < n:
        return np.array([_db(np.sqrt(np.mean(x ** 2) + 1e-12))]), hop
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop]
    return 20.0 * np.log10(np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-9), hop


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """``(start, end)`` index pairs of the True runs in ``mask``."""
    if mask.size == 0:
        return []
    d = np.diff(mask.astype(np.int8), prepend=0, append=0)
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def speech_mask(levels: np.ndarray) -> np.ndarray:
    """Frames that carry speech: 15 dB over the quietest 5 % and at most 30 dB
    under the loud frames, whichever is higher."""
    floor = float(np.percentile(levels, 5))
    threshold = max(floor + 15.0, float(np.percentile(levels, 90)) - 30.0)
    return levels > threshold


def loudness_range(x: np.ndarray, sr: int) -> float | None:
    """EBU R128 loudness range (LRA): 3 s short-term loudness, −70 LUFS absolute
    gate, −20 LU relative gate, 95th minus 10th percentile."""
    block = int(3.0 * sr)
    hop = int(1.0 * sr)
    z = k_weight(x, sr)[0] ** 2
    if len(z) < block:
        return 0.0
    starts = np.arange(0, len(z) - block + 1, hop)
    cumsum = np.concatenate([[0.0], np.cumsum(z)])
    power = (cumsum[starts + block] - cumsum[starts]) / block
    with np.errstate(divide="ignore"):
        st = -0.691 + 10.0 * np.log10(power)
    st = st[st > -70.0]
    if st.size == 0:
        return None
    rel = -0.691 + 10.0 * np.log10(np.mean(10 ** ((st + 0.691) / 10.0))) - 20.0
    st = st[st > rel]
    if st.size < 2:
        return 0.0
    return float(np.percentile(st, 95) - np.percentile(st, 10))


def pitch_track(x: np.ndarray, sr: int, hop_s: float = HOP_S) -> np.ndarray:
    """F0 per frame (Hz, 0 where unvoiced) via torchaudio's autocorrelation
    tracker, median-smoothed over 100 ms (10 frames): enough to drop octave
    glitches, short enough to keep a sentence's melody."""
    import torch
    import torchaudio

    t = torch.from_numpy(np.ascontiguousarray(x, dtype=np.float32)).unsqueeze(0)
    f0 = torchaudio.functional.detect_pitch_frequency(
        t, sr, frame_time=hop_s, win_length=10, freq_low=60, freq_high=450
    )
    return f0.squeeze(0).numpy()


def analyze_speech(samples: np.ndarray, sr: int) -> SpeechMetrics:
    x = to_mono(samples)
    duration = len(x) / sr
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    levels, hop = frame_levels(x, sr)
    hop_s = hop / sr
    active = speech_mask(levels)
    floor = float(np.percentile(levels, 5))
    idx = np.where(active)[0]
    if idx.size == 0:
        return SpeechMetrics(
            duration_s=round(duration, 3), speech_s=0.0, peak_dbfs=_db(peak), rms_dbfs=_db(rms),
            crest_db=_db(peak) - _db(rms), lufs=None, lra_lu=None, floor_dbfs=floor,
            level_std_db=0.0, level_spread_db=0.0, pauses=0, pause_mean_s=None, pause_max_s=None,
            pause_floor_dbfs=None, f0_median_hz=None, f0_std_st=None, f0_range_st=None,
            f0_micro_st=None, voiced_ratio=0.0,
        )
    first, last = idx[0], idx[-1]
    pauses = [(a, b) for a, b in runs(~active[first:last + 1]) if (b - a) * hop_s >= MIN_PAUSE_S]
    pause_lens = [(b - a) * hop_s for a, b in pauses]
    pause_floor = [float(np.median(levels[first + a:first + b])) for a, b in pauses]
    lvl_active = levels[active]

    f0 = pitch_track(x, sr, hop_s)
    m = min(len(f0), len(active))
    f0, act = f0[:m], active[:m]
    voiced = act & (f0 > 60) & (f0 < 450)
    if voiced.sum() > 10:
        med = float(np.median(f0[voiced]))
        voiced &= (f0 > med / 1.6) & (f0 < med * 1.6)  # drop octave errors
    f0v = f0[voiced]
    st = 12.0 * np.log2(f0v / 100.0) if f0v.size else np.array([])
    vi = np.where(voiced)[0]
    micro = None
    if vi.size > 2:
        adjacent = np.diff(vi) == 1
        steps = np.abs(np.diff(12.0 * np.log2(f0[vi] / 100.0)))[adjacent]
        micro = float(np.mean(steps)) if steps.size else None

    f, _, zxx = stft(x, fs=sr, nperseg=1024, noverlap=768)
    power = np.abs(zxx) ** 2
    frame_t = np.arange(power.shape[1]) * (256 / sr)
    act_t = np.interp(frame_t, np.arange(len(active)) * hop_s, active.astype(float)) > 0.5
    spec = power[:, act_t].mean(axis=1) if act_t.any() else power.mean(axis=1)
    total = float(spec.sum()) + 1e-12

    def band(lo: float, hi: float) -> float:
        sel = (f >= lo) & (f < hi)
        return float(10.0 * np.log10(spec[sel].sum() / total + 1e-12))

    bands = {"0-1k": band(0, 1000), "1-4k": band(1000, 4000), "4-8k": band(4000, 8000),
             "8k+": band(8000, sr / 2 + 1)}
    cumulative = np.cumsum(spec) / total
    return SpeechMetrics(
        duration_s=round(duration, 3),
        speech_s=round(float(active.sum() * hop_s), 3),
        peak_dbfs=round(_db(peak), 2),
        rms_dbfs=round(_db(rms), 2),
        crest_db=round(_db(peak) - _db(rms), 2),
        lufs=_round(integrated_loudness(x, sr)),
        lra_lu=_round(loudness_range(x, sr)),
        floor_dbfs=round(floor, 2),
        level_std_db=round(float(np.std(lvl_active)), 2),
        level_spread_db=round(float(np.percentile(lvl_active, 90) - np.percentile(lvl_active, 10)), 2),
        pauses=len(pauses),
        pause_mean_s=round(float(np.mean(pause_lens)), 3) if pause_lens else None,
        pause_max_s=round(max(pause_lens), 3) if pause_lens else None,
        pause_floor_dbfs=round(float(np.median(pause_floor)), 2) if pause_floor else None,
        f0_median_hz=round(float(np.median(f0v)), 1) if f0v.size else None,
        f0_std_st=round(float(np.std(st)), 3) if st.size else None,
        f0_range_st=round(float(np.percentile(st, 95) - np.percentile(st, 5)), 2) if st.size else None,
        f0_micro_st=_round(micro, 3),
        voiced_ratio=round(float(voiced.sum() / max(act.sum(), 1)), 3),
        band_db={k: round(v, 2) for k, v in bands.items()},
        centroid_hz=round(float((f * spec).sum() / total), 1),
        rolloff95_hz=round(float(f[min(int(np.searchsorted(cumulative, 0.95)), len(f) - 1)]), 1),
        tilt_db=round(bands["4-8k"] - bands["1-4k"], 2),
    )


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


#: Columns worth a glance in a comparison table, in reading order.
SUMMARY_COLUMNS = (
    "duration_s", "lufs", "lra_lu", "crest_db", "level_std_db", "pauses", "pause_mean_s",
    "pause_floor_dbfs", "f0_median_hz", "f0_std_st", "f0_range_st", "rolloff95_hz", "tilt_db",
)


def analyze_file(path: str) -> SpeechMetrics:
    import soundfile as sf

    samples, sr = sf.read(path, dtype="float32", always_2d=True)
    return analyze_speech(samples, sr)
