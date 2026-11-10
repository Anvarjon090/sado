"""Voice intake (owner rules, 2026-11-10): what a machine can check about a
human reference recording is checked here on synthetic signals, so the rules
are pinned without shipping anyone's voice in the repo.
"""
from __future__ import annotations

import numpy as np
import pytest
from services import voice_intake as vi

SR = 24_000


def speechlike(seconds: float, sr: int = SR, *, peak: float = 0.5, gap_at: float | None = None,
               gap_seconds: float = 0.0, lead: float = 0.3, trail: float = 0.4,
               noise_dbfs: float = -70.0, seed: int = 1) -> np.ndarray:
    """Band-limited noise bursts (words) with short pauses, over a quiet floor."""
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    out = rng.standard_normal(n) * (10 ** (noise_dbfs / 20))
    t = 0.0 + lead
    while t < seconds - trail:
        word = min(0.25, seconds - trail - t)
        start, stop = int(t * sr), int((t + word) * sr)
        burst = rng.standard_normal(stop - start)
        env = np.sin(np.linspace(0, np.pi, stop - start)) ** 0.5
        out[start:stop] += burst * env * 0.25
        t += word + 0.08
    if gap_at is not None:
        a, b = int(gap_at * sr), int((gap_at + gap_seconds) * sr)
        out[a:b] = rng.standard_normal(b - a) * (10 ** (noise_dbfs / 20))
    return out / np.max(np.abs(out)) * peak


def test_a_clean_take_measures_as_one_continuous_utterance():
    a = vi.analyze(speechlike(15.0), SR)
    assert 14.9 < a.duration_s < 15.1
    assert a.channels == 1 and a.clipped_runs == 0
    assert 0.2 <= a.lead_silence_s <= 0.4 and 0.3 <= a.trail_silence_s <= 0.5
    assert a.max_internal_gap_s < 0.2
    assert a.snr_db > vi.MIN_SNR_DB
    assert a.peak_dbfs == pytest.approx(20 * np.log10(0.5), abs=0.1)


def test_a_long_pause_fails_the_continuous_utterance_rule():
    a = vi.analyze(speechlike(15.0, gap_at=7.0, gap_seconds=2.0), SR)
    assert a.max_internal_gap_s == pytest.approx(2.0, abs=0.15)
    report = _report(a)
    vi.judge(report)
    assert any("uzluksiz emas" in f for f in report.failures)


def test_duration_sample_rate_clipping_and_noise_rules():
    short = _report(vi.analyze(speechlike(5.0), SR))
    vi.judge(short)
    assert any("Davomiylik 5.0 s" in f for f in short.failures)

    low_rate = _report(vi.analyze(speechlike(15.0, sr=16_000), 16_000))
    vi.judge(low_rate)
    assert any("16000 Hz" in f for f in low_rate.failures)

    clipped = speechlike(15.0, peak=1.0)
    clipped[SR * 5 : SR * 5 + 40] = 1.0
    hot = _report(vi.analyze(clipped, SR))
    vi.judge(hot)
    assert any("Klipping" in f for f in hot.failures)

    noisy = _report(vi.analyze(speechlike(15.0, noise_dbfs=-30.0), SR))
    vi.judge(noisy)
    assert any("Shovqin" in f for f in noisy.failures)


def test_stereo_is_downmixed_and_identical_channels_raise_no_warning():
    mono = speechlike(15.0)
    stereo = np.stack([mono, mono], axis=1)
    a = vi.analyze(stereo, SR)
    assert a.channels == 2
    assert a.stereo_difference_db is not None and a.stereo_difference_db < -60
    report = _report(a)
    vi.judge(report)
    assert not any("Stereo" in w for w in report.warnings)
    assert np.allclose(vi.to_mono(stereo), mono)


def test_normalize_hits_minus_16_lufs_or_stops_at_the_peak_ceiling():
    mono = speechlike(15.0, peak=0.1)  # −20 dBFS peak
    a = vi.analyze(mono, SR)
    quiet = vi.normalize(mono, SR, measured_lufs=-30.0, analysis=a)
    assert quiet.gain_db == pytest.approx(14.0) and not quiet.peak_limited
    assert np.max(np.abs(quiet.samples)) == pytest.approx(0.1 * 10 ** (14 / 20), rel=0.01)
    # 17 dB of gain would push the peak to −3 dBFS exactly; ask for more and it stops there.
    loud = vi.normalize(mono, SR, measured_lufs=-40.0, analysis=a)
    assert loud.peak_limited and loud.gain_db == pytest.approx(17.0, abs=0.05)
    assert 20 * np.log10(np.max(np.abs(loud.samples))) == pytest.approx(-3.0, abs=0.05)
    # Edges are trimmed to a quarter second of silence on each side.
    assert quiet.trimmed_lead_s == pytest.approx(0.3 - 0.25, abs=0.03)
    assert quiet.trimmed_trail_s == pytest.approx(0.4 - 0.25, abs=0.03)
    assert len(quiet.samples) < len(mono)


def test_text_helpers_normalize_apostrophes_and_measure_cer():
    assert vi.ascii_apostrophes("oʻzbek g‘oya o’rik") == "o'zbek g'oya o'rik"
    assert vi.cer("Men kichik bir qishloqda yashayman", "men kichik bir qishloqda yashayman.") == 0
    assert vi.cer("salom dunyo", "salom dunyo!") == 0
    assert vi.cer("salom dunyo", "salom dunya") == pytest.approx(0.1)
    assert vi.count_words("Bir bor ekan, bir yo'q ekan.") == 6
    assert vi.count_syllables("salom") == 2 and vi.count_syllables("o'rik") == 2
    assert vi.slug("Aisha toza (oʻzbekcha)") == "aisha_toza_ozbekcha"


def test_judge_requires_a_declared_human_source_and_consent():
    a = vi.analyze(speechlike(15.0), SR)
    own = _report(a, source="own", consent=False)
    vi.judge(own)
    assert any("roziligi" in f for f in own.failures)
    cv = _report(a, source="common-voice", license="")
    vi.judge(cv)
    assert any("litsenziya" in f for f in cv.failures)
    ok = _report(a, source="common-voice", license="CC0")
    vi.judge(ok)
    assert ok.accepted
    # The pace rule is reported as a warning, never a failure.
    assert any("so'z/s" in w for w in ok.warnings)


def test_a_mismatching_transcript_fails_the_reference_text_rule():
    a = vi.analyze(speechlike(15.0), SR)
    report = _report(a, transcript="butunlay boshqa gap aytilgan edi bu yerda")
    report.cer = vi.cer(report.ref_text, report.transcript)
    vi.judge(report)
    assert any("mos emas" in f for f in report.failures)


@pytest.mark.skipif(not __import__("services.ffmpeg_utils", fromlist=["find_ffmpeg"]).find_ffmpeg(),
                    reason="ffmpeg not available")
def test_ffmpeg_measures_loudness_of_a_known_tone(tmp_path):
    from services.ffmpeg_utils import find_ffmpeg

    t = np.arange(int(5 * SR)) / SR
    tone = 0.1 * np.sin(2 * np.pi * 1000 * t)  # −20 dBFS peak, −23 dBFS RMS, ≈ −23 LUFS
    path = tmp_path / "tone.wav"
    vi.write_pcm16(path, tone, SR)
    measured = vi.measure_lufs(find_ffmpeg(), path)
    assert measured is not None
    assert measured.input_i == pytest.approx(-23.0, abs=1.0)
    assert measured.input_tp == pytest.approx(-20.0, abs=0.5)


def _report(analysis: vi.Analysis, *, source: str = "own", consent: bool = True, license: str = "",
            transcript: str | None = None) -> vi.IntakeReport:
    text = "Men kichik bir qishloqda yashayman, qishlog'imiz juda chiroyli va tinch joy."
    return vi.IntakeReport(
        name="Sinov", language="uz", gender="ayol", age=30, region="Toshkent", ref_text=text,
        source=source, license=license, consent=consent, input_file="in.wav", output_file="out.wav",
        analysis=analysis, measured_lufs=-20.0, measured_true_peak=-6.0, output_lufs=-16.0,
        output_peak_dbfs=-3.5, gain_db=4.0, peak_limited=False,
        words=vi.count_words(text), syllables=vi.count_syllables(text),
        words_per_second=vi.count_words(text) / max(analysis.speech_seconds, 0.1),
        syllables_per_second=vi.count_syllables(text) / max(analysis.speech_seconds, 0.1),
        transcript=transcript, cer=None,
    )
