"""Manual voice tuning: pitch, timbre and tempo of a clone's reference."""

import io

import numpy as np
import pytest
import soundfile as sf
from scipy.signal import lfilter, welch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.voice_tune import tune_audio

RATE = 24000


FORMANTS = (700.0, 1800.0, 2700.0)


def voiced(f0: float = 150.0, seconds: float = 2.0) -> np.ndarray:
    """A sustained synthetic vowel: a pulse train through three formant resonators."""
    source = np.zeros(int(RATE * seconds))
    source[:: int(RATE / f0)] = 1.0
    signal = source
    for freq in FORMANTS:
        radius = np.exp(-np.pi * 90.0 / RATE)
        theta = 2 * np.pi * freq / RATE
        signal = lfilter([1.0], [1.0, -2 * radius * np.cos(theta), radius**2], signal)
    return (0.3 * signal / np.max(np.abs(signal))).astype(np.float32)[np.newaxis, :]


def fundamental(audio: np.ndarray) -> float:
    """Autocorrelation pitch of the middle second (robust to formant moves)."""
    x = audio[0]
    x = x[len(x) // 4: len(x) // 4 + RATE // 2]
    x = x - x.mean()
    corr = np.correlate(x, x, mode="full")[len(x) - 1:]
    low, high = RATE // 500, RATE // 60
    return RATE / (low + int(np.argmax(corr[low:high])))


def envelope_stretch(before: np.ndarray, after: np.ndarray) -> float:
    """How far the spectral envelope (the formants) moved along the frequency axis.

    The cepstrally smoothed long-term spectrum drops the harmonics, so a pitch
    change alone reads 1.0 and a formant shift of n semitones reads 2**(n/12).
    """
    def envelope(audio):
        freqs, power = welch(audio[0], RATE, nperseg=4096)
        cepstrum = np.fft.irfft(np.log(power + 1e-12))
        cepstrum[30:-30] = 0
        return freqs, np.fft.rfft(cepstrum).real[: len(freqs)]

    freqs, base = envelope(before)
    _, moved = envelope(after)
    band = (freqs > 300) & (freqs < 4000)
    return max(
        np.linspace(0.7, 1.45, 151),
        key=lambda r: np.corrcoef(np.interp(freqs[band] / r, freqs, base), moved[band])[0, 1],
    )


def semitones(a: float, b: float) -> float:
    return 12 * np.log2(b / a)


def test_neutral_settings_return_the_clip_unchanged():
    clip = voiced()
    assert np.array_equal(tune_audio(clip, RATE), clip)


def test_pitch_moves_the_fundamental_by_the_requested_semitones():
    clip = voiced()
    for shift in (-5.0, 4.0):
        tuned = tune_audio(clip, RATE, pitch=shift)
        assert semitones(fundamental(clip), fundamental(tuned)) == pytest.approx(shift, abs=0.6)
        assert tuned.shape == clip.shape


def test_timbre_moves_the_envelope_but_not_the_melody():
    clip = voiced()
    lighter = tune_audio(clip, RATE, timbre=4.0)
    deeper = tune_audio(clip, RATE, timbre=-4.0)
    for tuned in (lighter, deeper):
        assert semitones(fundamental(clip), fundamental(tuned)) == pytest.approx(0.0, abs=0.6)
    assert envelope_stretch(clip, lighter) == pytest.approx(2 ** (4 / 12), rel=0.08)
    assert envelope_stretch(clip, deeper) == pytest.approx(2 ** (-4 / 12), rel=0.08)


def test_pitch_alone_keeps_the_formants():
    clip = voiced()
    tuned = tune_audio(clip, RATE, pitch=5.0)
    assert envelope_stretch(clip, tuned) == pytest.approx(1.0, rel=0.08)


def test_female_preset_combines_both_passes():
    clip = voiced()
    tuned = tune_audio(clip, RATE, pitch=5.0, timbre=3.0)
    assert semitones(fundamental(clip), fundamental(tuned)) == pytest.approx(5.0, abs=0.6)
    assert envelope_stretch(clip, tuned) == pytest.approx(2 ** (3 / 12), rel=0.08)


def test_tempo_changes_length_and_keeps_pitch():
    clip = voiced()
    slower = tune_audio(clip, RATE, tempo=0.8)
    assert slower.shape[-1] == pytest.approx(clip.shape[-1] / 0.8, rel=0.02)
    assert semitones(fundamental(clip), fundamental(slower)) == pytest.approx(0.0, abs=0.6)


def test_output_never_clips():
    loud = voiced() / 0.3 * 0.999
    assert np.max(np.abs(tune_audio(loud, RATE, timbre=6.0, pitch=12.0))) <= 0.99 + 1e-6


@pytest.mark.parametrize("kwargs", [{"pitch": 12.5}, {"timbre": -6.5}, {"tempo": 0.5}, {"tempo": 1.5}])
def test_out_of_range_values_are_refused(kwargs):
    with pytest.raises(ValueError):
        tune_audio(voiced(), RATE, **kwargs)


def wav(audio: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, audio.T, RATE, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    from api.routers import profiles
    from core import db

    voices = tmp_path / "voices"
    monkeypatch.setattr(profiles, "VOICES_DIR", str(voices))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "profiles.db"))
    db.init_db()

    async def fake_transcribe(path, language=None):
        return "auto transcript"

    monkeypatch.setattr(profiles, "_auto_transcribe_reference", fake_transcribe)
    monkeypatch.setattr(profiles.event_bus, "emit", lambda *a: None)
    app = FastAPI()
    app.include_router(profiles.router)
    client = TestClient(app)
    created = client.post(
        "/profiles",
        data={"name": "Nodira", "ref_text": "salom"},
        files={"ref_audio": ("voice.wav", wav(voiced()), "audio/wav")},
    ).json()
    return client, db, voices, created


def test_tune_route_returns_a_tuned_wav_and_stores_nothing(env):
    client, _db, voices, created = env
    before = sorted(p.name for p in voices.iterdir())

    response = client.post(
        f"/profiles/{created['id']}/tune", json={"pitch": 5, "timbre": 3, "tempo": 0.8},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "audio/wav"
    audio, rate = sf.read(io.BytesIO(response.content), dtype="float32", always_2d=True)
    assert rate == RATE
    assert audio.shape[0] == pytest.approx(2.0 * RATE / 0.8, rel=0.02)
    assert semitones(fundamental(voiced()), fundamental(audio.T)) == pytest.approx(5.0, abs=0.6)
    assert sorted(p.name for p in voices.iterdir()) == before
    assert client.get(f"/profiles/{created['id']}").json()["ref_audio_path"] == created["ref_audio_path"]


def test_tune_route_validates_ranges(env):
    client, _db, _voices, created = env
    for body in ({"pitch": 13}, {"timbre": 7}, {"tempo": 2}):
        assert client.post(f"/profiles/{created['id']}/tune", json=body).status_code == 422


def test_tune_route_refuses_unknown_and_designed_voices(env):
    client, db, _voices, created = env
    assert client.post("/profiles/deadbeef/tune", json={}).status_code == 404
    with db.db_conn() as conn:
        conn.execute("UPDATE voice_profiles SET kind='design' WHERE id=?", (created["id"],))
    response = client.post(f"/profiles/{created['id']}/tune", json={"pitch": 2})
    assert response.status_code == 409
    assert "Voice Design" in response.json()["detail"]
