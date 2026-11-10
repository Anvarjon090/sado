"""scripts/voice_casting.py — the parts that need no engine: the slot sheet,
the transparent ranking, and the listening page."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def casting():
    spec = importlib.util.spec_from_file_location("voice_casting", ROOT / "scripts" / "voice_casting.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sixteen_slots_cover_eight_ages_for_both_sexes(casting):
    slots = casting.SLOTS
    assert len(slots) == 16
    assert len({s["id"] for s in slots}) == 16
    assert sorted({s["age"] for s in slots}) == [5, 15, 20, 30, 40, 50, 60, 70]
    for age in (5, 15, 20, 30, 40, 50, 60, 70):
        assert {s["sex"] for s in slots if s["age"] == age} == {"erkak", "ayol"}
    for slot in slots:
        lo, hi = slot["f0"]
        assert 60 < lo < hi < 400
        assert slot["tags"] and all(("male" in t or "female" in t) for t in slot["tags"])
        # Men below 30 are not asked for a "moderate" pitch: on this engine that is a teenager.
        if slot["sex"] == "erkak" and 20 <= slot["age"]:
            assert "moderate pitch" not in slot["tags"][0]


def test_f0_penalty_is_zero_inside_the_range_and_grows_in_semitones(casting):
    assert casting.f0_penalty(120.0, 105, 140) == 0.0
    assert casting.f0_penalty(None, 105, 140) == 12.0
    assert casting.f0_penalty(70.0, 105, 140) == pytest.approx(7.02, abs=0.05)  # an octave-ish below
    assert casting.f0_penalty(280.0, 105, 140) == pytest.approx(12.0, abs=0.05)


def test_score_prefers_smooth_in_range_intelligible_voices(casting):
    slot = {"f0": (190, 245)}
    soft = {"f0_median_hz": 225, "hnr_db": 14.0, "cpp_db": 1.6, "presence_db": -22.0, "lra_lu": 1.5}
    harsh = {"f0_median_hz": 225, "hnr_db": 8.0, "cpp_db": 1.0, "presence_db": -10.0, "lra_lu": 1.5}
    wrong_sex = {**soft, "f0_median_hz": 130}
    garbled = soft
    s_soft, terms = casting.score(soft, slot, 0.0)
    assert s_soft > casting.score(harsh, slot, 0.0)[0]
    assert s_soft > casting.score(wrong_sex, slot, 0.0)[0] + 15  # effectively disqualified
    assert s_soft > casting.score(garbled, slot, 0.3)[0]
    assert set(terms) == {"f0", "hnr", "cpp", "presence", "lra", "cer"}


def test_listening_page_lists_every_cast_voice(casting, tmp_path):
    slots = {}
    for s in casting.SLOTS:
        clip = tmp_path / "audition" / s["id"] / "v0_s7.wav"
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_bytes(b"RIFF")
        cand = {"stem": "v0_s7", "instruct": s["tags"][0], "seed": 7, "file": str(clip), "raw": str(clip),
                "metrics": {"f0_median_hz": 200, "hnr_db": 12, "cpp_db": 1.5, "presence_db": -20}, "score": 30.0,
                "cer": 0.0, "transcript": "x", "terms": {}}
        slots[s["id"]] = {**s, "candidates": [cand], "pick": "v0_s7"}
    casting_doc = {"model": "test", "settings": {"steps": 32, "cfg": 3.0, "pause_scale": 1.6}, "slots": slots}
    report = {"voices": {sid: {"config": {}, "cases": [{"case": "salom", "raw": str(tmp_path / "r.wav"),
                                                       "natural": str(tmp_path / "n.wav")}]} for sid in slots}}
    casting.write_listening_page(tmp_path, casting_doc, report)
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert page.count("<audio") == 16 * 3  # audition + one case (natural, raw) per voice
    for age in (5, 15, 20, 30, 40, 50, 60, 70):
        assert f"<h2>{age} yosh</h2>" in page
    assert "audition/05_erkak/v0_s7.wav" in page  # relative, so the folder can move
    json.dumps(casting_doc)  # the casting file stays plain JSON
