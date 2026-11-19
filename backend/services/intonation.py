"""Word-by-word intonation editing of a finished take.

The user raises or lowers the melody of single words ("make *bugun* higher,
drop *yaxshi* at the end") after a take is rendered, without re-generating it.
Two model-free steps make that possible:

* :func:`spans_from_asr` places the script's words on the take's timeline
  from the installed local ASR's word timings (``asr_backend.transcribe_words``),
  matched to the script word by word, so the editor shows the words the user
  wrote even where the recogniser spelled them differently. Measured against
  pauses on 14 Uzbek takes, those boundaries fell inside the pause 24 times
  out of 25 (median 35 ms off its centre).
* :func:`word_spans` is the fallback when no ASR model is installed: each
  word's syllable count (its vowel groups) is matched to the syllable nuclei
  in the audio. It is model-free but rough (median ~90 ms, worst cases a whole
  syllable off), so the API marks those spans ``approximate``.
* :func:`apply_word_pitch` turns per-word semitone offsets into a smooth
  pitch curve and renders it with Rubber Band (pedalboard) keeping the
  formants, so a raised word keeps the speaker's timbre and the take keeps its
  length and timing.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

import numpy as np

from services.speech_metrics import frame_levels, speech_mask, to_mono
from services.speech_rhythm import syllable_times

#: Largest offset a word can take, in semitones each way.
MAX_SHIFT = 12.0
#: Length of the cross-fade between two words' offsets: long enough to glide
#: like a real melody, short enough to stay inside a syllable.
_GLIDE_S = 0.05
_BRACKET_TAG = re.compile(r"\[[^\]]*\]")
_WORD = re.compile(r"[^\s]+")
# Vowel letters of the Latin, Cyrillic and Greek alphabets (base letters after
# NFD, so accented vowels count too). Uzbek o' / g' are a vowel and a
# consonant with a modifier, which this already handles.
_VOWELS = set("aeiouyæøœɑɛɪɔʊəаеёиоуўыэюяіїєөүұәαεηιοωυ")


@dataclass
class WordSpan:
    text: str
    start: float
    end: float


def script_words(text: str) -> list[str]:
    """Words of a script as a reader says them: tags like ``[laughter]`` and
    stray punctuation are dropped, punctuation attached to a word stays with
    it for display."""
    words = []
    for token in _WORD.findall(_BRACKET_TAG.sub(" ", text or "")):
        if any(ch.isalnum() for ch in token):
            words.append(token)
    return words


def syllable_count(word: str) -> int:
    """Vowel groups in ``word`` (at least 1). Scripts without vowel letters
    (CJK, Thai, Devanagari…) count one syllable per letter-ish character."""
    letters = [unicodedata.normalize("NFD", ch)[0].lower() for ch in word if ch.isalpha()]
    if not letters:
        return 1
    if not any(ch in _VOWELS for ch in letters) and not any(ch.isascii() for ch in letters):
        return max(1, len(letters))
    groups, previous = 0, False
    for ch in letters:
        vowel = ch in _VOWELS
        if vowel and not previous:
            groups += 1
        previous = vowel
    return max(1, groups)


def _speech_bounds(mono: np.ndarray, sample_rate: int) -> tuple[float, float]:
    levels, hop = frame_levels(mono, sample_rate)
    active = np.where(speech_mask(levels))[0]
    if active.size == 0:
        return 0.0, len(mono) / sample_rate
    return float(active[0] * hop / sample_rate), float((active[-1] + 1) * hop / sample_rate)


def word_spans(samples: np.ndarray, sample_rate: int, text: str) -> list[WordSpan]:
    """Place the words of ``text`` on the take's timeline (see module doc)."""
    words = script_words(text)
    if not words:
        return []
    mono = to_mono(np.asarray(samples, dtype=np.float32))
    start, end = _speech_bounds(mono, sample_rate)
    counts = np.array([syllable_count(w) for w in words])
    total = int(counts.sum())
    nuclei = syllable_times(mono, sample_rate)
    nuclei = nuclei[(nuclei >= start) & (nuclei <= end)]
    if nuclei.size >= 2:
        # Syllable k of the script lands on the k-th nucleus; when the audio
        # shows more or fewer nuclei than the text has syllables, the script's
        # syllables are spread evenly over the nuclei that were found.
        position = np.arange(total) * (nuclei.size - 1) / max(1, total - 1)
        times = np.interp(position, np.arange(nuclei.size), nuclei)
    else:
        times = np.linspace(start, end, total + 2)[1:-1]
    last = np.cumsum(counts) - 1
    first = last - counts + 1
    bounds = [start]
    for i in range(len(words) - 1):
        bounds.append(float((times[last[i]] + times[first[i + 1]]) / 2))
    bounds.append(end)
    return [WordSpan(w, bounds[i], bounds[i + 1]) for i, w in enumerate(words)]


def _match_key(word: str) -> str:
    """Spelling-insensitive key: lower case, letters and digits only."""
    folded = unicodedata.normalize("NFKD", word.lower())
    return "".join(ch for ch in folded if ch.isalnum())


def _letters(word: str) -> int:
    return max(1, sum(ch.isalnum() for ch in word))


def spans_from_asr(
    text: str, asr_words: list[dict], duration: float,
) -> list[WordSpan]:
    """Script words timed by the ASR's words (``{"word", "start", "end"}``).

    Words the recogniser heard as written take its times; a run it heard
    differently (split, merged or misspelt) shares the time of the ASR words
    it was matched against, by letter count; a run with nothing to match
    shares the gap between its neighbours. Spans are then made contiguous at
    the midpoints between words, so every moment of speech belongs to a word.
    """
    words = script_words(text)
    if not words:
        return []
    heard = sorted(asr_words, key=lambda item: item["start"])
    times: list[tuple[float, float] | None] = [None] * len(words)

    def spread(first: int, last: int, start: float, end: float) -> None:
        weights = np.array([_letters(words[k]) for k in range(first, last)], dtype=float)
        edges = start + (end - start) * np.concatenate([[0.0], np.cumsum(weights)]) / weights.sum()
        for offset, k in enumerate(range(first, last)):
            times[k] = (float(edges[offset]), float(edges[offset + 1]))

    matcher = difflib.SequenceMatcher(
        a=[_match_key(w) for w in words], b=[_match_key(h["word"]) for h in heard], autojunk=False,
    )
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                item = heard[j1 + offset]
                times[i1 + offset] = (item["start"], item["end"])
        elif i2 > i1 and j2 > j1:
            spread(i1, i2, heard[j1]["start"], heard[j2 - 1]["end"])
    k = 0
    while k < len(words):
        if times[k] is not None:
            k += 1
            continue
        run_end = k
        while run_end < len(words) and times[run_end] is None:
            run_end += 1
        gap_start = times[k - 1][1] if k > 0 else 0.0
        gap_end = times[run_end][0] if run_end < len(words) else duration
        if gap_end <= gap_start:
            gap_end = min(duration, gap_start + 0.05 * (run_end - k))
        spread(k, run_end, gap_start, gap_end)
        k = run_end
    spans = []
    for index, word in enumerate(words):
        start, end = times[index]
        if index > 0:
            start = (times[index - 1][1] + start) / 2
        if index + 1 < len(words):
            end = (end + times[index + 1][0]) / 2
        spans.append(WordSpan(word, round(max(0.0, start), 3), round(min(duration, max(end, start)), 3)))
    return spans


def pitch_curve(length: int, sample_rate: int, edits: list[tuple[float, float, float]]) -> np.ndarray:
    """Per-sample semitone curve: each ``(start_s, end_s, semitones)`` span
    holds its offset, and neighbouring offsets glide into each other over
    :data:`_GLIDE_S` centred on the boundary."""
    curve = np.zeros(length, dtype=np.float64)
    for start, end, shift in edits:
        a = max(0, int(round(start * sample_rate)))
        b = min(length, int(round(end * sample_rate)))
        if b > a:
            curve[a:b] = shift
    glide = max(1, int(_GLIDE_S * sample_rate))
    if glide > 1 and length > glide:
        window = np.hanning(glide)
        curve = np.convolve(curve, window / window.sum(), mode="same")
    return curve


def apply_word_pitch(
    samples: np.ndarray, sample_rate: int, edits: list[tuple[float, float, float]],
) -> np.ndarray:
    """Return ``samples`` (channels × frames) with each span's pitch moved by
    its semitones; timing, length and timbre stay as they were."""
    audio = np.ascontiguousarray(samples, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[np.newaxis, :]
    for start, end, shift in edits:
        if not -MAX_SHIFT <= shift <= MAX_SHIFT:
            raise ValueError(f"semitones={shift} is outside ±{MAX_SHIFT}")
        if end < start:
            raise ValueError("a span ends before it starts")
    active = [edit for edit in edits if edit[2] != 0]
    if not active or audio.shape[-1] == 0:
        return audio
    from pedalboard import time_stretch

    curve = pitch_curve(audio.shape[-1], sample_rate, active)
    out = time_stretch(
        audio, float(sample_rate),
        stretch_factor=1.0, pitch_shift_in_semitones=curve, preserve_formants=True,
    )
    # Rubber Band can return a few samples more or less; keep the take's
    # length so every time the editor shows stays true.
    length = audio.shape[-1]
    if out.shape[-1] >= length:
        out = out[:, :length]
    else:
        out = np.pad(out, ((0, 0), (0, length - out.shape[-1])))
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > 0.99:
        out = out * (0.99 / peak)
    return np.ascontiguousarray(out, dtype=np.float32)
