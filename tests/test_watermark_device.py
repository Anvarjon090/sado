"""The AudioSeal watermark runs on the GPU when there is one.

On the CPU it cost about 0.1 s per second of audio — 0.6 s on a 6 s take and
3.1 s on a 30 s one (i7-9700K, 2026-11-23), a fifth of a whole /generate. The
generator is a small conv net, so a CUDA GPU that already holds the TTS model
marks the same take in milliseconds. A GPU failure must still mark the take, on
the CPU, and keep later takes off the GPU.
"""
from __future__ import annotations

import sys
import types

import pytest
import torch

from services import watermark

SR = 16000


class FakeGenerator:
    """Stands in for AudioSeal's generator: records moves, marks by doubling."""

    def __init__(self):
        self.moves: list[str] = []

    def eval(self):
        return self

    def to(self, device):
        self.moves.append(str(device))
        return self

    def __call__(self, audio, sample_rate, message=None):
        return audio * 2.0


@pytest.fixture
def clean_state(monkeypatch):
    monkeypatch.setattr(watermark, "_generator", None)
    monkeypatch.setattr(watermark, "_generator_device", "cpu")
    monkeypatch.setattr(watermark, "_cuda_embed_failed", False)
    monkeypatch.setattr(watermark, "_audioseal_available", True)
    monkeypatch.delenv("OMNIVOICE_WATERMARK_DEVICE", raising=False)


def _host(monkeypatch, family: str, cuda: bool | None = None):
    """The host probe's device family (honours a pinned device) and torch's view."""
    from core import device_caps

    monkeypatch.setattr(device_caps, "detect_host_caps", lambda: types.SimpleNamespace(family=family))
    monkeypatch.setattr(torch.cuda, "is_available", lambda: family in ("cuda", "rocm") if cuda is None else cuda)


def _fake_audioseal(monkeypatch, generator):
    module = types.ModuleType("audioseal")
    module.AudioSeal = types.SimpleNamespace(load_generator=lambda _name: generator)
    monkeypatch.setitem(sys.modules, "audioseal", module)


@pytest.mark.parametrize("family", ["cuda", "rocm"])
def test_gpu_hosts_mark_on_the_gpu(clean_state, monkeypatch, family):
    _host(monkeypatch, family)
    assert watermark._watermark_device() == "cuda"


@pytest.mark.parametrize("family", ["cpu", "mps", "xpu"])
def test_other_hosts_mark_on_the_cpu(clean_state, monkeypatch, family):
    _host(monkeypatch, family, cuda=False)
    assert watermark._watermark_device() == "cpu"


def test_a_pinned_cpu_device_is_honoured_even_with_a_gpu_present(clean_state, monkeypatch):
    _host(monkeypatch, "cpu", cuda=True)  # OMNIVOICE_DEVICE=cpu on a CUDA box
    assert watermark._watermark_device() == "cpu"


def test_env_keeps_the_cpu_path(clean_state, monkeypatch):
    _host(monkeypatch, "cuda")
    monkeypatch.setenv("OMNIVOICE_WATERMARK_DEVICE", "cpu")
    assert watermark._watermark_device() == "cpu"


def test_loaded_generator_moves_to_the_gpu(clean_state, monkeypatch):
    gen = FakeGenerator()
    _fake_audioseal(monkeypatch, gen)
    _host(monkeypatch, "cuda")

    assert watermark._get_generator() is gen
    assert gen.moves == ["cuda"]
    assert watermark._generator_device == "cuda"


def test_gpu_failure_marks_on_the_cpu_and_stays_there(clean_state, monkeypatch):
    gen = FakeGenerator()
    monkeypatch.setattr(watermark, "_generator", gen)
    monkeypatch.setattr(watermark, "_generator_device", "cuda")
    real_embed_on = watermark._embed_on

    def embed_on(generator, device, audio, sample_rate, msg):
        if device != "cpu":
            raise RuntimeError("CUDA error: no kernel image is available")
        return real_embed_on(generator, device, audio, sample_rate, msg)

    monkeypatch.setattr(watermark, "_embed_on", embed_on)
    wave = torch.randn(1, SR * 2)

    out = watermark.embed_watermark(wave, SR, force=True)

    assert torch.equal(out, wave * 2.0)  # marked, not passed through
    assert gen.moves == ["cpu"]
    assert watermark._generator_device == "cpu"
    _host(monkeypatch, "cuda")
    assert watermark._watermark_device() == "cpu"  # no GPU retry on later takes


@pytest.mark.parametrize("name", ["generator_base.pth", "0f195d476dd87ca1bd7b09e6"])
def test_cached_checkpoint_found_under_either_audioseal_name(clean_state, monkeypatch, tmp_path, name):
    """AudioSeal 0.2's https fallback saves the generator as torch.hub's
    sha1-of-URL-path name; the startup prefetch must see that file too."""
    (tmp_path / "audioseal").mkdir()
    (tmp_path / "audioseal" / name).write_bytes(b"x")
    monkeypatch.setenv("AUDIOSEAL_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(watermark, "is_enabled", lambda: True)

    assert watermark._generator_checkpoint_cached()
    assert watermark.can_mark_offline()


def test_nothing_cached_means_no_offline_mark(clean_state, monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIOSEAL_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(watermark, "is_enabled", lambda: True)
    assert not watermark.can_mark_offline()


def test_marked_audio_returns_on_the_input_device_and_dtype(clean_state):
    wave = torch.randn(1, SR, dtype=torch.float32)
    out = watermark._embed_on(FakeGenerator(), "cpu", wave.unsqueeze(0), SR,
                              torch.tensor(watermark.OMNI_MESSAGE).unsqueeze(0))
    assert out.device == wave.device and out.dtype == wave.dtype
