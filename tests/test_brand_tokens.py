"""The Sado brand accent stays on the default palette.

The app's default palette ("default" = no `data-theme-id`) reads its colours
from `styles/t3-theme.css`. The Sado build recolours only `--primary` — the
brand indigo, deep on light surfaces (#5856D6) and bright on dark (#5E5CE6) —
and keeps white ink on filled controls, which clears 4.5:1 on both. This pins
the values so a palette edit cannot quietly drop the brand or the contrast.
"""
from __future__ import annotations

import re
from pathlib import Path

THEME = (
    Path(__file__).resolve().parents[1]
    / "electron/src/renderer/src/styles/t3-theme.css"
)

#: The brand indigo of the brand book (`sado logo/brand/tokens.css`).
_INDIGO = {"light": "#5856d6", "dark": "#5e5ce6"}
_PRIMARY = re.compile(r"--primary:\s*(#[0-9a-fA-F]{6})\s*;")
_PRIMARY_INK = re.compile(r"--primary-foreground:\s*var\(--color-white\)\s*;")


def _blocks() -> tuple[str, str]:
    """(light, dark) halves of the default palette, split at the dark variant."""
    source = THEME.read_text(encoding="utf-8")
    dark_at = source.index("@variant dark")
    return source[:dark_at], source[dark_at:]


def test_primary_is_the_brand_indigo_in_both_appearances():
    light, dark = _blocks()
    assert [v.lower() for v in _PRIMARY.findall(light)][:1] == [_INDIGO["light"]], (
        "light --primary is the deep brand indigo"
    )
    assert [v.lower() for v in _PRIMARY.findall(dark)][:1] == [_INDIGO["dark"]], (
        "dark --primary is the bright brand indigo"
    )


def test_filled_controls_use_white_ink_in_both_appearances():
    light, dark = _blocks()
    assert _PRIMARY_INK.search(light), "light --primary-foreground must be white ink on indigo"
    assert _PRIMARY_INK.search(dark), "dark --primary-foreground must be white ink on indigo"
