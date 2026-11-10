"""Voice intake: measure a human reference recording against Sado's acceptance
rules and master it into a reference clip (owner rules, 2026-11-10).

The rules, as the owner wrote them:

* a real person, one speaker, one continuous utterance of 12–20 s, no music,
  noise, reverb or second voice;
* natural pace (the owner's figure is 3.5–4.5 words/s — faster than natural
  Uzbek speech at ~2–2.5 words/s, so the pace is *reported*, never enforced);
* mono WAV, ≥ 24 kHz, 16-bit, peak −3 dBFS, integrated −16 LUFS;
* the reference text is what is said, word for word, with ASCII apostrophes;
* a generated sentence is listened to before the voice is accepted.

What a machine can check lives here, as pure functions over a numpy signal
plus one ffmpeg call for BS.1770 loudness (the same `loudnorm` measure the
longform master uses). What only an ear can check — naturalness, a second
voice, reverb — is left to the listener, and the report says so.

Nothing here decides whether the recording is a real person: that is a
declared fact (``source`` / ``consent`` in the metadata), and the pipeline
refuses to run without it.
"""
from __future__ import annotations

import json
import re
import subprocess
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from services.longform_render import MeasuredLoudness, parse_loudnorm_measure

MIN_SECONDS = 12.0
MAX_SECONDS = 20.0
MIN_SAMPLE_RATE = 24_000
TARGET_LUFS = -16.0
TARGET_PEAK_DBFS = -3.0
LUFS_TOLERANCE = 1.5
#: A pause longer than this inside the take means two utterances, not one.
MAX_INTERNAL_GAP_S = 1.2
#: Silence kept before the first and after the last word of the mastered clip.
EDGE_SILENCE_S = 0.25
MIN_SNR_DB = 25.0
#: The owner's pace window, in words per second. Reported, not enforced.
WORDS_PER_SECOND = (3.5, 4.5)
MAX_CER = 0.15
#: Sources the rules allow, each with the proof it needs in the metadata.
SOURCES = ("own", "consented", "common-voice", "open-license")
GENDERS = {"erkak": "erkak", "ayol": "ayol", "male": "erkak", "female": "ayol", "m": "erkak", "f": "ayol"}

_FRAME_S = 0.02
_ACTIVE_BELOW_PEAK_DB = 35.0
_APOSTROPHES = str.maketrans({"ʻ": "'", "ʼ": "'", "’": "'", "‘": "'", "`": "'", "´": "'", "ʹ": "'"})
_VOWELS = frozenset("aeiou")


# ── pure signal analysis ───────────────────────────────────────────────────


@dataclass
class Analysis:
    sample_rate: int
    channels: int
    duration_s: float
    peak_dbfs: float
    clipped_runs: int
    speech_db: float
    noise_db: float
    snr_db: float
    lead_silence_s: float
    trail_silence_s: float
    max_internal_gap_s: float
    speech_seconds: float
    stereo_difference_db: float | None


def to_mono(samples: np.ndarray) -> np.ndarray:
    """Average the channels; a plain downmix is what the TTS engines load."""
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim == 1:
        return data
    return data.mean(axis=1)


def _db(value: float) -> float:
    return float(20.0 * np.log10(max(float(value), 1e-12)))


def frame_levels(mono: np.ndarray, sample_rate: int) -> np.ndarray:
    """RMS level in dBFS per 20 ms frame."""
    size = max(1, round(sample_rate * _FRAME_S))
    count = len(mono) // size
    if count == 0:
        return np.asarray([_db(np.sqrt(np.mean(np.square(mono)))) if len(mono) else -120.0])
    frames = mono[: count * size].reshape(count, size)
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    return 20.0 * np.log10(np.maximum(rms, 1e-12))


def analyze(samples: np.ndarray, sample_rate: int) -> Analysis:
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim == 1:
        data = data[:, None]
    channels = data.shape[1]
    mono = to_mono(data)
    duration = len(mono) / sample_rate

    stereo_difference = None
    if channels > 1:
        side = data[:, 0] - data[:, 1]
        mid = data[:, 0] + data[:, 1]
        stereo_difference = _db(np.sqrt(np.mean(side * side))) - _db(np.sqrt(np.mean(mid * mid)))

    peak = float(np.max(np.abs(data))) if len(data) else 0.0
    hot = (np.abs(data) >= 0.999).any(axis=1).astype(np.int8)
    edges = np.diff(np.concatenate(([0], hot, [0])))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    clipped_runs = int(np.count_nonzero(ends - starts >= 3))

    levels = frame_levels(mono, sample_rate)
    active = levels > (levels.max() - _ACTIVE_BELOW_PEAK_DB)
    if not active.any():
        return Analysis(sample_rate, channels, duration, _db(peak), clipped_runs, -120.0, -120.0,
                        0.0, duration, 0.0, 0.0, 0.0, stereo_difference)
    speech_db = float(np.median(levels[active]))
    quiet = levels[~active]
    noise_db = float(np.percentile(quiet, 50)) if len(quiet) else float(np.percentile(levels, 10))
    first, last = int(np.argmax(active)), int(len(active) - 1 - np.argmax(active[::-1]))
    inner = active[first : last + 1]
    gap_edges = np.diff(np.concatenate(([1], inner.astype(np.int8), [1])))
    gap_starts, gap_ends = np.flatnonzero(gap_edges == -1), np.flatnonzero(gap_edges == 1)
    max_gap = float((gap_ends - gap_starts).max()) * _FRAME_S if len(gap_starts) else 0.0
    return Analysis(
        sample_rate=sample_rate,
        channels=channels,
        duration_s=duration,
        peak_dbfs=_db(peak),
        clipped_runs=clipped_runs,
        speech_db=speech_db,
        noise_db=noise_db,
        snr_db=speech_db - noise_db,
        lead_silence_s=first * _FRAME_S,
        trail_silence_s=(len(active) - 1 - last) * _FRAME_S,
        max_internal_gap_s=max_gap,
        speech_seconds=(last - first + 1) * _FRAME_S,
        stereo_difference_db=stereo_difference,
    )


# ── mastering ──────────────────────────────────────────────────────────────


@dataclass
class Mastered:
    samples: np.ndarray
    gain_db: float
    peak_limited: bool
    trimmed_lead_s: float
    trimmed_trail_s: float


def normalize(mono: np.ndarray, sample_rate: int, measured_lufs: float, analysis: Analysis) -> Mastered:
    """Linear gain to −16 LUFS, held back so the sample peak stays at or
    below −3 dBFS, then edge silence trimmed to a quarter second.

    Speech with a crest factor above 13 dB cannot meet both targets without a
    limiter, and a limiter would change the voice the engines clone; the
    report calls that out as ``peak_limited`` instead of pretending.
    """
    gain_db = TARGET_LUFS - measured_lufs
    peak_limited = False
    if analysis.peak_dbfs + gain_db > TARGET_PEAK_DBFS:
        gain_db = TARGET_PEAK_DBFS - analysis.peak_dbfs
        peak_limited = True
    out = np.asarray(mono, dtype=np.float64) * (10.0 ** (gain_db / 20.0))
    keep = int(EDGE_SILENCE_S * sample_rate)
    lead = max(0, int(analysis.lead_silence_s * sample_rate) - keep)
    trail = max(0, int(analysis.trail_silence_s * sample_rate) - keep)
    out = out[lead : len(out) - trail if trail else len(out)]
    return Mastered(out, gain_db, peak_limited, lead / sample_rate, trail / sample_rate)


def write_pcm16(path: Path, mono: np.ndarray, sample_rate: int) -> None:
    sf.write(str(path), np.clip(mono, -1.0, 1.0).astype(np.float32), sample_rate, subtype="PCM_16")


# ── ffmpeg: decode anything, measure loudness ──────────────────────────────


def decode(ffmpeg: str, source: Path, target: Path) -> None:
    """Decode any container to float WAV at its own sample rate and channels."""
    subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
         "-vn", "-acodec", "pcm_f32le", "-f", "wav", str(target)],
        check=True, capture_output=True, timeout=120,
    )


def measure_lufs(ffmpeg: str, path: Path) -> MeasuredLoudness | None:
    """BS.1770 integrated loudness and true peak via ffmpeg's loudnorm pass."""
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-af",
         f"loudnorm=I={TARGET_LUFS}:TP={TARGET_PEAK_DBFS}:LRA=11:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=120, check=False,
    )
    return parse_loudnorm_measure(proc.stderr)


# ── text ───────────────────────────────────────────────────────────────────


def ascii_apostrophes(text: str) -> str:
    return unicodedata.normalize("NFC", text).translate(_APOSTROPHES)


def normalize_text(text: str) -> str:
    text = ascii_apostrophes(text).lower()
    text = re.sub(r"[^a-z'\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalize_text(reference).replace(" ", ""), normalize_text(hypothesis).replace(" ", "")
    previous = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        current = [i]
        for j, hc in enumerate(hyp, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (rc != hc)))
        previous = current
    return previous[-1] / max(1, len(ref))


def count_words(text: str) -> int:
    return len(normalize_text(text).split())


def count_syllables(text: str) -> int:
    """Uzbek is written one vowel letter per syllable (oʻ is a vowel, gʻ is not)."""
    return sum(1 for ch in normalize_text(text) if ch in _VOWELS)


def slug(text: str) -> str:
    text = ascii_apostrophes(unicodedata.normalize("NFKD", text)).replace("'", "")
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return text or "ovoz"


# ── the report ─────────────────────────────────────────────────────────────


@dataclass
class IntakeReport:
    name: str
    language: str
    gender: str
    age: int | None
    region: str
    ref_text: str
    source: str
    license: str
    consent: bool
    input_file: str
    output_file: str
    analysis: Analysis
    measured_lufs: float | None
    measured_true_peak: float | None
    output_lufs: float | None
    output_peak_dbfs: float
    gain_db: float
    peak_limited: bool
    words: int
    syllables: int
    words_per_second: float
    syllables_per_second: float
    transcript: str | None
    cer: float | None
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manual_checks: list[str] = field(default_factory=lambda: [
        "Bitta odam gapiryaptimi, ikkinchi ovoz yo'qmi",
        "Musiqa, reverb, telefon effekti yo'qmi",
        "Ohang tabiiy, neytral yoki iliqmi (baqirmaydi, pichirlamaydi)",
        "Generatsiya namunasi: robotik yoki jarangli emasmi, nafas bormi",
    ])

    @property
    def accepted(self) -> bool:
        return not self.failures

    def to_metadata(self) -> dict:
        data = asdict(self)
        data["analysis"] = asdict(self.analysis)
        return data

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_metadata(), ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


def judge(report: IntakeReport) -> None:
    """Fill ``failures`` / ``warnings`` from the measurements. Idempotent."""
    a = report.analysis
    failures, warnings = [], []
    if report.source not in SOURCES:
        failures.append(f"Manba ko'rsatilmagan yoki noma'lum: {report.source!r} ({', '.join(SOURCES)})")
    if report.source in ("own", "consented") and not report.consent:
        failures.append("Yozuv egasining roziligi tasdiqlanmagan (--consent)")
    if report.source in ("common-voice", "open-license") and not report.license.strip():
        failures.append("Ochiq manba uchun litsenziya yozilmagan (--license)")
    if not (MIN_SECONDS <= a.duration_s <= MAX_SECONDS):
        failures.append(f"Davomiylik {a.duration_s:.1f} s; kerak: {MIN_SECONDS:.0f}–{MAX_SECONDS:.0f} s")
    if a.sample_rate < MIN_SAMPLE_RATE:
        failures.append(f"Diskretlash {a.sample_rate} Hz; kerak: kamida {MIN_SAMPLE_RATE} Hz")
    if a.clipped_runs:
        failures.append(f"Klipping: {a.clipped_runs} ta joyda signal kesilgan")
    if a.max_internal_gap_s > MAX_INTERNAL_GAP_S:
        failures.append(f"Gap uzluksiz emas: ichida {a.max_internal_gap_s:.1f} s pauza bor")
    if a.snr_db < MIN_SNR_DB:
        failures.append(f"Shovqin yuqori: SNR {a.snr_db:.0f} dB; kerak: kamida {MIN_SNR_DB:.0f} dB")
    if a.speech_seconds < 1.0:
        failures.append("Nutq topilmadi")
    if not report.ref_text.strip():
        failures.append("Ref matn bo'sh")
    if report.cer is not None and report.cer > MAX_CER:
        failures.append(f"Ref matn audio bilan mos emas: CER {report.cer:.0%} (chegara {MAX_CER:.0%})")
    if a.channels > 1 and a.stereo_difference_db is not None and a.stereo_difference_db > -20:
        warnings.append(f"Stereo kanallar farq qiladi ({a.stereo_difference_db:.0f} dB); mono'ga yig'ildi")
    if report.peak_limited:
        warnings.append(
            f"Peak -3 dBFS chegarasi tufayli {report.output_lufs if report.output_lufs is not None else TARGET_LUFS:.1f} LUFS'da to'xtadi (maqsad {TARGET_LUFS:.0f})"
        )
    elif report.output_lufs is not None and abs(report.output_lufs - TARGET_LUFS) > LUFS_TOLERANCE:
        warnings.append(f"O'rtacha balandlik {report.output_lufs:.1f} LUFS (maqsad {TARGET_LUFS:.0f})")
    if report.measured_lufs is None:
        warnings.append("LUFS o'lchanmadi (ffmpeg loudnorm javob bermadi); faqat peak'ga normallashtirildi")
    low, high = WORDS_PER_SECOND
    if not (low <= report.words_per_second <= high):
        warnings.append(
            f"Tezlik {report.words_per_second:.1f} so'z/s ({report.syllables_per_second:.1f} bo'g'in/s); "
            f"qoidadagi oraliq {low}–{high} so'z/s — tabiiy o'zbek nutqi odatda 2–2.5 so'z/s"
        )
    if report.cer is None:
        warnings.append("STT ishlamadi; ref matn audio bilan solishtirilmadi")
    if report.ref_text != ascii_apostrophes(report.ref_text):
        warnings.append("Ref matndagi apostroflar ASCII (') ga almashtirildi")
    report.failures, report.warnings = failures, warnings
