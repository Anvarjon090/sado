"""navoiy sidecar: Uzbek Navoiy-TTS in the engine's own venv.

Launched as ``<engine venv python> main.py`` by ``NavoiyBackend``. The venv
holds CosyVoice's runtime pinned to transformers 4.51.3 (the parent runs
transformers 5, where this checkpoint's LLM never emits its end-of-speech
token). This file imports nothing from the app.

Wire protocol: identical to the other sidecars (engines/pockettts/main.py) —
length-prefixed JSON frames on a private fd, ``ready`` first, then
``synthesize`` / ``ping`` / ``shutdown``.
"""
from __future__ import annotations

import base64
import json
import os
import struct
import sys
import threading
import time
import traceback
from pathlib import Path

# Mirrors services/subprocess_backend.py::MAX_FRAME_BYTES.
MAX_FRAME_BYTES = 64 * 1024 * 1024
#: The rate the engine reports; a checkpoint that differs gets resampled.
SAMPLE_RATE = 24000
_HEARTBEAT_S = 5.0

#: The checkpoint's ten presets (emotions_40h.json in the model repo, which is
#: Apache-2.0 like the weights).
EMOTIONS: dict[str, str] = {
    "xotirjam": "Speak in a calm, steady, neutral voice with even pacing and relaxed intonation.",
    "xursand": "Speak in a happy, excited and energetic voice with bright rising intonation and lively pacing.",
    "g'amgin": "Speak in a sad, sorrowful voice with low energy, slow pace and a falling, heavy tone.",
    "jahldor": "Speak in an angry voice with sharp, clipped, forceful delivery, loud volume and hard stress.",
    "qo'rqqan": "Speak in a fearful, nervous voice that is shaky and tense, with a higher pitch and uneven breathing.",
    "hayratda": "Speak in a surprised, astonished voice with a sudden sharp rise in pitch and wide-eyed emphasis.",
    "pichirlab": "Speak in a soft, quiet whisper with breathy, low-volume voice and gentle careful articulation.",
    "mehribon": "Speak in a warm, gentle, affectionate voice with soft tone and smooth slow pacing.",
    "charchagan": "Speak in a tired, weary voice with low energy, slow drawn-out pace and sighing breaths.",
    "kinoyali": "Speak in a sarcastic, mocking voice with exaggerated drawl and ironic stress on key words.",
}
DEFAULT_EMOTION = "xotirjam"
_ENDOFPROMPT = "<|endofprompt|>"

_MODEL = None
_send_lock = threading.Lock()


# -- wire protocol -----------------------------------------------------------


def _send(stream, obj: dict) -> None:
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    with _send_lock:
        stream.write(struct.pack("!I", len(body)))
        stream.write(body)
        stream.flush()


def _recv(stream):
    header = stream.read(4)
    if len(header) < 4:
        return None  # EOF
    (n,) = struct.unpack("!I", header)
    if n > MAX_FRAME_BYTES:
        raise IOError(f"frame too large: {n}")
    body = bytearray()
    while len(body) < n:
        chunk = stream.read(n - len(body))
        if not chunk:
            raise IOError("short read")
        body.extend(chunk)
    return json.loads(bytes(body).decode("utf-8"))


def _measure_vram_mb() -> float:
    try:
        import torch

        if torch.cuda.is_available():
            return round(torch.cuda.memory_allocated() / (1024 ** 2), 1)
    except Exception:
        pass
    return 0.0


# -- install layout ----------------------------------------------------------


def _root() -> Path:
    raw = (os.environ.get("OMNIVOICE_NAVOIY_DIR") or "").strip().strip('"')
    if not raw:
        raise RuntimeError(
            "OMNIVOICE_NAVOIY_DIR is not set. Point it at the Navoiy-TTS "
            "install root — see docs/engines/navoiy.md."
        )
    return Path(raw).expanduser()


def _layout(root: Path) -> tuple[Path, Path, Path]:
    """(cosyvoice checkout, CosyVoice2 base, Navoiy checkpoint)."""
    checkout = root / "CosyVoice"
    if not (checkout / "cosyvoice" / "cli" / "cosyvoice.py").is_file():
        checkout = root / "cosyvoice"
    base = root / "base"
    checkpoint = root / "navoiy" / "emotion_600h_joint.pt"
    for path, label in (
        (checkout, "CosyVoice checkout"),
        (base, "CosyVoice2 base weights"),
        (checkpoint, "Navoiy checkpoint"),
    ):
        if not path.exists():
            raise RuntimeError(f"{label} not found at {path} — see docs/engines/navoiy.md.")
    return checkout, base, checkpoint


def _instruct(raw: object) -> str:
    """The instruction prefix: preset name, "[tag]" spelling, or free prose."""
    value = str(raw or "").strip()
    if not value:
        return EMOTIONS[DEFAULT_EMOTION]
    key = value.lower().strip("[]")
    if key in EMOTIONS:
        return EMOTIONS[key]
    return value


# -- model ------------------------------------------------------------------


def _unwrap(value):
    if not isinstance(value, dict):
        return value
    for key in ("state_dict", "model", "llm"):
        nested = value.get(key)
        if isinstance(nested, dict):
            return _unwrap(nested)
    return value


def _build(checkout: Path, base_dir: Path, checkpoint: Path):
    """A CosyVoice2 CLI wrapper over the Navoiy checkpoint.

    ``CosyVoice2.__init__`` loads the base ``llm.pt`` and then refuses a
    mismatched state dict (it loads strictly), so the wrapper is assembled by
    hand: the base flow/vocoder, the Navoiy LLM, and a shell object that
    carries ``inference_instruct2`` (which lives on the CLI class, not on the
    model).
    """
    import torch
    from hyperpyyaml import load_hyperpyyaml

    from cosyvoice.cli.cosyvoice import CosyVoice2 as CosyVoice2CLI
    from cosyvoice.cli.frontend import CosyVoiceFrontEnd
    from cosyvoice.cli.model import CosyVoice2Model

    with open(base_dir / "cosyvoice2.yaml", "r") as handle:
        configs = load_hyperpyyaml(
            handle,
            overrides={"qwen_pretrain_path": str(base_dir / "CosyVoice-BlankEN")},
        )
    frontend = CosyVoiceFrontEnd(
        configs["get_tokenizer"],
        configs["feat_extractor"],
        str(base_dir / "campplus.onnx"),
        str(base_dir / "speech_tokenizer_v2.onnx"),
        str(base_dir / "spk2info.pt"),
        configs["allowed_special"],
    )
    model = CosyVoice2Model(configs["llm"], configs["flow"], configs["hift"], False)
    device = model.device
    flow = torch.load(str(base_dir / "flow.pt"), map_location=device, weights_only=True)
    model.flow.load_state_dict(flow, strict=True)
    model.flow.to(device).eval()
    hift = torch.load(str(base_dir / "hift.pt"), map_location=device, weights_only=True)
    model.hift.load_state_dict(
        {k.replace("generator.", ""): v for k, v in hift.items()}, strict=True
    )
    model.hift.to(device).eval()
    state = _unwrap(torch.load(str(checkpoint), map_location="cpu", weights_only=True))
    # The released checkpoint is bfloat16; the fp32 stack rejects the mismatch.
    state = {
        key: (value.float() if isinstance(value, torch.Tensor) and torch.is_floating_point(value)
              else value)
        for key, value in state.items()
    }
    report = model.llm.load_state_dict(state, strict=False)
    if report.missing_keys:
        print(
            f"navoiy sidecar: {len(report.missing_keys)} checkpoint keys missing",
            file=sys.stderr,
        )
    model.llm.float().to(device).eval()

    voice = CosyVoice2CLI.__new__(CosyVoice2CLI)
    voice.model_dir = str(base_dir)
    voice.fp16 = False
    voice.frontend = frontend
    voice.sample_rate = SAMPLE_RATE
    voice.model = model
    return voice, device


def _load(stdout) -> None:
    """Load once, heartbeating so a slow cold start is not read as a hang."""
    global _MODEL
    if _MODEL is not None:
        return
    _send(stdout, {"op": "progress", "stage": "loading_model", "percent": 0})
    stop = threading.Event()

    def beat() -> None:
        pct = 1
        while not stop.wait(_HEARTBEAT_S):
            pct = min(pct + 1, 99)
            _send(stdout, {"op": "progress", "stage": "loading_model", "percent": pct})

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    started = time.monotonic()
    try:
        root = _root()
        checkout, base_dir, checkpoint = _layout(root)
        for path in (str(checkout), str(checkout / "third_party" / "Matcha-TTS"),
                     str(checkpoint.parent)):
            if path not in sys.path:
                sys.path.insert(0, path)
        _MODEL = _build(checkout, base_dir, checkpoint)
        print(
            f"navoiy sidecar: loaded in {time.monotonic() - started:.1f}s on "
            f"{_MODEL[1]}",
            file=sys.stderr,
        )
    finally:
        stop.set()
        thread.join(timeout=_HEARTBEAT_S + 1)


def _normalize(text: str) -> str:
    """Uzbek number/date expansion when the checkpoint's normalizer is there.

    The parent already normalizes at its text→engine choke point; this covers
    direct API callers and keeps digits from being hallucinated.
    """
    try:
        from uztts.normalize import normalize  # type: ignore[import-not-found]

        return normalize(text, mode="infer")
    except Exception:
        return text


def _babbled(text: str, seconds: float) -> bool:
    """True when `seconds` is far too long to be `text` read out.

    Measured on this checkpoint: 12 Uzbek words took 3.5–4.8 s, about 0.06 s
    per character; 0.16 s/char plus three seconds keeps every real take.
    """
    return seconds > 0.16 * len(text) + 3.0


def _synthesize(msg: dict, stdout) -> None:
    import torch

    text = msg.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("synthesize: missing or non-string 'text'")
    ref_audio = msg.get("ref_audio")
    if not ref_audio:
        raise ValueError(
            "Navoiy-TTS needs a reference recording (it has no built-in voices)"
        )
    _load(stdout)
    voice, _device = _MODEL

    instruction = _instruct(msg.get("instruct") or msg.get("emo_text")
                            or msg.get("emotion"))
    if not instruction.endswith(_ENDOFPROMPT):
        instruction = instruction.strip() + _ENDOFPROMPT
    try:
        speed = float(msg.get("speed") or 1.0)
    except (TypeError, ValueError):
        speed = 1.0
    speed = min(2.0, max(0.5, speed))

    spoken = _normalize(text)
    _send(stdout, {"op": "progress", "stage": "generating", "percent": 0})

    chunks = []
    seconds = 0.0
    for attempt in range(1, 3):
        chunks = []
        with torch.inference_mode():
            for result in voice.inference_instruct2(
                spoken, instruction, str(ref_audio), stream=False, speed=speed
            ):
                chunks.append(result["tts_speech"].detach().cpu())
        if not chunks:
            raise RuntimeError("the model returned no audio")
        wave = torch.cat(chunks, dim=1)
        seconds = wave.shape[-1] / SAMPLE_RATE
        if not _babbled(spoken, seconds):
            break
        print(
            f"navoiy sidecar: take {attempt} ran on ({seconds:.1f}s for "
            f"{len(spoken)} chars), retrying",
            file=sys.stderr,
        )
    else:
        raise RuntimeError(
            f"Navoiy-TTS produced {seconds:.1f}s for {len(spoken)} characters "
            "twice — the take never reached its end-of-speech"
        )

    array = wave.squeeze(0).numpy()
    import numpy as np

    pcm = (np.clip(array, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
    _send(stdout, {
        "op": "audio",
        "audio_pcm_b64": base64.b64encode(pcm).decode("ascii"),
        "sample_rate": SAMPLE_RATE,
        "n_samples": int(array.shape[-1]),
    })


# -- main loop ---------------------------------------------------------------


def main() -> int:
    stdin = sys.stdin.buffer
    # Frames go down a private fd and fd 1 is pointed at stderr (#1428):
    # CosyVoice's libraries print freely to stdout and would corrupt framing.
    frame_fd = os.dup(1)
    os.dup2(2, 1)
    stdout = os.fdopen(frame_fd, "wb")

    _send(stdout, {"op": "ready", "engine": "navoiy", "sample_rate": SAMPLE_RATE})

    while True:
        try:
            msg = _recv(stdin)
        except Exception as exc:
            _send(stdout, {
                "op": "error",
                "stage": "recv",
                "message": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            })
            return 1
        if msg is None:
            return 0

        op = msg.get("op") if isinstance(msg, dict) else None
        try:
            if op == "ping":
                _send(stdout, {"op": "pong", "vram_mb": _measure_vram_mb()})
            elif op == "synthesize":
                _synthesize(msg, stdout)
            elif op == "shutdown":
                # torch's teardown can outlast the parent's shutdown wait; skip
                # it so the slot is released promptly.
                os._exit(0)
            else:
                _send(stdout, {
                    "op": "error",
                    "stage": "dispatch",
                    "message": f"unknown op: {op!r}",
                })
        except Exception as exc:
            _send(stdout, {
                "op": "error",
                "stage": op or "unknown",
                "message": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            })


if __name__ == "__main__":
    sys.exit(main())
