"""Walk the whole /generate path once, right after the TTS model loads.

Loading the weights is only part of a cold first take. The first synthesis
also pays for CUDA kernel selection, the lazy imports behind the take guard's
pitch measurement and the output chain, and the AudioSeal watermark model —
none of which the weight preload touched. On an install whose Python
environment sits on a spinning disk those imports read thousands of small files:
the owner's first take of 2026-11-23 spent ~117 s before synthesis even began
and 168 s in total, while the same take warm took 6 s.

So the preload finishes the job: one tiny synthesis (two decoding steps), the
take-guard measurement, the ``natural`` output chain and a watermark embed, all
thrown away. It runs once per loaded model, in the background, and never raises.
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("omnivoice.tts_warmup")

#: Long enough to give the take guard voiced speech to measure, short enough to
#: cost well under a second on a GPU.
WARM_TEXT = "Salom, bu sinov."
WARM_STEPS = 2

_lock = threading.Lock()
_warmed_model_id: int | None = None


def warm_generate_path(model) -> bool:
    """Run the throwaway take through ``model``; True when it ran now.

    Blocking — call it on the GPU pool, like any synthesis. A model that was
    already warmed returns False at once, so repeated preloads cost nothing.
    """
    global _warmed_model_id
    if model is None:
        return False
    with _lock:
        if _warmed_model_id == id(model):
            return False
        _warmed_model_id = id(model)
    started = time.perf_counter()
    try:
        import torch

        with torch.inference_mode():
            audio = model.generate(text=WARM_TEXT, language="uz", num_step=WARM_STEPS)[0]
        sample_rate = int(getattr(model, "sampling_rate", 24000) or 24000)
        audio = audio.detach().float().cpu().reshape(1, -1)

        from services import watermark
        from services.audio_dsp import finalize_output
        from services.take_guard import take_deviation

        take_deviation(audio, sample_rate, 120.0)
        audio = finalize_output(audio, sample_rate, "natural")
        # Only a checkpoint already on disk: a background warmup must never
        # turn into a download (the first real take fetches it, as before).
        if watermark.can_mark_offline():
            watermark.mark_synthetic(audio, sample_rate, context="tts_warmup")
    except Exception:  # noqa: BLE001 — a warmup must never surface as a failure
        logger.debug("Generate-path warmup failed; the first take will pay its own way",
                     exc_info=True)
        return False
    logger.info("Generate path warmed in %.1fs (kernels, take guard, output chain, watermark)",
                time.perf_counter() - started)
    return True


def forget_model() -> None:
    """Called on unload so the next load of the same object id warms again."""
    global _warmed_model_id
    with _lock:
        _warmed_model_id = None
