"""The release helper bumps every version mirror together.

A drift here ships an installer whose updater compares the wrong version: the
app would keep offering the same release forever. The three files must move in
lockstep, so the helper is tested against copies instead of the real tree.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    path = ROOT / "scripts" / "release_sado.py"
    spec = importlib.util.spec_from_file_location("release_sado", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_version_files_move_together(tmp_path, monkeypatch):
    module = _load_script()
    for name in module.VERSION_FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)

    monkeypatch.setattr(module, "ROOT", tmp_path)
    changed = module.bump_version_files("9.9.9")

    assert set(changed) == set(module.VERSION_FILES)
    package = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert package["version"] == "9.9.9"
    assert 'version = "9.9.9"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    fallback = (tmp_path / "backend/core/version.py").read_text(encoding="utf-8")
    assert '_FALLBACK_VERSION = "9.9.9"' in fallback


def test_current_version_is_read_from_package_json():
    module = _load_script()
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert module.current_version() == package["version"]
