"""The TTS model is ready before the click, not loaded after it.

Measured 2026-11-23 on the owner's machine: a warm take took 4-7 s, but the
first take after launch or after the 15-minute idle unload took 30-168 s —
the checkpoint and the Python environment sit on a spinning disk, and the
first synthesis also paid CUDA kernel selection, the take guard's lazy imports
and the AudioSeal load. Two fixes, both tested here:

* ``POST /tts/warm`` (pinged while the speech screens are open and focused)
  keeps the model resident, or starts the guarded background preload;
* the preload walks the whole generate path once (``services.tts_warmup``).
"""
from __future__ import annotations

import asyncio
import importlib
import types

import pytest
import torch

# Resolved per test, not at collection: other suites reload these modules, and
# a stale module object would take the patches while the route reads the live one.
generation = model_manager = tts_warmup = None


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    global generation, model_manager, tts_warmup
    generation = importlib.import_module("api.routers.generation")
    model_manager = importlib.import_module("services.model_manager")
    tts_warmup = importlib.import_module("services.tts_warmup")
    monkeypatch.setattr(generation, "_warm_task", None)
    monkeypatch.setattr(generation, "_routing_decision", lambda: types.SimpleNamespace(remote=False))
    tts_warmup.forget_model()
    yield
    tts_warmup.forget_model()


def _engine(monkeypatch, engine_id: str):
    tts_backend = importlib.import_module("services.tts_backend")
    monkeypatch.setattr(tts_backend, "active_backend_id", lambda: engine_id)


def test_warm_keeps_a_resident_model_from_idling_out(monkeypatch):
    _engine(monkeypatch, "omnivoice")
    monkeypatch.setattr(model_manager, "model", object())
    monkeypatch.setattr(model_manager, "_last_used", 0.0)

    assert asyncio.run(generation.warm_tts()) == {"engine": "omnivoice", "state": "ready"}
    assert model_manager._last_used > 0.0


def test_warm_starts_one_background_load_for_an_unloaded_model(monkeypatch):
    _engine(monkeypatch, "omnivoice")
    monkeypatch.setattr(model_manager, "model", None)
    calls = []

    async def preload():
        calls.append(1)
        await asyncio.sleep(0.05)

    monkeypatch.setattr(model_manager, "preload_model", preload)

    async def two_pings():
        first = await generation.warm_tts()
        second = await generation.warm_tts()  # while the first load still runs
        await generation._warm_task
        return first, second

    first, second = asyncio.run(two_pings())
    assert first["state"] == second["state"] == "loading"
    assert calls == [1]


def test_warm_never_loads_the_native_model_for_another_engine(monkeypatch):
    _engine(monkeypatch, "navoiy")
    monkeypatch.setattr(model_manager, "model", None)
    monkeypatch.setattr(model_manager, "preload_model", lambda: pytest.fail("loaded Sado for navoiy"))

    assert asyncio.run(generation.warm_tts())["state"] == "unsupported"


def test_warm_does_nothing_locally_for_a_remote_render(monkeypatch):
    _engine(monkeypatch, "omnivoice")
    monkeypatch.setattr(generation, "_routing_decision", lambda: types.SimpleNamespace(remote=True))
    monkeypatch.setattr(model_manager, "model", None)
    monkeypatch.setattr(model_manager, "preload_model", lambda: pytest.fail("warmed the wrong box"))

    assert asyncio.run(generation.warm_tts())["state"] == "remote"


class FakeModel:
    sampling_rate = 24000

    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        t = torch.arange(24000, dtype=torch.float32) / 24000
        return [torch.sin(2 * torch.pi * 150 * t).unsqueeze(0) * 0.3]


def test_warmup_walks_synthesis_guard_chain_and_watermark_once(monkeypatch):
    seen = []
    import services.audio_dsp as dsp
    import services.take_guard as guard
    import services.watermark as wm

    monkeypatch.setattr(guard, "take_deviation", lambda audio, sr, ref: seen.append("guard") or (0.0, 10.0))
    monkeypatch.setattr(dsp, "finalize_output", lambda audio, sr, preset, **_: seen.append(preset) or audio)
    monkeypatch.setattr(wm, "mark_synthetic", lambda audio, sr, **_: seen.append("mark") or audio)
    monkeypatch.setattr(wm, "can_mark_offline", lambda: True)
    model = FakeModel()

    assert tts_warmup.warm_generate_path(model) is True
    assert model.calls[0]["num_step"] == tts_warmup.WARM_STEPS
    assert seen == ["guard", "natural", "mark"]
    assert tts_warmup.warm_generate_path(model) is False  # once per loaded model
    assert len(model.calls) == 1

    tts_warmup.forget_model()  # an unload
    assert tts_warmup.warm_generate_path(model) is True


def test_warmup_never_fetches_the_watermark_model(monkeypatch):
    import services.watermark as wm

    monkeypatch.setattr(wm, "can_mark_offline", lambda: False)
    monkeypatch.setattr(wm, "mark_synthetic", lambda *a, **k: pytest.fail("would download AudioSeal"))

    assert tts_warmup.warm_generate_path(FakeModel()) is True


def test_warmup_failure_is_silent(monkeypatch):
    class Broken(FakeModel):
        def generate(self, **kwargs):
            raise RuntimeError("CUDA out of memory")

    assert tts_warmup.warm_generate_path(Broken()) is False


def test_unload_forgets_the_warmed_model(monkeypatch):
    model = FakeModel()
    monkeypatch.setattr(tts_warmup, "_warmed_model_id", id(model))
    monkeypatch.setattr(model_manager, "model", model)
    monkeypatch.setattr(model_manager, "free_vram", lambda: None)
    monkeypatch.setattr(model_manager, "release_tts_side_caches", lambda: None)

    assert model_manager.unload_shared_model() is True
    assert tts_warmup._warmed_model_id is None


def test_preload_walks_the_generate_path_after_loading(monkeypatch):
    loaded = FakeModel()
    warmed = []
    monkeypatch.setattr(model_manager, "model", None)
    monkeypatch.setattr(model_manager, "_headless_worker", lambda: False)
    monkeypatch.setattr(model_manager, "_checkpoint_in_local_cache", lambda _c: True)

    async def load():
        return loaded

    async def warm(model):
        warmed.append(model)

    monkeypatch.setattr(model_manager, "_load_model_with_timeout", load)
    monkeypatch.setattr(model_manager, "_warm_generate_path", warm)
    monkeypatch.setattr(model_manager, "_model_lock", asyncio.Lock())

    from core import device_caps

    monkeypatch.setattr(device_caps, "detect_host_caps", lambda: types.SimpleNamespace(family="cuda"))
    asyncio.run(model_manager.preload_model())
    assert warmed == [loaded]
