"""SSML (services/ssml.py) and its wiring into /generate.

The parser is pinned on the subset the docs promise; the route tests use the
fake engine to prove each span reaches the engine with its own speed and
language, that <break> becomes silence of the right length, that <voice>
switches the reference, and that unsupported markup comes back as a warning
header instead of vanishing.
"""
from __future__ import annotations

import io
import json
import os

os.environ.setdefault("OMNIVOICE_MODEL", "test")
os.environ.setdefault("OMNIVOICE_DISABLE_FILE_LOG", "1")

import importlib

import numpy as np
import pytest
import torch

from services import ssml
from services.chunked_tts import PARAGRAPH_PAUSE_MS

SR = 24_000


# ── parser ─────────────────────────────────────────────────────────────────


def test_detects_ssml_only_by_its_root():
    assert ssml.is_ssml("<speak>Salom</speak>")
    assert ssml.is_ssml("  <SPEAK version='1.1' xmlns='http://www.w3.org/2001/10/synthesis'>x</SPEAK>")
    assert ssml.is_ssml("<?xml version='1.0'?><speak>x</speak>")
    assert not ssml.is_ssml("Salom <b>dunyo</b>")
    assert not ssml.is_ssml("")


def test_breaks_paragraphs_and_sentences_become_pauses_and_punctuation():
    doc = ssml.parse_ssml(
        "<speak><p><s>Birinchi gap</s><s>Ikkinchi gap.</s></p>"
        "Keyingi xatboshi<break time='1.5s'/>va davomi<break strength='weak'/><break/>oxiri</speak>"
    )
    assert [(s.text, s.pause_ms) for s in doc.spans] == [
        ("Birinchi gap. Ikkinchi gap.", PARAGRAPH_PAUSE_MS),
        ("Keyingi xatboshi", 1500),
        ("va davomi", 200 + 350),
        ("oxiri", 0),
    ]
    assert doc.warnings == []
    assert ssml.parse_break_ms("250ms", None) == 250
    assert ssml.parse_break_ms(None, "x-strong") == 1000
    assert ssml.parse_break_ms("999s", None) == 10_000  # clamped to the pause ceiling


def test_prosody_rate_volume_and_emphasis_change_the_delivery_only():
    doc = ssml.parse_ssml(
        "<speak>Oddiy <prosody rate='slow' volume='+3dB'>sekin va balandroq</prosody>"
        " <prosody rate='120%' volume='soft'>tez va past</prosody>"
        " <prosody rate='+10%'><prosody rate='+10%'>ikki marta tezroq</prosody></prosody>"
        " <emphasis>muhim</emphasis> <emphasis level='none'>oddiy</emphasis></speak>"
    )
    deliveries = [(s.text, s.delivery.speed, s.delivery.gain_db) for s in doc.spans]
    assert deliveries[0] == ("Oddiy", 1.0, 0.0)
    assert deliveries[1] == ("sekin va balandroq", 0.8, 3.0)
    assert deliveries[2] == ("tez va past", 1.2, -6.0)
    assert deliveries[3][1] == pytest.approx(1.21)
    assert deliveries[4] == ("muhim", pytest.approx(0.92), 1.5)
    assert deliveries[5] == ("oddiy", 1.0, 0.0)
    assert ssml.parse_rate("x-fast", 1.0) == 1.5 and ssml.parse_rate("9", 1.0) == 2.0  # clamped
    assert ssml.parse_volume_db("50%", 0.0) == pytest.approx(-6.02, abs=0.01)
    assert ssml.parse_volume_db("-50dB", 0.0) == -40.0


def test_unsupported_markup_is_spoken_plainly_and_reported():
    doc = ssml.parse_ssml(
        "<speak><prosody pitch='+2st'>baland</prosody> <phoneme alphabet='ipa' ph='sa.lom'>salom</phoneme>"
        " <audio src='x.mp3'>zaxira matn</audio> <mark name='m1'/> <foo>noma'lum</foo></speak>"
    )
    assert doc.plain_text() == "baland salom zaxira matn noma'lum"
    joined = " | ".join(doc.warnings)
    for needle in ("prosody pitch", "<phoneme>", "<audio>", "<mark>", "<foo>"):
        assert needle in joined
    assert len(doc.warnings) == 5


def test_say_as_sub_lang_and_voice():
    doc = ssml.parse_ssml(
        "<speak xmlns='http://www.w3.org/2001/10/synthesis'>"
        "<say-as interpret-as='characters'>UZB 12</say-as> <sub alias='Toshkent'>TSH</sub>"
        " <lang xml:lang='ru-RU'>Привет</lang> <voice name='Aisha'>Salom</voice></speak>"
    )
    spans = doc.spans
    assert spans[0].text == "U Z B 1 2 Toshkent"
    assert spans[1].text == "Привет" and spans[1].delivery.language == "ru"
    assert spans[2].text == "Salom" and spans[2].delivery.voice == "Aisha"
    assert doc.voices() == ["Aisha"]
    assert spans[0].to_wire() == {"text": "U Z B 1 2 Toshkent", "pause_ms": 0, "speed_factor": 1.0,
                                  "gain_db": 0.0, "language": None, "voice": None}


def test_rejects_declarations_malformed_xml_and_silence():
    with pytest.raises(ssml.SsmlError, match="DOCTYPE"):
        ssml.parse_ssml("<!DOCTYPE speak [<!ENTITY a 'b'>]><speak>&a;</speak>")
    with pytest.raises(ssml.SsmlError, match="parsed"):
        ssml.parse_ssml("<speak><p>ochiq</speak>")
    with pytest.raises(ssml.SsmlError, match="root"):
        ssml.parse_ssml("<p>yo'q</p>")
    with pytest.raises(ssml.SsmlError, match="no text"):
        ssml.parse_ssml("<speak><break time='1s'/></speak>")


# ── /generate wiring ───────────────────────────────────────────────────────


def _tts_mod():
    return importlib.import_module("services.tts_backend")


def _fake_engine():
    class _FakeEngine(_tts_mod().TTSBackend):
        id = "fake-ssml"
        display_name = "Fake Engine (ssml tests)"
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
            return torch.full((1, SR), 0.25)  # one second of a flat tone-like block

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
    c = TestClient(app, client=("127.0.0.1", 50000))
    c.fake = fake
    return c


def _audio(res) -> np.ndarray:
    import soundfile as sf

    data, sr = sf.read(io.BytesIO(res.content), dtype="float32")
    assert sr == SR
    return data


def test_generate_renders_ssml_spans_with_their_own_delivery(client):
    client.fake.calls.clear()
    res = client.post("/generate", data={
        "text": "<speak>Salom<break time='500ms'/><prosody rate='slow' volume='-6dB'>sekin</prosody>"
                " <lang xml:lang='ru'>Привет</lang></speak>",
        "engine": "fake-ssml", "effect_preset": "raw", "language": "Uzbek", "speed": "1.0",
    })
    assert res.status_code == 200, res.text
    calls = client.fake.calls
    assert [c[0] for c in calls] == ["Salom", "sekin", "Привет"]
    assert calls[0][1]["speed"] == 1.0 and calls[1][1]["speed"] == 0.8
    assert calls[1][1]["language"] == "Uzbek" and calls[2][1]["language"] == "ru"
    audio = _audio(res)
    # three one-second spans + 500 ms of stitched silence; the quiet span is −6 dB.
    assert len(audio) == 3 * SR + SR // 2
    assert audio[:SR].max() == pytest.approx(0.25, abs=0.01)  # the provenance mark adds a hair
    assert abs(audio[SR:SR + SR // 2]).max() < 0.01  # stitched silence (the provenance mark rides on it)
    assert audio[SR + SR // 2: 2 * SR + SR // 2].max() == pytest.approx(0.25 * 10 ** (-6 / 20), abs=0.01)
    assert "X-SSML-Warnings" not in res.headers


def test_generate_reports_unsupported_ssml_and_rejects_bad_documents(client):
    res = client.post("/generate", data={
        "text": "<speak><prosody pitch='high'>baland</prosody><phoneme ph='x'>y</phoneme></speak>",
        "engine": "fake-ssml", "effect_preset": "raw",
    })
    assert res.status_code == 200, res.text
    warnings = json.loads(res.headers["X-SSML-Warnings"])
    assert any("pitch" in w for w in warnings) and any("phoneme" in w for w in warnings)

    res = client.post("/generate", data={"text": "<speak><p>ochiq</speak>", "engine": "fake-ssml"})
    assert res.status_code == 400 and "parsed" in res.json()["detail"]
    res = client.post("/generate", data={"text": "<!DOCTYPE x><speak>a</speak>", "engine": "fake-ssml"})
    assert res.status_code == 400


def test_generate_switches_voice_per_span(client, tmp_path, monkeypatch):
    """<voice name> picks a saved voice by name; an unknown name warns and keeps the request's voice."""
    import soundfile as sf

    import api.routers.generation as gen_mod
    from core.db import db_conn

    voices = tmp_path / "voices"
    voices.mkdir()
    ref = voices / "aisha.wav"
    sf.write(ref, np.zeros(SR, dtype=np.float32), SR, subtype="PCM_16")
    monkeypatch.setattr(gen_mod, "VOICES_DIR", str(voices))
    with db_conn() as conn:
        conn.execute("DELETE FROM voice_profiles WHERE id='ssmlaisha'")
        conn.execute(
            "INSERT INTO voice_profiles (id, name, ref_audio_path, ref_text, kind, language, created_at) "
            "VALUES ('ssmlaisha', 'Aisha SSML', 'aisha.wav', 'salom', 'clone', 'Uzbek', 0)"
        )
    client.fake.calls.clear()
    res = client.post("/generate", data={
        "text": "<speak>Men <voice name='aisha ssml'>u</voice> <voice name='yoq'>siz</voice></speak>",
        "engine": "fake-ssml", "effect_preset": "raw",
    })
    assert res.status_code == 200, res.text
    calls = client.fake.calls
    assert [c[0] for c in calls] == ["Men", "u", "siz"]
    assert calls[0][1].get("ref_audio") is None
    assert calls[1][1]["ref_audio"] == str(ref) and calls[1][1]["ref_text"] == "salom"
    assert calls[2][1].get("ref_audio") is None
    assert any("yoq" in w for w in json.loads(res.headers["X-SSML-Warnings"]))
