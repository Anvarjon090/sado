# Generation Parameters

Parameters can be passed as keyword arguments to `model.generate(...)` or via the `OmniVoiceGenerationConfig` dataclass. See below for the full list and which category each belongs to.

```python
# 1) Direct keyword arguments
audio = model.generate(text="Hello world", num_step=32, guidance_scale=2.0)

# 2) Via OmniVoiceGenerationConfig dataclass
from omnivoice import OmniVoiceGenerationConfig

config = OmniVoiceGenerationConfig(num_step=32, guidance_scale=2.0)
audio = model.generate(text="Hello world", generation_config=config)
```

## Decoding

| Parameter | Type | Default | Description |
|---|---|---|---|
| `num_step` | int | 32 | Number of iterative unmasking steps. Higher values improve quality but slow down generation. Use 16 for faster inference. |
| `denoise` | bool | True | Prepend the `<|denoise|>` token to the input, which signals the model to produce cleaner speech. Sado's `/generate` leaves it unset by default and decides per reference (see below). |
| `guidance_scale` | float | 2.0 | Classifier-free guidance scale.|
| `t_shift` | float | 0.1 | Time-step shift for the noise schedule. Smaller values emphasise earlier steps in decoding. |

## Sampling

| Parameter | Type | Default | Description |
|---|---|---|---|
| `position_temperature` | float | 5.0 | Temperature for mask-position selection. 0 = greedy (deterministic). Higher values increase randomness. |
| `class_temperature` | float | 0.0 | Temperature for token sampling at each step. 0 = greedy (deterministic). Higher values increase randomness. |
| `layer_penalty_factor` | float | 5.0 | Penalty applied to deeper codebook layers, encouraging earlier (lower) layers to unmask first. |

> Using temperature (and seed pinning) to elicit expressive delivery — breaths, laughter, sighs — is covered in [expressive-speech.md](expressive-speech.md), including the tradeoffs.

## Duration & Speed

These accept a single value applied to all items, or a per-item list (useful in batch mode):

```python
# Fixed 10-second output
audio = model.generate(text="Hello, this is a test of duration control", duration=10.0)

# Faster speech (1.2x faster than estimated)
audio = model.generate(text="Hello, this is a test of duration control", speed=1.2)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `duration` | float or list[float \| None] | None | Fixed output duration in seconds. Overrides `speed` when set. |
| `speed` | float or list[float \| None] | None | Speed factor. Values > 1.0 produce shorter audio (faster); values < 1.0 produce longer audio (slower). Ignored when `duration` is set. Defaults to 1.0 when both are None. |

Priority: `duration` > `speed`.

## Pre/Post Processing

| Parameter | Type | Default | Description |
|---|---|---|---|
| `preprocess_prompt` | bool | True | Whether to apply preprocessing to the voice-clone prompt audio (remove long silences in reference audio, add punctuation in the end of reference text). |
| `postprocess_output` | bool | True | Apply post-processing to generated audio (remove long silences). |

> **Note — quiet recordings are safe.** Silence removal is adaptive: if trimming at the standard threshold would consume a quiet-but-real recording, progressively gentler thresholds are tried and, as a last resort, trimming is skipped — a quiet clip clones instead of erroring. Only a clip with genuinely no audio (empty or fully silent) is rejected, with guidance to re-record closer to the microphone.
>
> **Tip — reference-clip quality transfers.** Zero-shot cloning mirrors the acoustics of the reference clip, not just the voice: a clip recorded in an echoey room clones echoey. Record dry and close-mic for clean output. No effect preset adds reverb unless you choose one that declares it (Cinematic, Warm).

For an in-app recording, choose the microphone and Auto, Mono, or Stereo in the Voice panel. While recording, the input meter confirms whether Sado is receiving a usable signal; monitoring is visual and never plays the microphone through the speakers.

## Sado output path (`POST /generate`)

| Field | Default | Description |
|---|---|---|
| `effect_preset` | `natural` | `natural` matches integrated loudness to −18 LUFS under a −1.5 dBTP ceiling and changes nothing else; `broadcast`, `podcast`, `cinematic`, `warm`, `bright` add their chains; `raw` returns the engine output as is. |
| `pause_scale` | `1.0` (app: `1.6`) | Lengthens the engine's own pauses of 150 ms or more by this factor with their room tone, capped at 0.9 s; range 1–3. Never adds or shortens a pause. |
| `denoise` | unset | Unset = measured per reference: the `<|denoise|>` token is used when the clip's speech-to-floor ratio is under 28 dB, otherwise the recording's acoustics are kept. `true`/`false` force it. Voice design has no reference and never uses it. |
| `num_step` | performance tier (16 / 32 / 64) | The app sends 32 unless you move the slider. |
| `retake` | `true` | With a reference clip: a chunk whose median pitch lands more than 6 semitones from the reference's, or that has no harmonic structure, is rendered once more with a retake seed and the closer take is kept (`backend/services/take_guard.py`). `false` keeps the first take. |

A blank line between paragraphs is rendered as separate spans with a 650 ms
breath between them; `[pause Nms]` markers take precedence when present. Text
that starts with `<speak>` is parsed as SSML — see [ssml.md](ssml.md).

## Long-Form Generation

To support stable long-form speech generation with low VRAM consumption, the text is automatically split into smaller segments when the estimated duration of the generated speech exceeds `audio_chunk_duration`, with each segment producing approximately `audio_chunk_duration` seconds of audio. This approach allows the model to accept arbitrarily long text and generate arbitrarily long speech with near-constant VRAM consumption.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `audio_chunk_duration` | float | 15.0 | Target chunk duration (seconds) when splitting long text. |
| `audio_chunk_threshold` | float | 30.0 | Estimated audio duration (seconds) above which chunking is activated. |
