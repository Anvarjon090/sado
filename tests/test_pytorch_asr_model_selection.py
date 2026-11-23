"""A transformers Whisper checkpoint can be picked in the catalogue (Sado ASR v1).

`aisha-org/sado-asr-v1` is an Uzbek fine-tune of Whisper large-v3 published in
transformers format, which only the PyTorch Whisper engine loads. Before this,
that engine read its model from an environment variable alone, so a catalogue
pick could install the weights but never use them.
"""
from __future__ import annotations

import importlib
import types

import pytest
from fastapi import HTTPException

SADO_ASR = "aisha-org/sado-asr-v1"


@pytest.fixture
def env(monkeypatch):
    engines = importlib.import_module("api.routers.engines")
    asr = importlib.import_module("services.asr_backend")
    setup_models = importlib.import_module("api.routers.setup.models")
    prefs = importlib.import_module("core.prefs")
    store: dict = {}
    monkeypatch.setattr(prefs, "set_", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr(prefs, "is_env_shadowed", lambda name: False)
    monkeypatch.setattr(
        prefs, "resolve",
        lambda key, env=None, default=None: store.get(key, default),
    )
    # select_pytorch_whisper_model writes os.environ; setenv first so the
    # teardown removes what the selection wrote (a bare delenv of an absent
    # variable records nothing to undo, and the pick leaked into later tests).
    monkeypatch.setenv("OMNIVOICE_PYTORCH_ASR_MODEL", "unset")
    monkeypatch.delenv("OMNIVOICE_PYTORCH_ASR_MODEL")
    monkeypatch.setattr(asr, "list_backends", lambda: [
        {"id": "pytorch-whisper", "available": True, "routing_status": "accelerated"},
        {"id": "faster-whisper", "available": True, "routing_status": "accelerated"},
    ])
    monkeypatch.setattr(asr, "active_backend_id", lambda: store.get("asr_backend", "faster-whisper"))
    monkeypatch.setattr(setup_models, "is_cached", lambda repo: True)
    return types.SimpleNamespace(engines=engines, asr=asr, store=store, setup_models=setup_models)


def _select(env, backend_id, model_id):
    req = env.engines.SelectEngineRequest(family="asr", backend_id=backend_id, model_id=model_id)
    return env.engines.select_engine(req)


def test_sado_asr_is_in_the_catalogue_for_the_pytorch_engine(env):
    entry = next(m for m in env.setup_models.KNOWN_MODELS if m["repo_id"] == SADO_ASR)
    assert entry["role"] == "ASR"
    assert entry["engines"] == ["pytorch-whisper"]
    assert entry["gated"] is True and entry["requires_hf_token"] is True
    assert entry["access_url"].endswith(SADO_ASR)


def test_picking_it_switches_the_engine_and_the_model(env, monkeypatch):
    result = _select(env, "pytorch-whisper", SADO_ASR)
    assert env.store["asr_model_pytorch"] == SADO_ASR
    assert env.asr.pytorch_whisper_model_id() == SADO_ASR
    assert env.asr.PyTorchWhisperBackend._model_name() == SADO_ASR
    assert result["active"] is not None


def test_an_uninstalled_pick_is_refused(env, monkeypatch):
    monkeypatch.setattr(env.setup_models, "is_cached", lambda repo: False)
    with pytest.raises(HTTPException) as caught:
        _select(env, "pytorch-whisper", SADO_ASR)
    assert caught.value.status_code == 409
    assert "asr_model_pytorch" not in env.store


@pytest.mark.parametrize("model_id", ["Systran/faster-whisper-large-v3", "nobody/unknown"])
def test_a_non_transformers_checkpoint_is_refused(env, model_id):
    with pytest.raises(HTTPException) as caught:
        _select(env, "pytorch-whisper", model_id)
    assert caught.value.status_code == 400


def test_the_ctranslate2_route_still_refuses_sado_asr(env):
    with pytest.raises(HTTPException):
        _select(env, "faster-whisper", SADO_ASR)


def test_a_loaded_pipeline_rebuilds_for_a_new_pick(env, monkeypatch):
    built = []

    def fake_pipeline(model, dtype, device):
        built.append(model)
        return types.SimpleNamespace(model=types.SimpleNamespace(name_or_path=model))

    freed = []
    mm = importlib.import_module("services.model_manager")
    monkeypatch.setattr(mm, "free_vram", lambda: freed.append(True))
    monkeypatch.setattr(env.asr.PyTorchWhisperBackend, "_new_pipeline", staticmethod(fake_pipeline))
    monkeypatch.setattr(env.asr, "_local_model_source", lambda name: name)
    monkeypatch.setattr(env.asr.PyTorchWhisperBackend, "_pick_device", classmethod(lambda cls, name=None: "cpu"))
    backend = env.asr.PyTorchWhisperBackend()
    backend._ensure_pipe()
    backend._ensure_pipe()  # same model: reused
    env.store["asr_model_pytorch"] = SADO_ASR
    backend._ensure_pipe()  # catalogue pick after the build: rebuilt
    assert built == ["openai/whisper-large-v3-turbo", SADO_ASR]
    assert freed == [True]  # the old model's memory is handed back first


def test_a_borrowed_pipeline_is_never_replaced(env):
    borrowed = object()
    backend = env.asr.PyTorchWhisperBackend(asr_pipe=borrowed)
    env.store["asr_model_pytorch"] = SADO_ASR
    backend._ensure_pipe()
    assert backend._pipe is borrowed
