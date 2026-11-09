"""Navoiy-TTS install probe: which interpreter, which weights.

Navoiy-TTS (`aisha-org/navoiy-tts`) is an Uzbek CosyVoice2-0.5B fine-tune. It
cannot live in Sado's interpreter: it needs ``transformers==4.51.3``
(the parent runs transformers 5, where the model's LLM loses its
end-of-speech and the audio degenerates into repeated syllables — measured
2026-11-06), and it is built for Python 3.10 with torch 2.7.

So it runs as a sidecar in its own venv, behind ``OMNIVOICE_NAVOIY_DIR``: the
user's install root, holding the CosyVoice checkout, the CosyVoice2 base
weights, the Navoiy checkpoint and a venv. Layout::

    <root>/.venv/                      (or <root>/venv/) — its interpreter
    <root>/CosyVoice/                  CosyVoice checkout @ 074ca6dc + Matcha-TTS
    <root>/base/                       FunAudioLLM/CosyVoice2-0.5B
    <root>/navoiy/emotion_600h_joint.pt

No auto-bootstrap: this engine is not a one-click install (the weights and the
CosyVoice checkout are GB-scale, and the venv pins conflict with the app's),
so the probe only reports what is missing and the doc page explains the setup.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("omnivoice.navoiy.bootstrap")

#: Env var pointing at the user's Navoiy-TTS install root.
NAVOIY_DIR_ENV = "OMNIVOICE_NAVOIY_DIR"

#: The sidecar entrypoint; SubprocessBackend spawns it with the venv python.
NAVOIY_SIDECAR_SCRIPT: Path = Path(__file__).parent / "main.py"

#: Directory names the install root may use for its venv.
_VENV_NAMES = (".venv", "venv")

#: CosyVoice checkout subdirectory (the upstream clone name by default).
_CHECKOUT_NAMES = ("CosyVoice", "cosyvoice")

#: Relative layout of the weights inside the install root.
BASE_SUBDIR = "base"
CHECKPOINT_SUBDIR = "navoiy"
CHECKPOINT_NAME = "emotion_600h_joint.pt"

_resolved: Optional[Path] = None
_resolved_key: Optional[str] = None


def invalidate() -> None:
    """Drop the memoised resolution (tests, and a .env edit inside one run)."""
    global _resolved, _resolved_key
    _resolved = None
    _resolved_key = None


def root_dir() -> Optional[Path]:
    """The configured install root, or None when the env var is unset."""
    raw = (os.environ.get(NAVOIY_DIR_ENV) or "").strip().strip('"')
    if not raw:
        return None
    return Path(raw).expanduser()


def _venv_python(venv: Path) -> Optional[Path]:
    if sys.platform == "win32":
        candidate = venv / "Scripts" / "python.exe"
    else:
        candidate = venv / "bin" / "python"
    return candidate if candidate.is_file() else None


def venv_python(root: Optional[Path] = None) -> Optional[Path]:
    """The engine venv's interpreter inside ``root``, if it exists."""
    root = root or root_dir()
    if root is None:
        return None
    key = str(root)
    global _resolved, _resolved_key
    if _resolved is not None and _resolved_key == key and _resolved.is_file():
        return _resolved
    for name in _VENV_NAMES:
        python = _venv_python(root / name)
        if python is not None:
            _resolved, _resolved_key = python, key
            return python
    return None


def checkout_dir(root: Optional[Path] = None) -> Optional[Path]:
    """The CosyVoice checkout the sidecar imports ``cosyvoice`` from."""
    root = root or root_dir()
    if root is None:
        return None
    for name in _CHECKOUT_NAMES:
        path = root / name
        if (path / "cosyvoice" / "cli" / "cosyvoice.py").is_file():
            return path
    return None


def base_dir(root: Optional[Path] = None) -> Optional[Path]:
    root = root or root_dir()
    if root is None:
        return None
    path = root / BASE_SUBDIR
    return path if (path / "cosyvoice2.yaml").is_file() else None


def checkpoint(root: Optional[Path] = None) -> Optional[Path]:
    root = root or root_dir()
    if root is None:
        return None
    path = root / CHECKPOINT_SUBDIR / CHECKPOINT_NAME
    return path if path.is_file() else None


def is_installed() -> bool:
    """Every piece the sidecar needs is on disk."""
    return bool(checkout_dir() and base_dir() and checkpoint() and venv_python())


def missing_message() -> str:
    """One user-facing sentence naming the first missing piece."""
    root = root_dir()
    if root is None:
        return (
            "Navoiy-TTS is not configured. Set OMNIVOICE_NAVOIY_DIR to your "
            "install root (the folder with CosyVoice/, base/ and navoiy/) and "
            "restart Sado — see docs/engines/navoiy.md."
        )
    if not root.is_dir():
        return f"{NAVOIY_DIR_ENV} points at {root}, which does not exist."
    if venv_python(root) is None:
        return (
            f"No engine venv under {root} (expected .venv/Scripts/python.exe). "
            "Create it with uv and install CosyVoice's runtime — see "
            "docs/engines/navoiy.md."
        )
    if checkout_dir(root) is None:
        return (
            f"CosyVoice checkout not found under {root} "
            "(expected CosyVoice/cosyvoice/cli/cosyvoice.py)."
        )
    if base_dir(root) is None:
        return (
            f"CosyVoice2-0.5B weights not found under {root}/base "
            "(expected cosyvoice2.yaml)."
        )
    if checkpoint(root) is None:
        return (
            f"Navoiy checkpoint not found at {root}/{CHECKPOINT_SUBDIR}/"
            f"{CHECKPOINT_NAME}."
        )
    return "Navoiy-TTS is ready."
