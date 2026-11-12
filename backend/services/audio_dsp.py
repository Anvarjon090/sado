"""
Audio DSP pipeline — output presets, pause shaping and the optional effects chain.

`finalize_output()` is the one tail every synthesis goes through. The default
preset, **natural**, is a measurement and a gain: BS.1770 integrated loudness
matched to −18 LUFS under a −1.5 dBTP ceiling, nothing else — the voice keeps
the dynamics, tone and silence floor the model gave it. That default exists
because the old one did not: the **broadcast** preset (two compressors, a
+2 dB high shelf, a limiter and a −2 dBFS peak normalization) measurably
flattened a cloned Uzbek voice — loudness range 2.9 → 1.2 LU, crest 17.5 →
15 dB, 95 % spectral roll-off 1.7 → 6.3 kHz against the human reference —
and that compressed, brightened result is what listeners hear as "AI".
Broadcast and the other coloured presets stay available as explicit choices.

`apply_mastering()` is the shared pre-stage of those coloured presets:
highpass + gentle compression only (see `MASTERING_CHAIN`). Reverb is
deliberately NOT part of it — it is preset-declared only (cinematic, warm); a
hidden reverb here used to bake echo into every synthesis. `apply_effects_chain()`
lets callers build custom pipelines from a list of named effects.

`shape_pauses()` lengthens the pauses the engine already placed — OmniVoice
leaves ~0.17 s between sentences where the human readers it was compared
with left ~0.38 s — by extending each gap with its own room tone. It never
adds pauses, noise or randomness.

The coloured effects use Spotify's `pedalboard` library. When pedalboard isn't
installed, those functions degrade gracefully (return audio unmodified); the
natural preset has no such dependency.
"""
import logging

import numpy as np
import torch

logger = logging.getLogger("omnivoice.dsp")

#: Preset every synthesis gets unless the request names another.
DEFAULT_EFFECT_PRESET = "natural"
#: Where the natural preset puts integrated loudness, and the true-peak ceiling
#: the gain stops at. −18 LUFS sits between podcast (−16) and broadcast (−23)
#: practice and leaves a cloned voice with a 20 dB crest factor unclipped.
NATURAL_TARGET_LUFS = -18.0
NATURAL_CEILING_DBTP = -1.5

# ── Effect presets ──────────────────────────────────────────────────────

EFFECT_PRESETS = {
    "natural": {
        "label": "Natural",
        "icon": "🎚️",
        "description": "Level only — the voice's own dynamics and tone, matched to −18 LUFS.",
        "chain": [],
    },
    "broadcast": {
        "label": "Broadcast",
        "icon": "📻",
        "description": "Radio/podcast standard — warm, compressed, clear.",
        "chain": [
            {"type": "highpass", "cutoff_hz": 80},
            {"type": "compressor", "threshold_db": -18, "ratio": 3.0, "attack_ms": 5, "release_ms": 80},
            {"type": "eq", "low_gain_db": 1.5, "mid_gain_db": 0, "high_gain_db": 2.0},
            {"type": "limiter", "threshold_db": -1.0},
        ],
    },
    "cinematic": {
        "label": "Cinematic",
        "icon": "🎬",
        "description": "Film-quality — spacious reverb, gentle compression.",
        "chain": [
            {"type": "highpass", "cutoff_hz": 60},
            {"type": "compressor", "threshold_db": -15, "ratio": 1.8, "attack_ms": 10, "release_ms": 150},
            {"type": "reverb", "room_size": 0.35, "wet_level": 0.15, "dry_level": 0.85},
            {"type": "limiter", "threshold_db": -1.5},
        ],
    },
    "podcast": {
        "label": "Podcast",
        "icon": "🎙️",
        "description": "Close-mic, intimate — heavy compression, no reverb.",
        "chain": [
            {"type": "highpass", "cutoff_hz": 100},
            {"type": "noise_gate", "threshold_db": -40, "release_ms": 200},
            {"type": "compressor", "threshold_db": -20, "ratio": 4.0, "attack_ms": 2, "release_ms": 60},
            {"type": "eq", "low_gain_db": -1.0, "mid_gain_db": 2.0, "high_gain_db": 1.5},
            {"type": "limiter", "threshold_db": -0.5},
        ],
    },
    "raw": {
        "label": "Raw",
        "icon": "🔇",
        "description": "No processing — model output as-is.",
        "chain": [],
    },
    "warm": {
        "label": "Warm",
        "icon": "☀️",
        "description": "Boosted low-mids, subtle saturation, cozy feel.",
        "chain": [
            {"type": "highpass", "cutoff_hz": 60},
            {"type": "eq", "low_gain_db": 3.0, "mid_gain_db": 1.0, "high_gain_db": -1.0},
            {"type": "compressor", "threshold_db": -16, "ratio": 2.0, "attack_ms": 8, "release_ms": 120},
            {"type": "reverb", "room_size": 0.15, "wet_level": 0.06, "dry_level": 0.94},
        ],
    },
    "bright": {
        "label": "Bright",
        "icon": "✨",
        "description": "Crisp high-end, presence boost, airy feel.",
        "chain": [
            {"type": "highpass", "cutoff_hz": 80},
            {"type": "eq", "low_gain_db": -1.0, "mid_gain_db": 0, "high_gain_db": 4.0},
            {"type": "compressor", "threshold_db": -14, "ratio": 2.5, "attack_ms": 3, "release_ms": 80},
            {"type": "limiter", "threshold_db": -1.0},
        ],
    },
}


def list_effect_presets() -> list[dict]:
    """Return presets for the frontend UI picker."""
    return [
        {"id": k, "label": v["label"], "icon": v["icon"], "description": v["description"]}
        for k, v in EFFECT_PRESETS.items()
    ]


def get_effect_chain(preset_id: str) -> list[dict]:
    """Return the effect chain for a preset. Falls back to empty chain."""
    p = EFFECT_PRESETS.get(preset_id)
    return p["chain"] if p else []


# ── Core DSP functions ──────────────────────────────────────────────────

#: Shared pre-preset mastering stage: highpass + gentle compression ONLY.
#: Reverb must never live here — a hidden Reverb in this chain baked echo
#: into every non-raw synthesis regardless of the chosen preset (field
#: reports of echoey voices; the podcast preset even promises "no reverb").
#: Reverb is preset-declared only (see EFFECT_PRESETS: cinematic, warm).
MASTERING_CHAIN = [
    {"type": "highpass", "cutoff_hz": 60},
    {"type": "compressor", "threshold_db": -15, "ratio": 1.5, "attack_ms": 2.0, "release_ms": 100},
]


def apply_mastering(audio_tensor, sample_rate=24000):
    """Applies the broadcast pre-stage (highpass + gentle compression) to the clone voice.

    Reverb is intentionally absent — only user-chosen effect presets declare
    it. Degrades gracefully: pedalboard missing or any DSP error returns the
    input unmodified.
    """
    try:
        return apply_effects_chain(audio_tensor, sample_rate, MASTERING_CHAIN)
    except Exception as e:
        logger.warning("Mastering DSP Error: %s", e)
        return audio_tensor


def normalize_audio(audio_tensor, target_dBFS=-2.0):
    """Peak-normalizes the audio to a standard broadcasting level (-2 dB) to fix F5TTS volume fluctuations.

    Never amplifies a near-silent signal. A failed/empty render sits at the
    noise floor; blindly scaling its peak up to -2 dBFS applies thousands of
    times of gain and turns silence into full-scale hiss — the "blank noise"
    some generated voices exhibited. Below a -50 dBFS silence floor we leave the
    audio untouched so it stays inaudible (and downstream guards can treat it as
    a dead render) instead of shipping amplified noise. Real speech — even a
    whisper — peaks well above this floor, so normal output is unaffected.
    """
    if audio_tensor.numel() == 0:
        return audio_tensor
    max_val = torch.abs(audio_tensor).max()
    # -50 dBFS ≈ 0.00316 linear. Anything at/below this is silence / noise floor.
    silence_floor = 10 ** (-50.0 / 20.0)
    if max_val > silence_floor:
        target_amp = 10 ** (target_dBFS / 20.0)
        audio_tensor = audio_tensor * (target_amp / max_val)
    return audio_tensor


def trim_trailing_silence(
    audio_tensor: torch.Tensor,
    sample_rate: int,
    keep_tail_s: float = 0.3,
) -> torch.Tensor:
    """Trim trailing near-silence from a generated clip, keeping a short
    natural tail of ``keep_tail_s`` seconds after the last voiced sample.

    Amplitude-based SILENCE trim only — no content analysis of any kind.
    Uses the same -50 dBFS silence floor as :func:`normalize_audio`: the last
    sample above that floor marks the end of speech, and everything more than
    ``keep_tail_s`` past it is dropped.

    Guaranteed no-op cases (input returned as-is, same object):
      • the trailing quiet span is already ≤ ``keep_tail_s`` (clean output);
      • the entire clip sits below the floor (dead render — downstream
        dead-render guards own that case, we must not shrink their evidence);
      • empty input.

    Accepts ``(n,)`` or ``(channels, n)`` tensors; the returned tensor keeps
    the input's shape convention.
    """
    if audio_tensor.numel() == 0:
        return audio_tensor
    # -50 dBFS ≈ 0.00316 linear — matches normalize_audio's silence floor.
    floor = 10 ** (-50.0 / 20.0)
    envelope = torch.abs(audio_tensor)
    if envelope.ndim > 1:
        envelope = envelope.amax(dim=tuple(range(envelope.ndim - 1)))
    voiced = torch.nonzero(envelope > floor)
    if voiced.numel() == 0:
        return audio_tensor
    last_voiced = int(voiced[-1].item())
    end = last_voiced + 1 + int(keep_tail_s * sample_rate)
    if end >= audio_tensor.shape[-1]:
        return audio_tensor
    return audio_tensor[..., :end]



def trim_speech_padding(audio_tensor: torch.Tensor, sample_rate: int) -> torch.Tensor:
    """Remove generated edge silence before timing, retaining 50 ms of context.

    Never compress silence into the spoken slot or delete internal pauses.
    Silent/invalid outputs remain intact for the generation integrity guard.
    """
    if audio_tensor.numel() == 0 or sample_rate <= 0:
        return audio_tensor
    envelope = audio_tensor.abs()
    if envelope.ndim > 1:
        envelope = envelope.amax(dim=tuple(range(envelope.ndim - 1)))
    voiced = torch.nonzero(envelope > 10 ** (-50 / 20))
    if voiced.numel() == 0:
        return audio_tensor
    margin = int(sample_rate * 0.05)
    start = max(0, int(voiced[0].item()) - margin)
    end = min(audio_tensor.shape[-1], int(voiced[-1].item()) + 1 + margin)
    return audio_tensor[..., start:end]

def apply_effects_chain(audio_tensor, sample_rate: int, chain: list[dict]) -> torch.Tensor:
    """Apply a chain of named effects to an audio tensor.

    Each item in `chain` is a dict with a `type` key and effect-specific
    parameters. Unknown types are silently skipped.

    Supported types:
        highpass    — cutoff_hz (default 80)
        lowpass     — cutoff_hz (default 8000)
        compressor  — threshold_db, ratio, attack_ms, release_ms
        reverb      — room_size, wet_level, dry_level
        noise_gate  — threshold_db, release_ms
        eq          — low_gain_db, mid_gain_db, high_gain_db
        limiter     — threshold_db
    """
    if not chain:
        return audio_tensor

    try:
        from pedalboard import (
            Pedalboard,
            Compressor,
            Reverb,
            HighpassFilter,
            LowpassFilter,
            NoiseGate,
            Limiter,
            LowShelfFilter,
            HighShelfFilter,
            PeakFilter,
        )
    except ImportError:
        logger.debug("pedalboard not installed — effects chain skipped")
        return audio_tensor

    plugins = []
    for fx in chain:
        t = fx.get("type", "").lower()
        try:
            if t == "highpass":
                plugins.append(HighpassFilter(cutoff_frequency_hz=fx.get("cutoff_hz", 80)))
            elif t == "lowpass":
                plugins.append(LowpassFilter(cutoff_frequency_hz=fx.get("cutoff_hz", 8000)))
            elif t == "compressor":
                plugins.append(Compressor(
                    threshold_db=fx.get("threshold_db", -15),
                    ratio=fx.get("ratio", 2.0),
                    attack_ms=fx.get("attack_ms", 5),
                    release_ms=fx.get("release_ms", 100),
                ))
            elif t == "reverb":
                plugins.append(Reverb(
                    room_size=fx.get("room_size", 0.2),
                    wet_level=fx.get("wet_level", 0.1),
                    dry_level=fx.get("dry_level", 0.9),
                ))
            elif t == "noise_gate":
                plugins.append(NoiseGate(
                    threshold_db=fx.get("threshold_db", -40),
                    release_ms=fx.get("release_ms", 200),
                ))
            elif t == "limiter":
                plugins.append(Limiter(threshold_db=fx.get("threshold_db", -1.0)))
            elif t == "eq":
                low = fx.get("low_gain_db", 0)
                mid = fx.get("mid_gain_db", 0)
                high = fx.get("high_gain_db", 0)
                if low:
                    plugins.append(LowShelfFilter(cutoff_frequency_hz=250, gain_db=low))
                if mid:
                    plugins.append(PeakFilter(cutoff_frequency_hz=1500, gain_db=mid, q=1.0))
                if high:
                    plugins.append(HighShelfFilter(cutoff_frequency_hz=4000, gain_db=high))
            else:
                logger.debug("Unknown effect type: %s — skipped", t)
        except Exception as e:
            logger.warning("Failed to create %s effect: %s", t, e)

    if not plugins:
        return audio_tensor

    board = Pedalboard(plugins)
    audio_np = audio_tensor.cpu().numpy()
    if audio_np.ndim == 1:
        audio_np = audio_np[None, :]
    try:
        effected = board(audio_np, sample_rate, reset=False)
        return torch.from_numpy(effected).to(audio_tensor.device)
    except Exception as e:
        logger.warning("Effects chain failed: %s — returning unmodified audio", e)
        return audio_tensor



# ── Output finalization: natural loudness, pause shaping, preset dispatch ──


def loudness_normalize(
    audio_tensor: torch.Tensor,
    sample_rate: int,
    target_lufs: float = NATURAL_TARGET_LUFS,
    ceiling_dbtp: float = NATURAL_CEILING_DBTP,
) -> torch.Tensor:
    """Gain-only BS.1770 loudness match — the whole of the ``natural`` preset.

    The waveform is multiplied by one constant: integrated loudness lands on
    ``target_lufs`` unless the true peak would pass ``ceiling_dbtp``, where the
    gain stops instead of limiting. Silence (nothing above the −70 LUFS gate)
    comes back untouched, never amplified into hiss. Shape, dtype and device
    are preserved.
    """
    if audio_tensor.numel() == 0:
        return audio_tensor
    from services.loudness_meter import normalize_gain

    arr = audio_tensor.detach().cpu().float().numpy()
    out, info = normalize_gain(arr, sample_rate, target_lufs=target_lufs, ceiling_dbtp=ceiling_dbtp)
    if info.gain_db == 0.0:
        return audio_tensor
    return torch.from_numpy(out).to(device=audio_tensor.device, dtype=audio_tensor.dtype)


#: Internal gaps shorter than this are articulation, not pauses.
PAUSE_MIN_MS = 150
#: No pause is stretched past this, whatever the scale.
PAUSE_MAX_MS = 900
#: With the text's pause sites known, a sentence pause is not stretched past
#: this and a clause pause not past the second: a reader's full stop is about
#: 0.4-0.6 s and a comma about 0.2 s (0.58 s and 0.17 s in the human reference
#: measured on 2026-11-12), and a paragraph break is PARAGRAPH_PAUSE_MS = 650.
PAUSE_SENTENCE_MAX_MS = 600
PAUSE_CLAUSE_MAX_MS = 300
_PAUSE_JOIN_S = 0.005


def _room_tone(gap: np.ndarray, n_samples: int) -> np.ndarray:
    """``n_samples`` of the gap's own ambience: its middle 60 % mirrored end to
    end, so the fill has the floor the model produced and no seam."""
    length = gap.shape[1]
    lo, hi = int(length * 0.2), max(int(length * 0.8), int(length * 0.2) + 1)
    core = gap[:, lo:hi]
    tile = np.concatenate([core, core[:, ::-1]], axis=1)
    reps = n_samples // tile.shape[1] + 1
    return np.tile(tile, (1, reps))[:, :n_samples]


def shape_pauses(
    audio_tensor: torch.Tensor,
    sample_rate: int,
    scale: float = 1.0,
    *,
    min_pause_ms: int = PAUSE_MIN_MS,
    max_pause_ms: int = PAUSE_MAX_MS,
    sites: tuple[int, int] | None = None,
) -> torch.Tensor:
    """Lengthen the pauses the engine already left, each by ``scale``.

    Every internal gap of at least ``min_pause_ms`` grows to
    ``min(gap × scale, max_pause_ms)``; the extension is the gap's own room
    tone (see :func:`_room_tone`), spliced in at the gap's centre with 5 ms
    crossfades. Gaps that are mostly exact digital silence are the ``[pause]``
    buffers and paragraph gaps a caller inserted on purpose (or an engine's
    zero padding at a chunk boundary) and are left alone. Nothing is
    added where the engine put no pause, no gap is shortened, and ``scale <= 1``
    returns the input itself. Accepts ``(n,)`` or ``(channels, n)``.

    ``sites`` — ``(sentence, clause)``, how many places the text itself gives a
    reader to pause (``speech_rhythm.pause_site_counts``). With it, only that
    many gaps are lengthened, the longest first: the ``sentence`` longest by
    ``scale`` up to :data:`PAUSE_SENTENCE_MAX_MS`, the next ``clause`` by half
    the extension up to :data:`PAUSE_CLAUSE_MAX_MS`, and every other gap is one
    the engine left *inside* a phrase and stays as spoken. Without it every gap
    is a pause, which on ten benchmark takes turned 45 gaps into 52 audible
    breaks and made sixteen of them 0.6 s or longer where the engine had made
    none (2026-11-12).
    """
    if scale <= 1.0 or audio_tensor.numel() == 0:
        return audio_tensor
    from services.speech_metrics import frame_levels, runs, speech_mask

    arr = audio_tensor.detach().cpu().float().numpy()
    flat = arr.ndim == 1
    x = arr[None, :] if flat else arr
    mono = x.mean(axis=0)
    levels, hop = frame_levels(mono, sample_rate)
    active = speech_mask(levels)
    idx = np.where(active)[0]
    if idx.size < 2:
        return audio_tensor
    first, last = int(idx[0]), int(idx[-1])
    xf = int(_PAUSE_JOIN_S * sample_rate)
    eligible = []
    for a, b in runs(~active[first:last + 1]):
        start, end = (a + first) * hop, min((b + first) * hop, x.shape[1])
        gap_s = (end - start) / sample_rate
        if gap_s * 1000.0 < min_pause_ms:
            continue
        if np.mean(x[:, start:end] == 0) > 0.5:
            # Mostly exact zeros: a [pause]/paragraph buffer or an engine's
            # edge padding at a chunk boundary, not a pause the model spoke.
            continue
        eligible.append((start, end, gap_s))
    # (scale, ceiling in seconds) per gap; without sites every gap is a pause.
    plans = [(scale, max_pause_ms / 1000.0)] * len(eligible)
    if sites is not None:
        sentence, clause = max(0, int(sites[0])), max(0, int(sites[1]))
        soft = 1.0 + (scale - 1.0) / 2.0
        by_length = sorted(range(len(eligible)), key=lambda i: -eligible[i][2])
        for rank, i in enumerate(by_length):
            if rank < sentence:
                plans[i] = (scale, min(max_pause_ms, PAUSE_SENTENCE_MAX_MS) / 1000.0)
            elif rank < sentence + clause:
                plans[i] = (soft, min(max_pause_ms, PAUSE_CLAUSE_MAX_MS) / 1000.0)
            else:
                plans[i] = (1.0, 0.0)
    pieces = []
    cursor = 0
    for (start, end, gap_s), (gap_scale, ceiling_s) in zip(eligible, plans):
        gap = x[:, start:end]
        extra = int(round((min(ceiling_s, gap_s * gap_scale) - gap_s) * sample_rate))
        if extra < xf * 2:
            continue
        mid = (start + end) // 2
        fill = _room_tone(gap, extra + 2 * xf)
        ramp = np.linspace(0.0, 1.0, xf, dtype=np.float32)[None, :] if xf else None
        head, tail = x[:, cursor:mid], x[:, mid:]
        if ramp is not None and head.shape[1] >= xf and tail.shape[1] >= xf:
            fill = fill.copy()
            fill[:, :xf] = head[:, -xf:] * (1 - ramp) + fill[:, :xf] * ramp
            fill[:, -xf:] = fill[:, -xf:] * (1 - ramp) + tail[:, :xf] * ramp
            pieces.extend([head[:, :-xf], fill])
            cursor = mid + xf
        else:
            pieces.extend([head, fill[:, xf:-xf] if xf else fill])
            cursor = mid
    if not pieces:
        return audio_tensor
    pieces.append(x[:, cursor:])
    out = np.concatenate(pieces, axis=1)
    if flat:
        out = out[0]
    return torch.from_numpy(np.ascontiguousarray(out)).to(
        device=audio_tensor.device, dtype=audio_tensor.dtype
    )


def finalize_output(
    audio_tensor: torch.Tensor,
    sample_rate: int,
    preset: str = DEFAULT_EFFECT_PRESET,
    *,
    skip_mastering: bool = False,
    pause_scale: float = 1.0,
    pause_sites: tuple[int, int] | None = None,
) -> torch.Tensor:
    """The one tail every synthesis runs: pause shaping, then the preset.

    * ``raw`` — the engine's output as it came, pauses included.
    * ``natural`` (default) — :func:`shape_pauses` then
      :func:`loudness_normalize`; no compression, EQ or limiting.
    * any coloured preset — :func:`shape_pauses`, the mastering pre-stage
      (unless ``skip_mastering``, for engines that master their own output),
      the preset's chain, then a −2 dBFS peak normalization.

    ``pause_sites`` is the text's ``(sentence, clause)`` pause count
    (``speech_rhythm.pause_site_counts``); a caller that knows the text passes
    it so only pauses the text asked for are lengthened.

    Raises ``ValueError`` for an unknown preset id so a typo is a 4xx, not
    silently "natural".
    """
    preset = preset or DEFAULT_EFFECT_PRESET
    if preset not in EFFECT_PRESETS:
        raise ValueError(
            f"Unknown effect preset: {preset!r}. Valid: {list(EFFECT_PRESETS.keys())}"
        )
    if preset == "raw":
        return audio_tensor
    if pause_scale and pause_scale != 1.0:
        audio_tensor = shape_pauses(audio_tensor, sample_rate, pause_scale, sites=pause_sites)
    if preset == "natural":
        return loudness_normalize(audio_tensor, sample_rate)
    if not skip_mastering:
        audio_tensor = apply_mastering(audio_tensor, sample_rate=sample_rate)
    chain = get_effect_chain(preset)
    if chain:
        audio_tensor = apply_effects_chain(audio_tensor, sample_rate=sample_rate, chain=chain)
    return normalize_audio(audio_tensor, target_dBFS=-2.0)
