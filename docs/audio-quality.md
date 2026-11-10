# Audio quality in Clone and Design

The **Audio quality** controls apply to the next generated take. Existing files
stay unchanged. Normal defaults are 16-bit WAV, 32 sampling steps (the model's
own default) and the **natural** output path — a loudness match and nothing
else; model-specific limits still apply.

The compact slider sits below the script in Clone and Design. **More options**
reveals voice refinement (sampling steps), volume balancing and format guidance.
The three plain-language choices are **Standard**, **For editing**, and
**Original**; the collapsed details explain the WAV formats. Size estimates use
decimal MB per minute from the active engine’s output metadata. For unknown
model formats, the UI shows the actual size after generation instead of guessing. **Voice controls** exposes
speed, pauses, duration and reference cleanup (Auto / Yes / No); technical
model controls are collapsed under **Advanced model tuning** with plain-language
names and guidance.

Both popover headers have a **Reset to defaults** icon. Audio quality resets
WAV precision, sampling steps and mastering; Voice controls resets speed,
duration, cleanup and advanced model tuning. Each reset preserves the other
panel's settings, script, language and selected voice. Audio-quality reset is
disabled while generation is running. Existing audio files are never modified.

## Normal to maximum export precision

| WAV slider | Use | Approximate size per minute, 24 kHz mono |
| --- | --- | ---: |
| Standard (16-bit PCM) | Normal playback, smallest WAV, broad player support | 2.9 MB |
| For editing (24-bit PCM) | More precision for editing | 4.3 MB |
| Original (32-bit float) | Highest supported export precision | 5.8 MB |

These are uncompressed WAVs. Size scales with duration, sample rate and channel
count; 48 kHz doubles these estimates. The finished take shows its actual size,
sample rate, channels and sample format. Export precision cannot add information
that an engine has already discarded or improve voice identity by itself.
The WAV slider does not change model weights, quantization or sample rate.

**Voice refinement** controls model computation separately. More steps take longer,
without increasing WAV size or guaranteeing better speech. The slider appears
only for adapters that forward this setting:

| Engine | Sampling slider | Export controls |
| --- | --- | --- |
| OmniVoice, including subprocess mode | 8–64 steps | 16/24/32-bit WAV |
| VoxCPM2 | 8–64 steps | 16/24/32-bit WAV, native 48 kHz |
| dots.tts | 8–64 steps | 16/24/32-bit WAV |
| Supertonic-3 | 5–12 steps, matching its adapter limits | 16/24/32-bit WAV |
| Other TTS engines | Engine manages sampling; no ineffective slider | 16/24/32-bit WAV |

**Broadcast compression** adds the radio-style chain (two compressors, a +2 dB
high shelf, a limiter and a −2 dBFS peak normalization). It is **off by
default**: the natural path keeps the voice's own dynamics, tone and silence
floor and only matches integrated loudness to −18 LUFS under a −1.5 dBTP
ceiling (`backend/services/loudness_meter.py`, ITU-R BS.1770-4; the gain stops
at the ceiling instead of limiting). The `raw` API preset skips even that.
Engine postprocessing and the provenance watermark setting remain in effect
either way. An engine that performs its own mastering skips the coloured
presets' pre-stage; the natural path has none to skip.

## Natural output, pauses and reference cleanup

The broadcast chain used to be the silent default on every take. Measured on
a cloned Uzbek voice against its human reference (`scripts/voice_bench.py`),
it cut the loudness range from 2.9 to 1.2 LU, the crest factor from 17.5 to
15 dB and pushed the 95 % spectral roll-off from 1.7 kHz to 6.3 kHz — a
compressed, brightened result that listeners hear as synthetic. The raw model
output sat within 0.5 kHz and 2 dB of the human recording on the same
measures, so the fix was to stop processing, not to process better.

Three controls follow from the same measurements:

- **Pauses** (`pause_scale`, Voice controls → Pauses). OmniVoice leaves about
  0.17 s between sentences; the human readers it was compared with left about
  0.38 s. The control lengthens each pause the engine already produced by the
  factor, filling with that pause's own room tone and never past 0.9 s. It
  adds nothing where the engine put no pause and never shortens one. The app
  defaults to 1.6×; the API defaults to 1× so scripted callers keep their
  timing. A blank line between paragraphs becomes a 650 ms breath in every
  path (`[pause Nms]` markers still win when present).
- **Reference cleanup** (`denoise`, Voice controls → Clean reference noise).
  The model's `<|denoise|>` token asks for clean speech regardless of the
  reference's acoustics. On a clean recording that discards the room and
  microphone a listener hears as a real person; on a phone clip it is the
  right call. **Auto** (the default) measures the reference's speech-to-floor
  ratio once per file and uses the token only under 28 dB; Yes and No force it.
- **Sampling steps** default to 32: at 16 the same take measured 1.2 LU of
  loudness range against 2.0–2.2 LU at 32–64.

`scripts/voice_bench.py` renders a fixed Uzbek set — short lines, a long
paragraph, questions, joy and sorrow, numbers and dates, a mixed Uzbek /
English / Russian line, two-paragraph narration and the hard phonemes
(oʻ, gʻ, q, x, h, sh, ch, ng) — for any voice and setting, measures each take
(LUFS, loudness range, crest, pauses, F0 spread, spectral tilt), checks it
with the local Uzbek STT and, with `--baseline`, prints the deltas against an
earlier run. The numbers are proxies; the report ends with the files to listen
to. Dubbing keeps its own per-segment preset (broadcast unless a segment says
otherwise) because its loudness is set against the programme mix.

The final playback response uses the saved WAV itself. Streaming previews still
use PCM16; their completed take uses the selected precision. Updated remote
workers honor the requested precision before returning audio. Older workers or
engines that only deliver PCM16 cannot recover extra detail through a larger export.
OmniVoice and VoxCPM2 subprocesses negotiate float32 transport; legacy PCM16
responses remain supported without reinstalling engines. Float-capable responses
have a bounded 128 MiB frame allowance, preserving the old PCM16 duration limit;
other engines and requests retain their 64 MiB limit. Retention protects the take
being generated even when starred history entries already fill the cap. Cancelled
or failed save/read operations remove unpublished WAVs after the writer finishes.

## Optional signal checks

Use **Check audio** below a finished take to scan locally for long silence,
relative volume changes, clipping, empty audio or invalid samples. Click a warning
to seek to its timestamp; close the report to dismiss it. Scanning is bounded to
two hours and 100 warnings, and reports when limited. It never modifies audio.
Warnings are advisory signal checks, not a voice-similarity or naturalness score.

## Validation and repeatable comparisons

PR #2406 exercises real installed engines on Windows with an RTX 4090:

| Engine | Real generation coverage | Format |
| --- | --- | --- |
| OmniVoice | TTS and cloning, 16/32/64 steps | 24 kHz mono |
| OmniVoice subprocess | TTS and cloning, 16/32/64 steps | 24 kHz mono |
| VoxCPM2 subprocess | TTS and cloning, 16/32/64 steps | 48 kHz mono |
| KittenTTS | Fixed-voice TTS; cloning/step tuning unsupported | 24 kHz mono |

Each condition is exported at all three precisions, with broadcast and raw
processing. The first sweep produced 114 valid WAVs with finite samples and no
signal warnings. Offline Whisper large-v3 recovered all 13 words in each of the
19 raw float conditions. That short single-text check establishes intelligibility
for these trials, not a perceptual ranking across voices or languages.

The sweep exposed seed propagation gaps in the explicit OmniVoice and VoxCPM2
sidecars. Those now receive per-chunk seeds, with a fresh sweep after the fix.
On the seeded VoxCPM2 clone trial, 16/32/64 steps took approximately 9.7/14.1/27.2
seconds; increasing sampling effort has a measurable time cost.

Model-free regression tests cover export precision, identical final playback/save
bytes, streamed final samples, stereo/rate preservation, remote-worker encoding,
float sidecar round trips, legacy frames, seed forwarding, warning bounds, path
confinement, keyboard sliders and locale parity. Precision tests fail against the
original PR implementation, which writes PCM16 regardless of the requested bits.
The same implementation is used on macOS, Windows and Linux; real synthesis on
macOS/Linux and engines absent from this Windows installation is not claimed here.

For another installed engine or reference, run the repository Python interpreter:

```sh
python scripts/compare_generation_quality.py \
  --engines omnivoice omnivoice-subprocess voxcpm2 kittentts \
  --output /path/to/new-comparison-directory \
  --ref-audio /path/to/reference.wav --ref-text "Reference transcript"
```

The script runs offline, uses installed models, routes WAVs through provenance marking when enabled and available, and writes
`results.json`, and refuses to overwrite an output directory. Omit the reference
arguments for TTS only; use `--text`, `--steps` and `--seed` to vary the experiment.
Keep private recordings and generated voice comparisons outside Git. The original
[audio investigation](audio-quality-handoff.md) remains available as historical
evidence; this work does not establish a cause for the historical reverb report.

Generated WAV reads use a shared TorchCodec fallback, including dub assembly,
cached segments, watermark detection, longform and persona previews. Voice Clone
blocks models that explicitly report no cloning support and explains how to select
a capable model; plain text-to-speech remains available.
