"""Tests for the Navoiy-TTS engine — the Uzbek CosyVoice2 fine-tune.

The engine lives in its own subprocess venv (transformers==4.51.3), so these
tests never import cosyvoice/torch. They cover the parent-side wiring and the
sidecar's pure helpers: registry resolution, the Uzbek-only contract, the
reference-clip requirement, install probing, and the emotion mapping.
"""
from __future__ import annotations

import pytest


# ── registry wiring ────────────────────────────────────────────────────────


def test_registry_contains_navoiy():
    from services.tts_backend import _REGISTRY, get_backend_class

    assert "navoiy" in _REGISTRY, (
        "_REGISTRY is missing 'navoiy'; check _LAZY_REGISTRY in "
        "services/tts_backend.py"
    )
    cls = _REGISTRY["navoiy"]
    assert cls.__name__ == "NavoiyBackend"
    assert get_backend_class("navoiy") is cls
    assert cls.id == "navoiy"


def test_navoiy_is_explained_in_the_engine_metadata():
    from services.tts_backend import _ENGINE_DOCS, _INSTALL_HINTS, _SETUP_SNIPPETS

    assert _ENGINE_DOCS["navoiy"] == "docs/engines/navoiy.md"
    assert "OMNIVOICE_NAVOIY_DIR" in _INSTALL_HINTS["navoiy"]
    assert _SETUP_SNIPPETS["navoiy"].startswith("export OMNIVOICE_NAVOIY_DIR=")


def test_engine_doc_page_exists():
    from pathlib import Path

    from services.tts_backend import _ENGINE_DOCS

    root = Path(__file__).resolve().parents[1]
    page = root / _ENGINE_DOCS["navoiy"]
    assert page.is_file(), f"{page} is missing"
    text = page.read_text(encoding="utf-8")
    assert "OMNIVOICE_NAVOIY_DIR" in text
    assert "emotion_600h_joint.pt" in text


# ── the engine contract ────────────────────────────────────────────────────


def test_navoiy_declares_uzbek_only_and_emotion():
    from services.tts_backend import get_backend_class

    cls = get_backend_class("navoiy")
    backend = cls()
    assert backend.supported_languages == ["uz"]
    assert backend.supports_emotion is True
    assert backend.supports_cloning is True
    assert backend.supports_voice_design is False
    assert backend.sample_rate == 24000


def test_navoiy_rejects_a_language_it_cannot_speak():
    """#2104: a finite engine must refuse, not mispronounce.

    Before this contract existed the caller got Uzbek phonetics over English
    text and no error. The message has to name the engine and the supported
    set so the UI can turn it into "switch engine or pick another language".
    """
    from services.tts_backend import get_backend_class

    backend = get_backend_class("navoiy")()
    with pytest.raises(ValueError) as excinfo:
        backend._check_language("en")
    message = str(excinfo.value)
    assert "Navoiy" in message and "uz" in message


def test_navoiy_accepts_auto_and_uzbek():
    from services.tts_backend import get_backend_class

    backend = get_backend_class("navoiy")()
    assert backend._check_language(None) is None
    assert backend._check_language("uz") == "uz"
    assert backend._check_language("Uzbek") == "uz"


def test_generate_without_a_reference_names_the_fix():
    """The checkpoint has no built-in speakers, so a missing recording is a
    400 with a sentence the UI can show — not a sidecar spawn that fails."""
    from services.tts_backend import TTSInputError, get_backend_class

    backend = get_backend_class("navoiy")()
    with pytest.raises(TTSInputError) as excinfo:
        backend.generate("Salom.", language="uz")
    message = str(excinfo.value)
    assert "reference" in message.lower()
    assert "voice" in message.lower()


# ── install probe ──────────────────────────────────────────────────────────


def test_unconfigured_install_explains_the_env_var(monkeypatch):
    from engines.navoiy import bootstrap

    monkeypatch.delenv(bootstrap.NAVOIY_DIR_ENV, raising=False)
    bootstrap.invalidate()
    try:
        assert bootstrap.root_dir() is None
        assert bootstrap.is_installed() is False
        assert "OMNIVOICE_NAVOIY_DIR" in bootstrap.missing_message()
    finally:
        bootstrap.invalidate()


def test_a_configured_but_incomplete_root_names_what_is_missing(tmp_path, monkeypatch):
    from engines.navoiy import bootstrap

    monkeypatch.setenv(bootstrap.NAVOIY_DIR_ENV, str(tmp_path))
    bootstrap.invalidate()
    try:
        assert bootstrap.is_installed() is False
        message = bootstrap.missing_message()
        assert "venv" in message.lower()
    finally:
        bootstrap.invalidate()


def test_a_complete_layout_is_installed(tmp_path, monkeypatch):
    from engines.navoiy import bootstrap

    root = tmp_path
    (root / "CosyVoice" / "cosyvoice" / "cli").mkdir(parents=True)
    (root / "CosyVoice" / "cosyvoice" / "cli" / "cosyvoice.py").write_text("", encoding="utf-8")
    (root / "base").mkdir()
    (root / "base" / "cosyvoice2.yaml").write_text("", encoding="utf-8")
    (root / "navoiy").mkdir()
    (root / "navoiy" / "emotion_600h_joint.pt").write_bytes(b"x")
    venv = root / "venv" / ("Scripts" if __import__("sys").platform == "win32" else "bin")
    venv.mkdir(parents=True)
    (venv / ("python.exe" if __import__("sys").platform == "win32" else "python")).write_bytes(b"")

    monkeypatch.setenv(bootstrap.NAVOIY_DIR_ENV, str(root))
    bootstrap.invalidate()
    try:
        assert bootstrap.venv_python() is not None
        assert bootstrap.checkout_dir() == root / "CosyVoice"
        assert bootstrap.base_dir() == root / "base"
        assert bootstrap.checkpoint() == root / "navoiy" / "emotion_600h_joint.pt"
        assert bootstrap.is_installed() is True
    finally:
        bootstrap.invalidate()


def test_available_engine_reports_the_uzbek_contract(monkeypatch):
    from engines.navoiy import bootstrap
    from services.tts_backend import get_backend_class

    # Pretend the install exists without touching the filesystem: the probe is
    # the only thing that decides availability.
    monkeypatch.setattr(bootstrap, "is_installed", lambda: True)
    ok, message = get_backend_class("navoiy").is_available()
    assert ok is True
    assert "Uzbek" in message


# ── language routing (dub) ────────────────────────────────────────────────


class _FakeNavoiy:
    """Stands in for the engine class: availability is the only thing routing
    asks of it."""

    @classmethod
    def is_available(cls):
        return True, "ready"


def _route_with_navoiy(monkeypatch):
    from services import tts_backend

    real = tts_backend.get_backend_class

    def fake(engine_id):
        if engine_id == "navoiy":
            return _FakeNavoiy
        return real(engine_id)

    monkeypatch.setattr(tts_backend, "get_backend_class", fake)


def test_is_uzbek_names_every_spelling(monkeypatch):
    from services.tts_backend import is_uzbek

    for value in ("uz", "uz-UZ", "uz_UZ", "Uzbek", "uzb", "uzn"):
        assert is_uzbek(value), value
    for value in ("en", "ru", "auto", "", None, "uzbekistanian-ish"):
        assert not is_uzbek(value), value


def test_an_uzbek_dub_goes_to_navoiy(monkeypatch):
    from services.tts_backend import uzbek_engine_id

    _route_with_navoiy(monkeypatch)
    assert uzbek_engine_id("uz", configured="omnivoice") == "navoiy"
    # Any other language keeps the configured engine.
    assert uzbek_engine_id("ru", configured="omnivoice") == "omnivoice"
    # An explicit pick is the user talking; never override it.
    assert uzbek_engine_id("uz", configured="cosyvoice") == "cosyvoice"


def test_uzbek_dub_routing_skips_a_mixed_language_job(monkeypatch):
    from api.routers import dub_generate
    from types import SimpleNamespace

    _route_with_navoiy(monkeypatch)
    monkeypatch.setattr(dub_generate, "active_backend_id", lambda: "omnivoice")

    def req(language, targets):
        return SimpleNamespace(
            language=language,
            segments=[SimpleNamespace(target_lang=t) for t in targets],
        )

    assert dub_generate._dub_engine_id(req("uz", ["uz", None, "uz"])) == "navoiy"
    # One non-Uzbek segment keeps the whole job on the configured engine:
    # Navoiy would refuse that segment mid-render.
    assert dub_generate._dub_engine_id(req("uz", ["uz", "en"])) == "omnivoice"
    assert dub_generate._dub_engine_id(req("en", ["en"])) == "omnivoice"


def test_uzbek_routing_leaves_an_uninstalled_engine_alone(monkeypatch):
    from services import tts_backend

    monkeypatch.setenv("OMNIVOICE_NAVOIY_DIR", "")
    from engines.navoiy import bootstrap

    bootstrap.invalidate()
    try:
        assert tts_backend.uzbek_engine_id("uz", configured="omnivoice") == "omnivoice"
    finally:
        bootstrap.invalidate()


# ── sidecar helpers (import-safe: no torch/cosyvoice at module level) ──────


def test_sidecar_emotion_mapping():
    from engines.navoiy.main import DEFAULT_EMOTION, EMOTIONS, _instruct

    assert len(EMOTIONS) == 10
    assert _instruct("xursand") == EMOTIONS["xursand"]
    assert _instruct("[jahldor]") == EMOTIONS["jahldor"]
    assert _instruct(None) == EMOTIONS[DEFAULT_EMOTION]
    # A written description is passed through: the dub director's tone and a
    # user's own words both reach the model.
    assert _instruct("Speak very slowly.") == "Speak very slowly."


def test_sidecar_babbling_guard_keeps_real_takes():
    from engines.navoiy.main import _babbled

    text = "Assalomu alaykum! Bugun sizga juda muhim bir xabarim bor."
    # Measured on the checkpoint: 3.6–4.8 s for this sentence.
    assert not _babbled(text, 4.8)
    # A missed end-of-speech ran to 17.6 s on transformers 5.
    assert _babbled(text, 17.6)
