"""Sado release-brand and source-launch contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = json.loads((ROOT / "package.json").read_text())["version"]


def test_current_version_is_in_lockstep_everywhere() -> None:
    package = json.loads((ROOT / "package.json").read_text())
    assert package["version"] == CURRENT_VERSION

    mirrors = {
        "pyproject.toml": r'(?m)^version = "([^"]+)"',
        "backend/core/version.py": r'(?m)^_FALLBACK_VERSION = "([^"]+)"',
    }
    for path, pattern in mirrors.items():
        match = re.search(pattern, (ROOT / path).read_text())
        assert match and match.group(1) == CURRENT_VERSION, path

    lock_contracts = {"uv.lock": r'name = "omnivoice"\s+version = "([^"]+)"'}
    for path, pattern in lock_contracts.items():
        match = re.search(pattern, (ROOT / path).read_text())
        assert match and match.group(1) == CURRENT_VERSION, path


def test_visible_brand_surfaces_say_sado() -> None:
    visible_files = ("electron/build/Info.plist", "electron/src/renderer/index.html")
    for path in visible_files:
        text = (ROOT / path).read_text()
        assert "Sado" in text, path
        assert "OmniVoice needs" not in text, path
        assert "OmniVoice may" not in text, path
        assert "OmniVoice Gallery" not in text, path

    readme = (ROOT / "README.md").read_text()
    assert "**Sado** (default, powered by k2-fsa/OmniVoice)" in readme
    assert "**OmniVoice** (default)" not in readme


def test_brand_mark_is_shared_and_fills_the_icon() -> None:
    mark = (ROOT / "electron/src/shared/components/brand/SadoMark.jsx").read_text()
    header = (ROOT / "electron/src/shared/components/Header.jsx").read_text()
    about = (ROOT / "electron/src/shared/components/settings/AboutTab.jsx").read_text()
    logo = (ROOT / "docs/logo.svg").read_text()
    favicon = (ROOT / "electron/public/favicon.svg").read_text()

    signature = 'x="24.94"'
    assert signature in mark
    assert signature in logo
    assert signature in favicon
    assert "<SadoMark" in header
    assert "<SadoMark" in about
    assert 'data-testid="voice-studio-logo"' in header

    # The Sado tile fills the 64-unit canvas with a 14-unit corner radius and
    # four waveform bars; the desktop icon renders the same geometry.
    assert 'width="64" height="64" rx="14"' in logo
    assert "<circle" not in logo
    assert 'src="docs/logo.png"' in (ROOT / "README.md").read_text()


def test_python_package_metadata_points_to_sado() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert 'Homepage = "https://github.com/Anvarjon090/sado"' in pyproject
    assert 'Repository = "https://github.com/Anvarjon090/sado"' in pyproject
    assert '"Upstream TTS Model" = "https://github.com/k2-fsa/OmniVoice"' in pyproject


def test_engine_help_names_the_app_not_the_upstream_model() -> None:
    paths = (
        "backend/engines/confucius4/__init__.py",
        "backend/engines/confucius4/bootstrap.py",
        "backend/engines/dots_tts/__init__.py",
        "backend/engines/dots_tts/bootstrap.py",
        "backend/engines/indextts/__init__.py",
        "backend/engines/indextts/bootstrap.py",
        "backend/engines/moss_tts_v15/__init__.py",
        "backend/engines/moss_tts_v15/bootstrap.py",
    )
    stale_help = re.compile(r"(?:restart|reinstall|re-launch|Run) OmniVoice")
    for path in paths:
        text = (ROOT / path).read_text()
        assert not stale_help.search(text), path


def test_compatibility_identifiers_stay_stable() -> None:
    package = json.loads((ROOT / "package.json").read_text())
    assert package["name"] == "omnivoice-studio-monorepo"
    assert 'name = "omnivoice"' in (ROOT / "pyproject.toml").read_text()
    assert "com.sado.desktop" in (ROOT / "electron/electron-builder.config.mjs").read_text()


def test_active_source_launch_is_electron_and_web_ports_clean_quietly() -> None:
    scripts = json.loads((ROOT / "package.json").read_text())["scripts"]
    assert scripts["dev"] == "bun run --cwd electron dev"
    assert not any("tauri" in name for name in scripts)
    command = scripts["predev:web"]
    assert "bun scripts/clear-dev-ports.mjs 3900 3901" in command
    assert "|| true" not in command


def test_icon_rail_has_no_static_section_captions_and_keeps_air_between_items() -> None:
    rail = (ROOT / "electron/src/shared/components/NavRail.jsx").read_text()
    for stale_caption in ("Start", "Create", "Workflows", "Reference"):
        assert stale_caption not in rail
    assert "pt-[18px]" in rail
    assert "gap-[9px]" in rail


def test_electron_launch_preserves_an_existing_backend():
    scripts = json.loads((ROOT / "package.json").read_text())["scripts"]
    for name in ("predev", "predesktop"):
        assert "clear-dev-ports" not in scripts[name]
        assert "desktop-runtime-preflight" not in scripts[name]
    assert scripts["dev"] == "bun run --cwd electron dev"
    assert scripts["desktop-prod:run"] == "bun run start"
    assert scripts["start"] == "bun run --cwd electron start"
