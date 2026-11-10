"""The natural output path (owner request, 2026-11-10): a cloned voice must
leave /generate with the dynamics, tone and pauses the model gave it.

* ``finalize_output('natural')`` is a single gain — no compressor, EQ or
  limiter touches the waveform — and it is the default everywhere.
* ``shape_pauses`` lengthens only the engine's own pauses, never explicit
  silence buffers, never past the cap, never when the scale is 1.
* Paragraph breaks become stitched spans with a real breath between them.
* ``denoise`` is decided from the reference's SNR unless the caller says.
"""
from __future__ import annotations

import io
import os

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

import importlib
from unittest.mock import MagicMock

import numpy as np
import pytest
import torch

from services import audio_dsp
from services.chunked_tts import PARAGRAPH_PAUSE_MS, paragraph_segments, text_segments
from services.loudness_meter import integrated_loudness, true_peak_dbtp

SR = 24_000


def speechlike(seconds: float, *, floor: float = 1e-4, gap_at: float | None = None,
               gap_s: float = 0.0, seed: int = 1) -> np.ndarray:
    """Noise bursts (words) with 80 ms articulation gaps over a quiet floor; an
    optional longer gap at ``gap_at`` seconds."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    out = rng.standard_normal(n).astype(np.float32) * floor
    t = 0.2
    while t < seconds - 0.2:
        a, b = int(t * SR), int(min(t + 0.25, seconds - 0.2) * SR)
        env = np.sin(np.linspace(0, np.pi, b - a)) ** 0.25
        out[a:b] += rng.standard_normal(b - a).astype(np.float32) * env * 0.2
        t += 0.25 + 0.04
    if gap_at is not None:
        a, b = int(gap_at * SR), int((gap_at + gap_s) * SR)
        out[a:b] = rng.standard_normal(b - a).astype(np.float32) * floor
    return out


# ── finalize_output / natural ──────────────────────────────────────────────


def test_natural_is_the_default_and_is_gain_only():
    assert audio_dsp.DEFAULT_EFFECT_PRESET == "natural"
    assert "natural" in audio_dsp.EFFECT_PRESETS and audio_dsp.EFFECT_PRESETS["natural"]["chain"] == []
    x = torch.from_numpy(speechlike(4.0))[None, :] * 0.3
    y = audio_dsp.finalize_output(x, SR)
    ratio = (y / x)[x.abs() > 1e-3]
    assert ratio.min().item() == pytest.approx(ratio.max().item(), rel=1e-5)
    assert integrated_loudness(y[0].numpy(), SR) == pytest.approx(audio_dsp.NATURAL_TARGET_LUFS, abs=0.2)
    assert true_peak_dbtp(y[0].numpy(), SR) <= audio_dsp.NATURAL_CEILING_DBTP + 0.05
    assert y.shape == x.shape and y.dtype == x.dtype


def test_natural_never_amplifies_silence_and_never_calls_the_coloured_chain(monkeypatch):
    mastering = MagicMock(side_effect=lambda t, sample_rate=24000: t)
    monkeypatch.setattr(audio_dsp, "apply_mastering", mastering)
    silence = torch.zeros(1, SR)
    assert audio_dsp.finalize_output(silence, SR) is silence
    audio_dsp.finalize_output(torch.from_numpy(speechlike(3.0))[None, :], SR)
    assert mastering.call_count == 0
    audio_dsp.finalize_output(torch.from_numpy(speechlike(3.0))[None, :], SR, "broadcast")
    assert mastering.call_count == 1


def test_raw_passes_through_and_unknown_presets_are_rejected():
    x = torch.from_numpy(speechlike(2.0))[None, :]
    assert audio_dsp.finalize_output(x, SR, "raw", pause_scale=2.0) is x
    with pytest.raises(ValueError, match="Unknown effect preset"):
        audio_dsp.finalize_output(x, SR, "loud")


# ── shape_pauses ───────────────────────────────────────────────────────────


def test_shape_pauses_lengthens_the_engines_pause_with_its_own_room_tone():
    x = torch.from_numpy(speechlike(6.0, gap_at=3.0, gap_s=0.2))
    y = audio_dsp.shape_pauses(x, SR, 2.0)
    added = y.shape[-1] - x.shape[-1]
    assert added == pytest.approx(0.2 * SR, abs=0.03 * SR)  # 0.2 s → 0.4 s
    # The fill is room tone at the gap's level, not digital silence.
    mid = y.shape[-1] // 2
    fill = y[mid - int(0.05 * SR): mid + int(0.05 * SR)].numpy()
    assert 0 < np.abs(fill).max() < 1e-3
    assert y.dtype == x.dtype


def test_shape_pauses_caps_skips_explicit_silence_and_is_identity_at_one():
    x = torch.from_numpy(speechlike(6.0, gap_at=3.0, gap_s=0.6))
    capped = audio_dsp.shape_pauses(x, SR, 3.0)  # 0.6 × 3 = 1.8 s → capped at 0.9 s
    assert capped.shape[-1] - x.shape[-1] == pytest.approx(0.3 * SR, abs=0.03 * SR)
    assert audio_dsp.shape_pauses(x, SR, 1.0) is x
    # An inserted [pause] buffer is exact zeros and must stay exactly as long:
    # only the engine's 0.6 s pause grows (to the 0.9 s cap).
    buffered = torch.cat([x[: 2 * SR], torch.zeros(int(0.5 * SR)), x[2 * SR:]])
    out = audio_dsp.shape_pauses(buffered, SR, 2.0)
    assert out.shape[-1] - buffered.shape[-1] == pytest.approx(0.3 * SR, abs=0.03 * SR)
    # No pause at all → nothing to do, same object back.
    plain = torch.from_numpy(speechlike(3.0))
    assert audio_dsp.shape_pauses(plain, SR, 2.0) is plain


def test_shape_pauses_handles_channel_first_audio():
    mono = speechlike(5.0, gap_at=2.5, gap_s=0.3)
    stereo = torch.from_numpy(np.stack([mono, mono * 0.5]))
    out = audio_dsp.shape_pauses(stereo, SR, 1.5)
    assert out.shape[0] == 2
    assert out.shape[1] - stereo.shape[1] == pytest.approx(0.15 * SR, abs=0.03 * SR)


# ── paragraph spans ────────────────────────────────────────────────────────


def test_paragraph_breaks_become_spans_with_a_breath_between_them():
    assert paragraph_segments("Bir gap.") == [("Bir gap.", 0)]
    assert paragraph_segments("Birinchi xatboshi.\n\nIkkinchi xatboshi.") == [
        ("Birinchi xatboshi.", PARAGRAPH_PAUSE_MS), ("Ikkinchi xatboshi.", 0),
    ]
    # Explicit markers win over paragraphs; a single paragraph is not stitched.
    assert text_segments("Salom [pause 300ms] dunyo") == ([("Salom ", 300), (" dunyo", 0)], True)
    assert text_segments("Salom dunyo.\nYangi qator, lekin xatboshi emas.")[1] is False
    assert text_segments("A.\n\nB.")[1] is True


# ── /generate wiring ───────────────────────────────────────────────────────


def _tts_mod():
    return importlib.import_module("services.tts_backend")


def _fake_engine():
    class _FakeEngine(_tts_mod().TTSBackend):
        id = "fake-natural"
        display_name = "Fake Engine (natural tests)"
        applies_own_mastering = False
        gpu_compat = ("cpu",)
        calls: list = []  # noqa: RUF012 — per-class recorder, reset by the tests

        @property
        def sample_rate(self) -> int:
            return SR

        @property
        def supported_languages(self) -> list[str]:
            return ["multi"]

        @classmethod
        def is_available(cls):
            return True, "ready"

        def generate(self, text, **kw) -> torch.Tensor:
            type(self).calls.append((text, kw))
            return torch.zeros(1, SR)

    return _FakeEngine


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient

    import api.routers.generation as gen_mod
    from main import app

    async def _boom():
        raise AssertionError("get_model() was called — the fake engine was bypassed")

    monkeypatch.setattr(gen_mod, "get_model", _boom)
    fake = _fake_engine()
    monkeypatch.setitem(_tts_mod()._REGISTRY, fake.id, fake)
    client = TestClient(app, client=("127.0.0.1", 50000))
    client.fake = fake
    return client


def _wav_bytes(x: np.ndarray) -> bytes:
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, x, SR, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def test_generate_defaults_to_natural_and_forwards_pause_scale(client, monkeypatch):
    seen = {}

    def _finalize(audio, sr, preset=audio_dsp.DEFAULT_EFFECT_PRESET, *, skip_mastering=False, pause_scale=1.0):
        seen.update(preset=preset, pause_scale=pause_scale, skip=skip_mastering)
        return audio

    monkeypatch.setattr(audio_dsp, "finalize_output", _finalize)
    res = client.post("/generate", data={"text": "Salom dunyo", "engine": "fake-natural"})
    assert res.status_code == 200, res.text
    assert seen == {"preset": "natural", "pause_scale": 1.0, "skip": False}

    res = client.post("/generate", data={"text": "Salom dunyo", "engine": "fake-natural",
                                         "effect_preset": "broadcast", "pause_scale": "1.6"})
    assert res.status_code == 200, res.text
    assert seen["preset"] == "broadcast" and seen["pause_scale"] == 1.6

    res = client.post("/generate", data={"text": "Salom", "engine": "fake-natural", "pause_scale": "0.5"})
    assert res.status_code == 422


def test_generate_stitches_paragraphs_with_a_breath(client):
    client.fake.calls.clear()
    res = client.post("/generate", data={"text": "Birinchi xatboshi.\n\nIkkinchi xatboshi.",
                                         "engine": "fake-natural", "effect_preset": "raw"})
    assert res.status_code == 200, res.text
    assert [c[0] for c in client.fake.calls] == ["Birinchi xatboshi.", "Ikkinchi xatboshi."]
    import soundfile as sf

    audio, sr = sf.read(io.BytesIO(res.content), dtype="float32")
    assert sr == SR
    assert len(audio) == 2 * SR + round(SR * PARAGRAPH_PAUSE_MS / 1000)


def test_denoise_is_decided_by_the_references_noise_floor(client):
    clean = _wav_bytes(speechlike(3.0, floor=1e-5))
    noisy = _wav_bytes(speechlike(3.0, floor=3e-2))

    client.fake.calls.clear()
    res = client.post("/generate", data={"text": "Salom", "engine": "fake-natural", "ref_text": "salom"},
                      files={"ref_audio": ("clean.wav", clean, "audio/wav")})
    assert res.status_code == 200, res.text
    assert client.fake.calls[-1][1]["denoise"] is False

    res = client.post("/generate", data={"text": "Salom", "engine": "fake-natural", "ref_text": "salom"},
                      files={"ref_audio": ("noisy.wav", noisy, "audio/wav")})
    assert res.status_code == 200, res.text
    assert client.fake.calls[-1][1]["denoise"] is True

    # An explicit choice always wins over the measurement.
    res = client.post("/generate", data={"text": "Salom", "engine": "fake-natural", "ref_text": "salom",
                                         "denoise": "true"},
                      files={"ref_audio": ("clean.wav", clean, "audio/wav")})
    assert res.status_code == 200, res.text
    assert client.fake.calls[-1][1]["denoise"] is True

    # Voice design has no reference and therefore nothing to clean.
    res = client.post("/generate", data={"text": "Salom", "engine": "fake-natural"})
    assert res.status_code == 200, res.text
    assert client.fake.calls[-1][1]["denoise"] is False


def test_reference_acoustics_measures_and_caches(tmp_path):
    import soundfile as sf

    from services import reference_acoustics as ra

    clean = tmp_path / "clean.wav"
    sf.write(clean, speechlike(3.0, floor=1e-5), SR, subtype="PCM_16")
    assert ra.reference_snr_db(str(clean)) > ra.DENOISE_BELOW_SNR_DB
    assert ra.reference_wants_denoise(str(clean)) is False
    noisy = tmp_path / "noisy.wav"
    sf.write(noisy, speechlike(3.0, floor=3e-2), SR, subtype="PCM_16")
    assert ra.reference_wants_denoise(str(noisy)) is True
    assert ra.reference_wants_denoise(str(tmp_path / "missing.wav")) is True  # unmeasurable → clean up
    assert ra.reference_wants_denoise(None) is False
    cached = ra._snr_cached.cache_info()
    ra.reference_snr_db(str(clean))
    assert ra._snr_cached.cache_info().hits == cached.hits + 1
