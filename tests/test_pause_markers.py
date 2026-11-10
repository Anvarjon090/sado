"""Inline `[pause Nms]` transcript marker (issue #276).

Covers the pure text parser (`parse_pause_markers`) and the model-free audio
stitching (`_render_with_pauses`) — no TTS model is loaded; `gen_span` is a
fake that returns known-length tensors so the silence math is deterministic.
"""
import pytest
import torch

from omnivoice.utils.text import (
    parse_pause_markers,
    PAUSE_DEFAULT_MS,
    PAUSE_MAX_MS,
)
from api.routers.generation import _render_with_pauses


# ── parser ────────────────────────────────────────────────────────────────

def test_no_marker_returns_text_unchanged():
    assert parse_pause_markers("Hello world") == [("Hello world", 0)]
    assert parse_pause_markers("") == [("", 0)]


def test_bare_pause_uses_default():
    assert parse_pause_markers("a[pause]b") == [("a", PAUSE_DEFAULT_MS), ("b", 0)]


def test_explicit_ms_and_seconds():
    assert parse_pause_markers("a [pause 500ms] b") == [("a ", 500), (" b", 0)]
    assert parse_pause_markers("a[pause 1s]b") == [("a", 1000), ("b", 0)]
    assert parse_pause_markers("a[pause 1.5s]b") == [("a", 1500), ("b", 0)]


def test_bare_number_is_milliseconds():
    assert parse_pause_markers("a[pause 250]b") == [("a", 250), ("b", 0)]


def test_case_insensitive_and_inner_whitespace():
    assert parse_pause_markers("a[PAUSE  750 ms]b") == [("a", 750), ("b", 0)]


def test_leading_marker_yields_empty_first_span():
    assert parse_pause_markers("[pause 1s]Hi") == [("", 1000), ("Hi", 0)]


def test_trailing_marker():
    assert parse_pause_markers("Bye[pause]") == [("Bye", PAUSE_DEFAULT_MS)]


def test_adjacent_markers_sum():
    assert parse_pause_markers("a[pause][pause 2s]b") == [
        ("a", PAUSE_DEFAULT_MS + 2000),
        ("b", 0),
    ]


def test_duration_clamped():
    assert parse_pause_markers("a[pause 99s]b") == [("a", PAUSE_MAX_MS), ("b", 0)]


def test_text_round_trips_without_markers():
    text = "One [pause 200ms] two [pause] three"
    spans = "".join(t for t, _ in parse_pause_markers(text))
    assert spans == "One  two  three"


# ── audio stitching ─────────────────────────────────────────────────────────

def _fake_gen(sr):
    # Each span renders to 1 second of mono audio (shape [1, sr]); the value
    # encodes nothing — we only assert lengths.
    return lambda text: torch.ones(1, sr)


def test_render_inserts_silence_between_spans():
    sr = 1000  # 1000 samples/sec keeps the math trivial
    segs = [("hello", 500), ("world", 0)]  # 500ms = 500 samples of silence
    out = _render_with_pauses(_fake_gen(sr), segs, sr)
    # 1s audio + 0.5s silence + 1s audio = 2.5s = 2500 samples
    assert out.shape == (1, 2500)
    # The middle 500 samples (after the first second) are silence.
    assert torch.all(out[:, sr:sr + 500] == 0)
    assert torch.all(out[:, :sr] == 1)


def test_render_leading_silence():
    sr = 1000
    segs = [("", 1000), ("hi", 0)]  # 1s leading silence + 1s audio
    out = _render_with_pauses(_fake_gen(sr), segs, sr)
    assert out.shape == (1, 2000)
    assert torch.all(out[:, :1000] == 0)
    assert torch.all(out[:, 1000:] == 1)


def test_render_pause_only_input_is_silence():
    sr = 1000
    segs = [("", 750)]  # only a pause, no speakable text
    out = _render_with_pauses(_fake_gen(sr), segs, sr)
    assert out.numel() == 750
    assert torch.all(out == 0)


def test_render_no_pause_single_span_passthrough():
    sr = 1000
    segs = [("just text", 0)]
    out = _render_with_pauses(_fake_gen(sr), segs, sr)
    assert out.shape == (1, sr)


# ── engine padding vs the pause the listener hears ─────────────────────────


def _padded_gen(sr, pad_ms=200, tone_ms=500):
    """Engine-like spans: ~200 ms of silence on each side of the speech."""
    pad = torch.zeros(1, sr * pad_ms // 1000)
    t = torch.arange(sr * tone_ms // 1000) / sr
    tone = (0.3 * torch.sin(2 * torch.pi * 220 * t)).unsqueeze(0)
    return lambda *_: torch.cat([pad, tone, pad], dim=-1)


def _gaps(out, sr):
    loud = torch.nonzero(out.abs().flatten() > 0.01).flatten()
    cuts = torch.nonzero(loud[1:] - loud[:-1] > sr // 100).flatten()
    return [float((loud[c + 1] - loud[c]) / sr) for c in cuts]


def test_requested_pause_is_the_gap_heard_not_pause_plus_engine_padding():
    sr = 24_000
    out = _render_with_pauses(_padded_gen(sr), [("a", 500), ("b", 0), ("c", 0)], sr)
    gaps = _gaps(out, sr)
    assert gaps[0] == pytest.approx(0.5, abs=0.015)  # <break time="500ms"/>, not 0.9 s
    # No pause asked for: spans part like words (two kept 40 ms edges), not by 400 ms.
    assert gaps[1] == pytest.approx(0.08, abs=0.015)
    # The trim keeps the speech itself intact: three tones' worth of loud samples remain.
    tone_loud = int((_padded_gen(sr)().abs() > 0.01).sum())
    assert int((out.abs() > 0.01).sum()) == pytest.approx(3 * tone_loud, abs=sr // 100)


def test_leading_and_trailing_pauses_stay_exact_with_padded_spans():
    sr = 24_000
    out = _render_with_pauses(_padded_gen(sr), [("", 1000), ("a", 300)], sr)
    loud = torch.nonzero(out.abs().flatten() > 0.01).flatten()
    assert float(loud[0]) / sr == pytest.approx(1.0, abs=0.015)
    assert float(out.shape[-1] - 1 - loud[-1]) / sr == pytest.approx(0.3, abs=0.015)
