"""Word-by-word intonation editing of a finished take.

``POST /audio/{id}/words`` places the script's words on the take and reports
each word's pitch; ``POST /audio/{id}/intonation`` raises or lowers chosen
words and either returns the result to listen to or saves it as a new take
next to the original. See ``services.intonation`` for the signal work.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import sqlite3
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core import event_bus
from core.db import db_conn, ensure_schema
from services.intonation import MAX_SHIFT

router = APIRouter()
logger = logging.getLogger("omnivoice.intonation")

_AUDIO_ID = re.compile(r"[0-9a-f]{8}")
#: Wall-clock bound on the word-timing pass; past it the editor still opens
#: with the acoustic estimate instead of waiting on a cold ASR load.
_WORDS_ASR_TIMEOUT_S = 90.0
_MAX_WORDS_TEXT = 5000
_MAX_EDITS = 2000


def _take_path(audio_id: str) -> str:
    from api.routers.generation import _safe_output_path

    if not _AUDIO_ID.fullmatch(audio_id or ""):
        raise HTTPException(status_code=404, detail="Audio file not found")
    path = _safe_output_path(f"{audio_id}.wav")
    if path is None or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    return path


def _load(path: str):
    import soundfile as sf

    samples, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    return samples.T, sample_rate


class WordsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=_MAX_WORDS_TEXT)
    #: The take's language (picker name or ISO code) for the recogniser.
    language: Optional[str] = None


@router.post("/audio/{audio_id}/words")
async def take_words(audio_id: str, request: WordsRequest):
    """The script's words on the take with their ``start``/``end`` seconds.
    ``approximate`` is true when no local ASR model could time the words and
    syllables were counted instead."""
    from services import intonation
    from services.asr_backend import transcribe_words

    path = _take_path(audio_id)
    samples, sample_rate = await asyncio.to_thread(_load, path)
    duration = samples.shape[-1] / sample_rate
    heard = None
    try:
        heard = await asyncio.wait_for(
            asyncio.to_thread(transcribe_words, path, language=request.language),
            _WORDS_ASR_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning("word timing for %s exceeded %.0fs; estimating", audio_id, _WORDS_ASR_TIMEOUT_S)
    if heard:
        spans = intonation.spans_from_asr(request.text, heard, duration)
    else:
        spans = await asyncio.to_thread(intonation.word_spans, samples, sample_rate, request.text)
    if not spans:
        raise HTTPException(status_code=422, detail="The script has no words to edit.")
    return {
        "duration": round(duration, 3),
        "approximate": not heard,
        "words": [
            {"text": s.text, "start": s.start, "end": s.end} for s in spans
        ],
    }


class WordEdit(BaseModel):
    start: float = Field(..., ge=0)
    end: float = Field(..., ge=0)
    semitones: float = Field(..., ge=-MAX_SHIFT, le=MAX_SHIFT)


class IntonationRequest(BaseModel):
    edits: list[WordEdit] = Field(..., max_length=_MAX_EDITS)
    #: False: return the edited audio to listen to. True: store it as a new
    #: take beside the original (the original is never overwritten).
    save: bool = False


@router.post("/audio/{audio_id}/intonation")
async def edit_take_intonation(audio_id: str, request: IntonationRequest):
    from services import intonation
    from services.generation_audio import save_generation_wav
    from services.audio_io import _safe_soundfile_write
    from services.watermark import mark_synthetic_async
    import torch

    path = _take_path(audio_id)
    if not any(edit.semitones for edit in request.edits):
        raise HTTPException(status_code=422, detail="Move at least one word up or down first.")
    for edit in request.edits:
        if edit.end < edit.start:
            raise HTTPException(status_code=422, detail="A word ends before it starts.")
    samples, sample_rate = await asyncio.to_thread(_load, path)
    edited = await asyncio.to_thread(
        intonation.apply_word_pitch, samples, sample_rate,
        [(e.start, e.end, e.semitones) for e in request.edits],
    )
    # The edit re-renders synthetic speech, so it leaves the app through the
    # same provenance chokepoint as every other take (#1169).
    waveform = await mark_synthetic_async(
        torch.from_numpy(edited), sample_rate, context="intonation-edit",
    )
    if not request.save:
        buffer = io.BytesIO()
        _safe_soundfile_write(buffer, waveform.numpy().T, sample_rate, format="WAV")
        return Response(buffer.getvalue(), media_type="audio/wav", headers={"Cache-Control": "no-store"})

    from api.routers.generation import _safe_output_path

    new_id = uuid.uuid4().hex[:8]
    new_name = f"{new_id}.wav"
    new_path = _safe_output_path(new_name)
    await asyncio.to_thread(save_generation_wav, new_path, waveform, sample_rate)
    duration = round(waveform.shape[-1] / sample_rate, 2)

    def write_history():
        with db_conn() as conn:
            source = conn.execute(
                "SELECT text, mode, language, instruct, profile_id, seed, design_recipe "
                "FROM generation_history WHERE audio_path=? ORDER BY created_at DESC LIMIT 1",
                (f"{audio_id}.wav",),
            ).fetchone()
            row = dict(source) if source else {}
            conn.execute(
                "INSERT INTO generation_history (id, text, mode, language, instruct, profile_id, "
                "audio_path, duration_seconds, generation_time, seed, design_recipe, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_id, row.get("text") or "", row.get("mode") or "clone",
                 row.get("language") or "Auto", row.get("instruct") or "", row.get("profile_id"),
                 new_name, duration, 0.0, row.get("seed"), row.get("design_recipe"), time.time()),
            )

    try:
        await asyncio.to_thread(write_history)
    except sqlite3.OperationalError:
        await asyncio.to_thread(ensure_schema)
        await asyncio.to_thread(write_history)
    event_bus.emit("generation_history", {"action": "created", "id": new_id})
    return {"id": new_id, "audio_path": new_name, "duration_seconds": duration}
