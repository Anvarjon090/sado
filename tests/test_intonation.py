"""Word-by-word intonation editing of a finished take."""

import io

import numpy as np
import pytest
import soundfile as sf
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services import intonation
from services.intonation import (
    apply_word_pitch,
    pitch_curve,
    script_words,
    spans_from_asr,
    syllable_count,
)

RATE = 24000


def tone(f0: float, seconds: float) -> np.ndarray:
    t = np.arange(int(RATE * seconds)) / RATE
    wave = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 12))
    return (0.3 * wave / np.max(np.abs(wave))).astype(np.float32)


def fundamental(x: np.ndarray) -> float:
    x = x - x.mean()
    corr = np.correlate(x, x, mode="full")[len(x) - 1:]
    low, high = RATE // 500, RATE // 60
    return RATE / (low + int(np.argmax(corr[low:high])))


def semitones(a: float, b: float) -> float:
    return 12 * np.log2(b / a)


def test_script_words_drop_tags_and_bare_punctuation():
    assert script_words("Salom, [laughter] bugun — havo yaxshi!") == [
        "Salom,", "bugun", "havo", "yaxshi!",
    ]


@pytest.mark.parametrize(
    ("word", "count"),
    [("bugun", 2), ("Assalomu", 4), ("o'rinni", 3), ("yaxshi!", 2), ("salom", 2), ("Привет", 2)],
)
def test_syllables_are_vowel_groups(word, count):
    assert syllable_count(word) == count


def heard(*items):
    return [{"word": w, "start": s, "end": e} for w, s, e in items]


def test_asr_words_time_the_script_words_even_when_spelt_differently():
    spans = spans_from_asr(
        "Assalomu alaykum! Bugun yoki-da ertaga.",
        heard(("Assalomu", 0.10, 0.60), ("alaytum", 0.62, 1.10), ("Bugun", 1.40, 1.80),
              ("yoki", 1.85, 2.05), ("da", 2.05, 2.20), ("ertaga.", 2.25, 2.80)),
        3.0,
    )
    assert [s.text for s in spans] == ["Assalomu", "alaykum!", "Bugun", "yoki-da", "ertaga."]
    # Contiguous, ordered, and each word sits on the time the ASR heard it.
    for left, right in zip(spans, spans[1:]):
        assert left.end == pytest.approx(right.start)
        assert left.start < left.end
    assert spans[2].start == pytest.approx(1.25) and spans[2].end == pytest.approx(1.825)
    assert spans[3].start < 1.85 < 2.20 < spans[3].end + 0.03


def test_words_the_asr_missed_share_the_gap_between_neighbours():
    spans = spans_from_asr(
        "bir ikki uch to'rt",
        heard(("bir", 0.0, 0.4), ("to'rt", 1.6, 2.0)),
        2.0,
    )
    assert [s.text for s in spans] == ["bir", "ikki", "uch", "to'rt"]
    assert spans[0].end < spans[1].end < spans[2].end < spans[3].end
    assert spans[1].start == pytest.approx(0.4, abs=0.01)
    assert spans[2].end == pytest.approx(1.6, abs=0.01)


def test_pitch_curve_holds_each_offset_and_glides_between_them():
    curve = pitch_curve(RATE * 2, RATE, [(0.0, 1.0, 4.0), (1.0, 2.0, -2.0)])
    assert curve[int(0.5 * RATE)] == pytest.approx(4.0)
    assert curve[int(1.5 * RATE)] == pytest.approx(-2.0)
    middle = curve[int(0.99 * RATE):int(1.01 * RATE)]
    assert middle.max() < 4.0 and middle.min() > -2.0


def test_only_the_edited_word_moves():
    first, second = tone(150.0, 1.0), tone(150.0, 1.0)
    take = np.concatenate([first, second])
    edited = apply_word_pitch(take, RATE, [(0.0, 1.0, 0.0), (1.0, 2.0, 5.0)])
    assert edited.shape == (1, take.size)
    kept = edited[0, int(0.3 * RATE):int(0.7 * RATE)]
    raised = edited[0, int(1.3 * RATE):int(1.7 * RATE)]
    assert semitones(150.0, fundamental(kept)) == pytest.approx(0.0, abs=0.6)
    assert semitones(150.0, fundamental(raised)) == pytest.approx(5.0, abs=0.6)


def test_no_edits_returns_the_take_unchanged():
    take = tone(150.0, 0.5)
    assert np.array_equal(apply_word_pitch(take, RATE, [(0.0, 0.5, 0.0)])[0], take)


@pytest.mark.parametrize("edit", [(0.0, 1.0, 13.0), (1.0, 0.5, 2.0)])
def test_bad_edits_are_refused(edit):
    with pytest.raises(ValueError):
        apply_word_pitch(tone(150.0, 1.0), RATE, [edit])


@pytest.fixture
def env(tmp_path, monkeypatch):
    from api.routers import generation, intonation as route
    from core import db
    from services import asr_backend, watermark

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setattr(generation, "OUTPUTS_DIR", str(outputs))
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "history.db"))
    db.init_db()

    async def keep(waveform, sample_rate, **_):
        return waveform

    monkeypatch.setattr(watermark, "mark_synthetic_async", keep)
    asr = {"words": heard(("salom", 0.25, 1.15), ("dunyo", 1.25, 2.15))}
    monkeypatch.setattr(asr_backend, "transcribe_words", lambda path, language=None: asr["words"])
    monkeypatch.setattr(route.event_bus, "emit", lambda *a, **k: None)
    quiet = np.zeros(int(0.2 * RATE), dtype=np.float32)
    take = np.concatenate([quiet, tone(150.0, 1.0), tone(150.0, 1.0), quiet])
    sf.write(outputs / "abcd1234.wav", take, RATE)
    with db.db_conn() as conn:
        conn.execute(
            "INSERT INTO generation_history (id, text, mode, language, instruct, profile_id, "
            "audio_path, duration_seconds, generation_time, seed, design_recipe, created_at) "
            "VALUES ('abcd1234','salom dunyo','clone','Uzbek','',NULL,'abcd1234.wav',2.0,1.0,7,NULL,1.0)"
        )
    app = FastAPI()
    app.include_router(route.router)
    return TestClient(app), outputs, db, asr


def test_words_route_times_the_script_with_the_local_asr(env):
    client, _outputs, _db, _asr = env
    body = client.post("/audio/abcd1234/words", json={"text": "Salom, dunyo!", "language": "Uzbek"}).json()
    assert body["approximate"] is False
    assert [w["text"] for w in body["words"]] == ["Salom,", "dunyo!"]
    assert body["words"][0]["end"] == pytest.approx(1.2, abs=0.01)


def test_words_route_estimates_when_no_asr_model_is_installed(env):
    client, _outputs, _db, asr = env
    asr["words"] = None
    body = client.post("/audio/abcd1234/words", json={"text": "salom dunyo"}).json()
    assert body["approximate"] is True
    assert [w["text"] for w in body["words"]] == ["salom", "dunyo"]


def test_preview_returns_the_edited_take_and_stores_nothing(env):
    client, outputs, _db, _asr = env
    response = client.post(
        "/audio/abcd1234/intonation",
        json={"edits": [{"start": 1.2, "end": 2.2, "semitones": 4}]},
    )
    assert response.status_code == 200, response.text
    audio, rate = sf.read(io.BytesIO(response.content), dtype="float32")
    assert rate == RATE and audio.size == int(2.4 * RATE)
    assert semitones(150.0, fundamental(audio[int(1.5 * RATE):int(1.9 * RATE)])) == pytest.approx(4.0, abs=0.6)
    assert semitones(150.0, fundamental(audio[int(0.5 * RATE):int(0.9 * RATE)])) == pytest.approx(0.0, abs=0.6)
    assert sorted(p.name for p in outputs.iterdir()) == ["abcd1234.wav"]


def test_save_adds_a_new_take_and_keeps_the_original(env):
    client, outputs, db, _asr = env
    original = (outputs / "abcd1234.wav").read_bytes()
    body = client.post(
        "/audio/abcd1234/intonation",
        json={"edits": [{"start": 0.0, "end": 1.0, "semitones": -3}], "save": True},
    ).json()
    assert body["audio_path"] == f"{body['id']}.wav"
    assert (outputs / body["audio_path"]).is_file()
    assert (outputs / "abcd1234.wav").read_bytes() == original
    with db.db_conn() as conn:
        row = conn.execute("SELECT * FROM generation_history WHERE id=?", (body["id"],)).fetchone()
    assert row["text"] == "salom dunyo" and row["language"] == "Uzbek" and row["seed"] == 7


def test_intonation_route_refuses_bad_requests(env):
    client, _outputs, _db, _asr = env
    edit = {"start": 0.0, "end": 1.0, "semitones": 2}
    assert client.post("/audio/../intonation", json={"edits": [edit]}).status_code == 404
    assert client.post("/audio/ffffffff/intonation", json={"edits": [edit]}).status_code == 404
    flat = {"edits": [{"start": 0.0, "end": 1.0, "semitones": 0}]}
    assert client.post("/audio/abcd1234/intonation", json=flat).status_code == 422
    too_far = {"edits": [{"start": 0.0, "end": 1.0, "semitones": 20}]}
    assert client.post("/audio/abcd1234/intonation", json=too_far).status_code == 422
    backwards = {"edits": [{"start": 1.0, "end": 0.5, "semitones": 2}]}
    assert client.post("/audio/abcd1234/intonation", json=backwards).status_code == 422


class FakeASR:
    def __init__(self, id_, words, calls):
        self.id, self._words, self._calls = id_, words, calls

    def transcribe(self, audio_path, *, word_timestamps=True, language=None):
        self._calls.append((self.id, language))
        return {"segments": [{"words": self._words}]}


@pytest.fixture
def asr(monkeypatch):
    from services import asr_backend

    calls, loads = [], []
    asr_backend._NO_WORD_TIMES.clear()
    timed = [{"word": "salom", "start": 0.1, "end": 0.5}]
    engines = {"capture": FakeASR("faster-whisper", timed, calls), "offline": FakeASR("whisperx", [], calls)}
    monkeypatch.setattr(asr_backend, "active_backend_id", lambda: "whisperx")
    monkeypatch.setattr(asr_backend, "asr_model_missing_error", lambda **_: None)
    monkeypatch.setattr(asr_backend, "get_capture_asr_backend", lambda: engines["capture"])

    def load(**_):
        loads.append("whisperx")
        return engines["offline"]

    monkeypatch.setattr(asr_backend, "load_active_asr_backend", load)
    monkeypatch.setattr(asr_backend, "_installed_reference_fallbacks", lambda tried: [])
    yield asr_backend, engines, calls, loads
    asr_backend._NO_WORD_TIMES.clear()


def test_word_times_come_from_the_dictation_engine_first(asr):
    asr_backend, _engines, calls, loads = asr
    words = asr_backend.transcribe_words("take.wav", language="Uzbek")
    assert words == [{"word": "salom", "start": 0.1, "end": 0.5}]
    assert calls == [("faster-whisper", "uz")] and loads == []


def test_an_engine_without_word_times_is_skipped_next_time(asr):
    asr_backend, engines, calls, loads = asr
    engines["capture"]._words = []
    engines["offline"]._words = []
    assert asr_backend.transcribe_words("take.wav", language="Uzbek") is None
    assert loads == ["whisperx"]
    calls.clear()
    assert asr_backend.transcribe_words("take.wav", language="Uzbek") is None
    # Neither engine is asked again for Uzbek, and WhisperX is not even loaded.
    assert calls == [] and loads == ["whisperx"]


def test_a_remote_recogniser_never_receives_the_take(asr, monkeypatch):
    asr_backend, engines, calls, loads = asr
    engines["capture"].id = "openai-compat-asr"
    monkeypatch.setattr(asr_backend, "active_backend_id", lambda: "openai-compat-asr")
    assert asr_backend.transcribe_words("take.wav", language="Uzbek") is None
    assert calls == [] and loads == []
