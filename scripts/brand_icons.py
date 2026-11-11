#!/usr/bin/env python3
"""Build Sado's app icons from the brand geometry (electron/build/brand/README.md).

    uv run python scripts/brand_icons.py            # writes into electron/build/brand/icon/
    uv run python scripts/brand_icons.py --out DIR  # somewhere else, for a look first

The mark: three rings that meet at one point on the left — a voice and its
two echoes — on a 140×140 grid, stroke 11, opacities 1 / .65 / .35 from the
inside out. Under 32 px the two-ring small mark (stroke 18) is drawn instead,
so the rings stay apart and the meeting point reads.

The tile: a rounded square (radius 230 of 1024), indigo gradient #8482F5 →
#4442C4 top to bottom with a soft white highlight from the top-left; the mark
is 58 % of the tile's width, centred. ``dark`` and ``light`` keep the geometry
and change only the colours.

Outputs (the spec's file list):

* ``png/app-icon-{indigo,dark,light}-{16,24,32,48,64,128,256,512,1024}.png``
* ``app-icon.ico`` — 16, 20, 24, 32, 40, 48, 64, 256 (PNG-compressed entries)
* ``app-icon.icns`` — 16…1024 with the @2x entries, drawn on Apple's template
  (the tile 824 of 1024, centred, radius 185, a soft shadow underneath)
* ``app-icon-macos-1024.png`` — that template at full size

Everything is rendered with Pillow at 4–8× and downsampled, so edges are
anti-aliased and no size is a blurry resize of another. Nothing here is
stretched, rotated, recoloured per ring, glowed or outlined.
"""
from __future__ import annotations

import argparse
import io
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "electron" / "build" / "brand" / "icon"

GRID = 140.0
MARK_SCALE = 4.2667  # 140 grid units → ~597 px of a 1024 tile (58 %)
MARK_OFFSET = 213.33
RINGS = [(70.0, 70.0, 64.5, 0.35), (49.0, 70.0, 43.5, 0.65), (28.0, 70.0, 22.5, 1.0)]
RINGS_SMALL = [(70.0, 70.0, 61.0, 0.5), (35.0, 70.0, 26.0, 1.0)]
STROKE, STROKE_SMALL = 11.0, 18.0
TILE_RADIUS = 230 / 1024
MAC_TILE, MAC_RADIUS, MAC_SHADOW_Y, MAC_SHADOW_BLUR = 824 / 1024, 185 / 1024, 10 / 1024, 20 / 1024

VARIANTS = {
    "indigo": {"top": (0x84, 0x82, 0xF5), "bottom": (0x44, 0x42, 0xC4), "ring": (255, 255, 255), "highlight": 0.22},
    "dark": {"top": (0x0E, 0x10, 0x13), "bottom": (0x0E, 0x10, 0x13), "ring": (0xE9, 0xEC, 0xEF), "highlight": 0.0},
    "light": {"top": (0xEE, 0xF2, 0xF8), "bottom": (0xEE, 0xF2, 0xF8), "ring": (0x0A, 0x0C, 0x10), "highlight": 0.0},
}
PNG_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
#: icns type → pixel size (ic11–ic14 are the @2x members of 16/32/128/256).
ICNS_TYPES = (("icp4", 16), ("icp5", 32), ("icp6", 64), ("ic07", 128), ("ic08", 256), ("ic09", 512),
              ("ic10", 1024), ("ic11", 32), ("ic12", 64), ("ic13", 256), ("ic14", 512))


def _supersample(size: int) -> int:
    return 8 if size <= 64 else 4 if size <= 256 else 2


def tile_layer(canvas: int, tile: int, radius: int, variant: dict) -> Image.Image:
    """The rounded tile with its gradient and highlight, centred on ``canvas``."""
    top, bottom = np.array(variant["top"], float), np.array(variant["bottom"], float)
    y = np.linspace(0.0, 1.0, tile)[:, None, None]
    rgb = top * (1 - y) + bottom * y
    rgb = np.broadcast_to(rgb, (tile, tile, 3)).copy()
    if variant["highlight"]:
        xs = (np.arange(tile) + 0.5) / tile
        ys = (np.arange(tile) + 0.5) / tile
        d = np.sqrt((xs[None, :] - 0.30) ** 2 + (ys[:, None] - 0.0) ** 2) / 0.70
        glow = np.clip(1.0 - d, 0.0, 1.0) * variant["highlight"]
        rgb = rgb * (1 - glow[..., None]) + 255.0 * glow[..., None]
    mask = Image.new("L", (tile, tile), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, tile - 1, tile - 1), radius=radius, fill=255)
    layer = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    body = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    body.putalpha(mask)
    origin = (canvas - tile) // 2
    layer.alpha_composite(body, (origin, origin))
    return layer


def mark_layer(canvas: int, tile: int, variant: dict, small: bool) -> Image.Image:
    """The rings, each on its own layer at its opacity, centred on the tile."""
    rings, stroke = (RINGS_SMALL, STROKE_SMALL) if small else (RINGS, STROKE)
    k = tile / 1024.0 * MARK_SCALE
    origin = (canvas - tile) / 2.0 + MARK_OFFSET * tile / 1024.0
    layer = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    for cx, cy, r, opacity in rings:
        ring = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
        x, y, rad, w = origin + cx * k, origin + cy * k, r * k, stroke * k
        ImageDraw.Draw(ring).ellipse(
            (x - rad - w / 2, y - rad - w / 2, x + rad + w / 2, y + rad + w / 2),
            outline=(*variant["ring"], 255), width=max(1, round(w)),
        )
        if opacity < 1.0:
            alpha = ring.getchannel("A").point(lambda a, o=opacity: int(a * o))
            ring.putalpha(alpha)
        layer.alpha_composite(ring)
    return layer


def render(size: int, variant: str, *, macos: bool = False) -> Image.Image:
    """One icon at ``size`` px: full tile (Windows/Linux) or Apple's inset template."""
    v = VARIANTS[variant]
    ss = _supersample(size)
    canvas = size * ss
    tile = round(canvas * (MAC_TILE if macos else 1.0))
    radius = round(tile * ((MAC_RADIUS / MAC_TILE) if macos else TILE_RADIUS))
    out = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    if macos:
        shadow = Image.new("L", (canvas, canvas), 0)
        origin = (canvas - tile) // 2
        ImageDraw.Draw(shadow).rounded_rectangle(
            (origin, origin, origin + tile - 1, origin + tile - 1), radius=radius, fill=int(255 * 0.30),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(MAC_SHADOW_BLUR * canvas / 2))
        dy = round(MAC_SHADOW_Y * canvas)
        shifted = Image.new("L", (canvas, canvas), 0)
        shifted.paste(shadow, (0, dy))
        out.alpha_composite(Image.merge("RGBA", (*[Image.new("L", (canvas, canvas), 0)] * 3, shifted)))
    out.alpha_composite(tile_layer(canvas, tile, radius, v))
    out.alpha_composite(mark_layer(canvas, tile, v, small=size < 32))
    return out.resize((size, size), Image.LANCZOS) if ss > 1 else out


def png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def write_ico(path: Path, images: dict[int, Image.Image]) -> None:
    """A Windows icon with one PNG-compressed entry per size (Vista+)."""
    entries = sorted(images.items())
    header = struct.pack("<HHH", 0, 1, len(entries))
    directory, blobs, offset = b"", b"", 6 + 16 * len(entries)
    for size, image in entries:
        blob = png_bytes(image)
        directory += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    path.write_bytes(header + directory + blobs)


def write_icns(path: Path, images: dict[int, Image.Image]) -> None:
    chunks = b""
    for icns_type, size in ICNS_TYPES:
        blob = png_bytes(images[size])
        chunks += icns_type.encode("ascii") + struct.pack(">I", 8 + len(blob)) + blob
    path.write_bytes(b"icns" + struct.pack(">I", 8 + len(chunks)) + chunks)


def build(out: Path) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    (out / "png").mkdir(exist_ok=True)
    written = []
    for variant in VARIANTS:
        for size in PNG_SIZES:
            target = out / "png" / f"app-icon-{variant}-{size}.png"
            render(size, variant).save(target, optimize=True)
            written.append(target.name)
    write_ico(out / "app-icon.ico", {size: render(size, "indigo") for size in ICO_SIZES})
    written.append("app-icon.ico")
    mac = {size: render(size, "indigo", macos=True) for size in sorted({s for _, s in ICNS_TYPES})}
    write_icns(out / "app-icon.icns", mac)
    mac[1024].save(out / "app-icon-macos-1024.png", optimize=True)
    written += ["app-icon.icns", "app-icon-macos-1024.png"]
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    written = build(args.out)
    print(f"{len(written)} files → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
