"""The Sado brand accent stays on the default palette.

The app's default palette ("default" = no `data-theme-id`) reads its colours
from `styles/t3-theme.css`. The Sado build recolours only `--primary` — deep
teal on light surfaces, neon teal on dark — and the filled-control foreground
has to flip to dark ink there, or white-on-neon lands near 1.9:1. This pins
both values so a palette edit cannot quietly drop the brand or the contrast
fix.
"""
from __future__ import annotations

import re
from pathlib import Path

THEME = (
    Path(__file__).resolve().parents[1]
    / "electron/src/renderer/src/styles/t3-theme.css"
)

#: Hue of the brand teal in oklch.
_BRAND_HUE = re.compile(r"--primary:\s*oklch\(([\d.]+)%?\s+([\d.]+)\s+175\)")


def _source() -> str:
    return THEME.read_text(encoding="utf-8")


def _lightness(value: str) -> float:
    """oklch lightness as a 0-100 percentage (the CSS may write 0.84 or 84%)."""
    number = float(value.rstrip("%"))
    return number * 100 if number <= 1 else number


def test_primary_is_the_brand_teal_in_both_appearances():
    values = _BRAND_HUE.findall(_source())
    assert len(values) == 2, (
        "expected a light and a dark --primary in the brand hue; found "
        f"{values}"
    )
    light, dark = values
    # Light: a deep teal that keeps white button text readable.
    assert _lightness(light[0]) <= 60
    # Dark: a bright neon teal that reads as the accent on near-black.
    assert _lightness(dark[0]) >= 75


def test_dark_filled_controls_use_dark_ink():
    source = _source()
    dark_block = source[source.index("@variant dark"):]
    assert re.search(
        r"--primary-foreground:\s*var\(--color-neutral-950\)", dark_block
    ), "dark --primary-foreground must be dark ink, not white, on neon teal"
