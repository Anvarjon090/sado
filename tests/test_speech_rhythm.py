"""services.speech_rhythm: pause sites of a text, and the pauses and pace of a take.

The measurements behind "it breaks" and "it rushes" (2026-11-12): a paragraph
rendered in one 29 s shot paused at eleven places for five punctuation marks,
and mid-length takes ran a syllable rate 15-40 % higher in their last third.
"""
from __future__ import annotations

import numpy as np
import pytest
from services import speech_rhythm as sr_mod

SR = 24_000


def _room(seconds: float, seed: int = 9) -> np.ndarray:
    return (np.random.default_rng(seed).standard_normal(int(seconds * SR)) * 1e-4).astype(np.float32)


def _syllables(seconds: float, rate_at, seed: int = 1) -> np.ndarray:
    """Noise whose level peaks once per syllable; ``rate_at(t)`` is the syllable
    rate (per second) at time ``t``. Dips stay 10 dB under the peaks, like the
    consonants between vowels, so the whole stretch is speech."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    phase = np.cumsum(np.vectorize(rate_at)(t)) / SR
    envelope = 0.3 + 0.7 * np.abs(np.sin(np.pi * phase))
    return (np.random.default_rng(seed).standard_normal(n) * 0.2 * envelope).astype(np.float32)


def _take(*parts) -> np.ndarray:
    """Speech stretches (arrays) and pauses (seconds of room tone), in order,
    with a quiet lead-in and tail as an engine leaves them."""
    pieces = [_room(0.3)]
    for index, part in enumerate(parts):
        pieces.append(_room(part, seed=20 + index) if isinstance(part, (int, float)) else part)
    pieces.append(_room(0.3, seed=7))
    return np.concatenate(pieces)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Salom dunyo", (0, 0)),
        ("Salom, dunyo. Yaxshimisiz?", (1, 1)),
        ("Birinchi. Ikkinchi! Uchinchi?", (2, 0)),
        # A decimal point and a clock colon are not pauses; the final mark has nothing after it.
        ("Narxi 3.5 so'm, soat 14:30 da.", (0, 1)),
        ("Voy... rostdanmi?! Ha — albatta.", (2, 1)),
        ("[pause 300ms] Salom. [laugh] Xayr.", (1, 0)),
        ("", (0, 0)),
        (None, (0, 0)),
    ],
)
def test_pause_sites_are_the_marks_a_reader_pauses_at(text, expected):
    assert sr_mod.pause_site_counts(text) == expected


def test_pause_sites_are_counted_span_by_span():
    # The silence between spans is stitched in by the renderer: the full stop
    # that ends a paragraph is not a pause the engine places.
    assert sr_mod.pause_site_counts(["Birinchi xatboshi.", "Ikkinchi, uchinchi."]) == (0, 1)
    assert sr_mod.pause_site_counts("Birinchi xatboshi. Ikkinchi, uchinchi.") == (1, 1)


def test_inner_silences_and_breaks_are_measured_against_the_text():
    steady = lambda t: 5.0
    take = _take(_syllables(1.5, steady), 0.45, _syllables(1.5, steady, seed=2), 0.25,
                 _syllables(1.5, steady, seed=3), 0.22, _syllables(1.5, steady, seed=4))
    silences = sr_mod.inner_silences(take, SR)
    assert len(silences) == 3
    assert [end - start for start, end in silences] == pytest.approx([0.45, 0.25, 0.22], abs=0.06)

    # One sentence end in the text: three breaks, two of them unasked for.
    measured = sr_mod.rhythm(take, SR, "Bir gap tugadi. Ikkinchi gap esa hech qayerda to'xtamaydi")
    assert (measured.breaks, measured.sentence_sites, measured.clause_sites) == (3, 1, 0)
    assert measured.extra_breaks == 2 and measured.long_pauses == 0

    # With a comma and a second full stop every pause has a site.
    covered = sr_mod.rhythm(take, SR, "Bir gap. Ikkinchi gap, uchinchi qism. To'rtinchi")
    assert covered.extra_breaks == 0


def test_tempo_drift_follows_the_syllable_rate():
    steady = sr_mod.rhythm(_take(_syllables(8.0, lambda t: 5.0)), SR)
    assert steady.syllable_rate == pytest.approx(5.0, abs=0.6)
    assert abs(steady.tempo_drift_pct) < 15

    # 4 syllables a second rising to 7: the last third is far faster than the first.
    rushing = sr_mod.rhythm(_take(_syllables(8.0, lambda t: 4.0 + 3.0 * t / 8.0)), SR)
    assert rushing.tempo_drift_pct > 30
    assert rushing.tempo_spread_pct > steady.tempo_spread_pct


def test_short_takes_have_no_tempo_estimate():
    short = sr_mod.rhythm(_take(_syllables(1.5, lambda t: 5.0)), SR, "Salom!")
    assert short.syllable_rate is None and short.tempo_drift_pct is None
    assert short.to_dict()["pauses"] == 0
