# Sado — Navoiy-TTS (Uzbek)

[Navoiy-TTS](https://huggingface.co/aisha-org/navoiy-tts) (Apache-2.0) is an
Uzbek text-to-speech checkpoint: **CosyVoice2-0.5B** fine-tuned on roughly
**640 hours of Uzbek speech** (600 h neutral + 40 h expressive). It reads
Uzbek with Uzbek phonetics instead of borrowing a neighbouring language's,
clones a voice from a 3–10 s recording, and applies **ten emotion presets**
through an English instruction prefix.

> **Opt-in, and never the default.** Navoiy-TTS is selected explicitly in
> **Model Catalogue** (or `OMNIVOICE_TTS_BACKEND=navoiy`). It is not part of
> the default install, and it speaks **Uzbek only**.

## Why its own Python environment

The checkpoint needs **`transformers==4.51.3`**. Under the `transformers` 5
build the parent process runs, the model's LLM never emits its end-of-speech
token: a 12-word sentence that should take ~4 s came back as 17.6 s of drawn
out syllables ("ba-ba-ba") with `transformers` 5.10.1, and 3.6 s with 4.51.3.
That is a hard pin conflict, so the engine runs as a sidecar in its own venv —
the same isolation [IndexTTS-2](indextts.md) and
[MOSS-TTS-v1.5](moss-tts-v15.md) use.

## Platform support

- **Windows, Linux, macOS** — the code path is plain PyTorch + ONNX.
- **CUDA strongly recommended.** fp32 inference on an RTX 2070 Super renders
  about 1 s of audio in 1–2 s once warm; CPU is roughly 5× slower.
- **VRAM:** ~3.5 GB with the base model, the LLM checkpoint and the vocoder
  resident in fp32.
- **Reference recording required.** The checkpoint ships no built-in speakers,
  so a voice without a recording cannot be spoken by this engine (the request
  is refused with a message, and other engines still can).

## Install

Everything lives in one folder — call it the install root, `D:\omni-navoiy`
below. It holds the CosyVoice checkout, the base weights, the checkpoint and
the engine's venv.

```powershell
# 1. The engine's own environment (Python 3.10/3.11, torch 2.7 cu128 on NVIDIA)
uv venv -p 3.11 D:\omni-navoiy\venv
uv pip install -p D:\omni-navoiy\venv\Scripts\python.exe `
  torch==2.7.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128
#    (CPU-only host: drop the --index-url line)
uv pip install -p D:\omni-navoiy\venv\Scripts\python.exe `
  -r backend\engines\cosyvoice_subprocess\requirements.txt pyworld
# then pin transformers to what this checkpoint was trained with:
uv pip install -p D:\omni-navoiy\venv\Scripts\python.exe transformers==4.51.3

# 2. The CosyVoice checkout the checkpoint runs on, at the reviewed commit
git clone https://github.com/FunAudioLLM/CosyVoice.git D:\omni-navoiy\CosyVoice
git -C D:\omni-navoiy\CosyVoice checkout 074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc
git -C D:\omni-navoiy\CosyVoice submodule update --init --recursive

# 3. Weights
hf download FunAudioLLM/CosyVoice2-0.5B --local-dir D:\omni-navoiy\base
hf download aisha-org/navoiy-tts emotion_600h_joint.pt --local-dir D:\omni-navoiy\navoiy
```

`base/` needs `cosyvoice2.yaml`, `campplus.onnx`, `speech_tokenizer_v2.onnx`,
`flow.pt`, `hift.pt` and `CosyVoice-BlankEN/`. The base `llm.pt` is **not**
used — the Navoiy checkpoint replaces it — so you may skip that 2 GB file if
your download tool allows it.

## Configure

```
OMNIVOICE_NAVOIY_DIR=D:/omni-navoiy
```

Set it in **Settings → Environment** (or the OS environment) and restart
Sado. **Model Catalogue → Navoiy-TTS** then shows the engine as
available; pick it before generating, or pin it with
`OMNIVOICE_TTS_BACKEND=navoiy`.

## Using it

1. Pick a voice that has a **reference recording** (a cloned profile, not a
   designed/built-in one).
2. Choose an emotion. In the Audiobook expressive panel the free-text field is
   `emo_text`; the ten preset names are accepted verbatim, and any other text
   is passed to the model as its own instruction:

   | Preset | Delivery |
   |---|---|
   | `xotirjam` | calm, steady, even pacing (default) |
   | `xursand` | happy, energetic, bright rising intonation |
   | `g'amgin` | sad, low energy, slow falling tone |
   | `jahldor` | angry, clipped, forceful, loud |
   | `qo'rqqan` | fearful, shaky, higher pitch |
   | `hayratda` | surprised, sharp rise in pitch |
   | `pichirlab` | soft whisper, breathy |
   | `mehribon` | warm, gentle, slow |
   | `charchagan` | tired, drawn-out pace, sighs |
   | `kinoyali` | sarcastic, mocking drawl |

3. Dubbing passes its director tone (`instruct=`) through unchanged, so a
   per-segment "urgent, surprised" direction reaches the model as prose.

### Dubbing switches to it on its own

An **all-Uzbek dub** runs on Navoiy-TTS as soon as the engine is installed:
the dub route routes the job before any weights load, so the video pipeline
gets the Uzbek checkpoint without touching the engine selected in Settings. A
job keeps the configured engine when any segment carries a non-Uzbek language
override, and an explicit Settings pick or `OMNIVOICE_TTS_BACKEND` pin always
wins. Nothing is routed when a voice has no recording — dubbing clones from a
profile, so this holds by construction; the one-shot **Text → Speech** path
still needs the engine chosen explicitly (its voices may be designed, with no
reference to clone).

## Limits

- **Uzbek only.** A request for another language is refused by the engine
  contract with the standard "engine can't speak X" message.
- **One emotion per request.** A long text read in one preset is the intended
  use; per-segment emotions belong to dubbing, where each segment is its own
  request.
- **Reference quality matters.** A noisy or heavily accented sample carries
  over; a clean 5–15 s clip is best.
- **First call is slow** (~30 s cold load, longer on a cold page cache). Later
  calls reuse the sidecar.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Row says `OMNIVOICE_NAVOIY_DIR is not set` | Set the env var and restart the app. |
| `No engine venv under …` | The venv must be at `<root>/.venv` or `<root>/venv`. |
| Output is drawn-out syllables | Wrong `transformers` in the engine venv — reinstall `transformers==4.51.3` there. |
| `Navoiy-TTS needs a reference recording` | The chosen voice has no sample; pick a cloned profile or another engine. |
| Slow on CPU | Expected (~5× real time). Use a CUDA build of torch in the engine venv. |
