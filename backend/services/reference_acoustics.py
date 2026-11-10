"""Should this clone reference carry OmniVoice's ``<|denoise|>`` token?

The token tells the model to synthesize *clean* speech regardless of the
reference's acoustics. On a noisy phone clip that is the right call; on a
clean recording it throws away the very thing a listener hears as a real
room and a real microphone — measured on a 38 dB SNR Uzbek reference, the
token cost 0.7 LU of loudness range and moved the spectrum away from the
original. So the default is decided per reference from its signal-to-noise
ratio, not fixed to ``True``; a request that sets ``denoise`` explicitly is
always honoured.

Measurement reuses :mod:`services.voice_intake` (frame-level speech/noise
levels) and is cached per file identity, so a profile's reference is
analysed once, not once per generate.
"""
from __future__ import annotations

import logging
import os
import tempfile
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("omnivoice.reference_acoustics")

#: Below this SNR the reference is treated as noisy and the model is asked to
#: clean up; at or above it the recording's own acoustics are kept.
DENOISE_BELOW_SNR_DB = 28.0


def reference_snr_db(path: str | None) -> float | None:
    """Speech-to-floor SNR of the reference in dB, or ``None`` when the clip
    cannot be read (missing file, undecodable container)."""
    if not path:
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return _snr_cached(os.fspath(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=64)
def _snr_cached(path: str, _mtime_ns: int, _size: int) -> float | None:
    import soundfile as sf

    from services import voice_intake as vi

    try:
        try:
            samples, sample_rate = sf.read(path, dtype="float32", always_2d=True)
        except Exception:  # noqa: BLE001 — not a WAV/FLAC/OGG soundfile reads; decode via ffmpeg
            from services.ffmpeg_utils import find_ffmpeg

            ffmpeg = find_ffmpeg()
            if not ffmpeg:
                return None
            with tempfile.TemporaryDirectory() as tmp:
                decoded = Path(tmp) / "ref.wav"
                vi.decode(ffmpeg, Path(path), decoded)
                samples, sample_rate = sf.read(str(decoded), dtype="float32", always_2d=True)
        if samples.shape[0] < sample_rate // 10:
            return None
        return float(vi.analyze(samples, sample_rate).snr_db)
    except Exception:
        logger.debug("reference SNR measurement failed", exc_info=True)
        return None


def reference_wants_denoise(path: str | None) -> bool:
    """``True`` when the reference is noisy (or unmeasurable) and the model
    should be asked for clean output; ``False`` for a clean recording whose
    acoustics are worth keeping. Voice design (no reference) never needs the
    token — the model only emits it alongside reference tokens anyway."""
    if not path:
        return False
    snr = reference_snr_db(path)
    if snr is None:
        return True
    return snr < DENOISE_BELOW_SNR_DB
