"""Navoiy-TTS sidecar package — Uzbek expressive TTS (CosyVoice2 fine-tune).

`aisha-org/navoiy-tts` (Apache-2.0) is CosyVoice2-0.5B fine-tuned on ~640 h of
Uzbek speech (600 h neutral + 40 h expressive). It speaks Uzbek with Uzbek
phonetics rather than borrowing a neighbouring language's, clones a voice from
a 3–10 s reference, and takes ten emotion presets through an English
instruction prefix (``xotirjam``, ``xursand``, ``g'amgin``, ``jahldor``,
``qo'rqqan``, ``hayratda``, ``pichirlab``, ``mehribon``, ``charchagan``,
``kinoyali``).

Why its own process *and* its own venv: the checkpoint needs
``transformers==4.51.3``. Under transformers 5 the model's LLM never emits its
end-of-speech token and the output degenerates into repeated syllables (heard
2026-11-06 as "ba-ba-ba"); the parent runs transformers 5. That is the same
shape of conflict IndexTTS and MOSS-TTS-v1.5 have, and it is solved the same
way — ``SubprocessBackend`` with ``OMNIVOICE_NAVOIY_DIR`` pointing at the
user's install (see ``bootstrap.py`` for the expected layout).

Defined here rather than in ``services.tts_backend`` to break the import cycle
(``services.subprocess_backend`` imports ``TTSBackend`` from there).
"""
from __future__ import annotations

import math
import os
from typing import TYPE_CHECKING

from services.subprocess_backend import SubprocessBackend

if TYPE_CHECKING:
    import torch  # noqa: F401

#: The ten presets the checkpoint ships, in the model's own names.
EMOTIONS: tuple[str, ...] = (
    "xotirjam",
    "xursand",
    "g'amgin",
    "jahldor",
    "qo'rqqan",
    "hayratda",
    "pichirlab",
    "mehribon",
    "charchagan",
    "kinoyali",
)

#: CosyVoice2 speaks at 24 kHz; the sidecar resamples if a checkpoint differs.
SAMPLE_RATE = 24000


class NavoiyBackend(SubprocessBackend):
    """Navoiy-TTS (Uzbek, CosyVoice2 clone, 10 emotions, Apache-2.0).

    Runs in a long-lived sidecar in its own venv. The first synthesize
    cold-loads the base model plus the 2.0 GB checkpoint (~30 s on a 2070);
    later calls reuse the process.

    Setup (see docs/engines/navoiy.md)::

        OMNIVOICE_NAVOIY_DIR=D:/omni-navoiy

    The folder holds ``CosyVoice/`` (checkout at 074ca6dc + Matcha-TTS),
    ``base/`` (FunAudioLLM/CosyVoice2-0.5B) and
    ``navoiy/emotion_600h_joint.pt``, plus a ``.venv`` with that checkout's
    runtime (transformers 4.51.3, torch 2.7).
    """

    id = "navoiy"
    display_name = "Navoiy-TTS (Uzbek, 10 emotions, Apache-2.0)"
    #: No built-in speakers: the checkpoint clones from a reference clip.
    #: Voice Design therefore needs a reference too, so it is refused up front.
    supports_voice_design = False
    supports_cloning = True
    #: Graded emotion is this engine's headline feature (`emo_text` / `instruct`).
    supports_emotion = True
    #: CosyVoice's inference path is CUDA-first; CPU works but is ~5x slower.
    gpu_compat = ("cuda", "cpu")
    #: 0.5B base + the LLM checkpoint in fp32 sits near 3.5 GB once loaded.
    min_vram_gb = 4.0
    _DEFAULT_SAMPLE_RATE = SAMPLE_RATE

    # ── availability ───────────────────────────────────────────────────────

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        # Never import torch/cosyvoice here: the parent pins transformers 5 and
        # co-importing this engine's stack is exactly what the venv prevents.
        from engines.navoiy import bootstrap

        if not bootstrap.is_installed():
            return False, bootstrap.missing_message()
        if not bootstrap.NAVOIY_SIDECAR_SCRIPT.is_file():
            return False, (
                "Navoiy-TTS sidecar script missing at "
                f"{bootstrap.NAVOIY_SIDECAR_SCRIPT} — reinstall Sado."
            )
        return True, "ready (Uzbek only, reference clip required)"

    @classmethod
    def venv_python(cls):
        from engines.navoiy import bootstrap

        python = bootstrap.venv_python()
        if python is None:
            raise RuntimeError(
                "Navoiy-TTS's environment is missing. Set OMNIVOICE_NAVOIY_DIR "
                "and create its venv — see docs/engines/navoiy.md."
            )
        return python

    @classmethod
    def sidecar_script(cls):
        from engines.navoiy import bootstrap

        return bootstrap.NAVOIY_SIDECAR_SCRIPT

    @property
    def recv_timeout_s(self) -> float:
        """Deadline for a sidecar frame; the cold load alone is ~30 s."""
        try:
            value = float(os.environ.get("OMNIVOICE_NAVOIY_RECV_TIMEOUT_S", "900"))
        except (TypeError, ValueError):
            return 900.0
        if not math.isfinite(value):
            return 900.0
        return max(60.0, value)

    # ── TTSBackend protocol ────────────────────────────────────────────────

    @property
    def sample_rate(self) -> int:
        return self._DEFAULT_SAMPLE_RATE

    @property
    def supported_languages(self) -> list[str]:
        # The checkpoint is Uzbek-only. Declaring that here is what makes a
        # request for another language fail with the standard "engine can't
        # speak X" message instead of Uzbek-accented English.
        return ["uz"]

    @property
    def language_display_names(self) -> dict[str, str]:
        return {"uz": "Uzbek"}

    def model_identity(self) -> str:
        return "Navoiy-TTS (Uzbek)"

    # ── generate (parent-side arbitration) ─────────────────────────────────

    def generate(self, text: str, **kw) -> "torch.Tensor":
        """Synthesize Uzbek ``text`` in the reference voice.

        kwargs honored:
          * ``ref_audio`` — path to the voice's recording. Required: the
            checkpoint has no speakers of its own, so a request without one is
            refused with a message the UI can show.
          * ``ref_text``  — accepted but unused; the instruction, not the
            transcript, steers this model.
          * ``emo_text``  — a preset name (see :data:`EMOTIONS`) or a written
            description; the sidecar maps it to the checkpoint's instruction.
          * ``instruct``  — free-form instruction (takes precedence over
            ``emo_text``), which is how the dub director's tone reaches it.
          * ``speed``     — 0.5–2.0 duration scale.
        """
        from services.tts_backend import TTSInputError

        ref_audio = kw.get("ref_audio")
        if not ref_audio:
            raise TTSInputError(
                "Navoiy-TTS speaks in a cloned voice, so it needs a reference "
                "recording: pick a voice that has one (Model Catalogue → "
                "Voices), or switch engine for this request."
            )

        forwarded: dict = {"ref_audio": str(ref_audio)}
        for key in ("ref_text", "instruct", "emo_text", "emotion"):
            value = kw.get(key)
            if value:
                forwarded[key] = str(value)
        speed = kw.get("speed")
        if speed is not None:
            try:
                forwarded["speed"] = float(speed)
            except (TypeError, ValueError):
                pass
        language = kw.get("language")
        if language:
            forwarded["language"] = str(language)

        return super().generate(text, **forwarded)


__all__ = ["EMOTIONS", "NavoiyBackend", "SAMPLE_RATE"]
