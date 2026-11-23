"""No Python source in the repository starts with a UTF-8 byte-order mark.

Python itself tolerates one, but the repository's own AST guards read sources
with ``encoding="utf-8"`` and then fail on the stray U+FEFF — a BOM in one test
file (``tests/test_dub_complete_audio.py``, saved by a Windows editor) broke
``test_symlink_guards`` on every CI run. Catch the file, not the guard.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".venv", "node_modules", ".git", "_audit", "dist", "build"}


def test_python_sources_have_no_bom():
    offenders = [
        str(path.relative_to(ROOT))
        for top in ("backend", "tests", "scripts", "omnivoice")
        for path in (ROOT / top).rglob("*.py")
        if not SKIP.intersection(path.parts) and path.read_bytes()[:3] == b"\xef\xbb\xbf"
    ]
    assert not offenders, f"remove the UTF-8 BOM from: {offenders}"
