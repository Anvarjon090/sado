# Sado brand

Sado's mark is three rings that meet at one point on the left edge: a voice
and its two echoes. It carries no letters, so it never depends on the product
name. The product voice is clear, calm, and direct.

## Assets

The brand pack lives in `electron/build/brand/`; its `README.md` is the
reference for geometry, files, and motion states.

| Surface | Source |
|---|---|
| In-app mark (Electron) | `<BrandMark />` in `electron/src/renderer/src/components/brand-mark.tsx` (inline SVG, `currentColor`, states from `build/brand/motion/mark-motion.css`) |
| Vector mark files | `electron/build/brand/logo/` (`mark.svg`; `mark-small.svg` is a two-ring glyph for monochrome spots under 16 px, not used by the app) |
| Browser icon | `electron/public/brand/favicon.svg` |
| App icons | `electron/build/brand/icon/` (`app-icon.ico`, `app-icon.icns`, `png/app-icon-indigo-*.png`), copied verbatim from the brand book, which builds them with `icon/make-icons.py`; every size keeps all three rings (64 px and below use thicker strokes and brighter outer rings) |
| Tray | `electron/build/brand/tray/` (`trayTemplate.png` on macOS; `tray-white-16.png` / `tray-dark-16.png` on Windows and Linux); the recording dot is still `electron/build/icons/tray-recording.png` |
| Legacy mark (README, shared modules) | `docs/logo.svg`, `electron/public/favicon.svg`, `electron/build/icons/` |

Use `<BrandMark />` in the app; never redraw the rings per screen. Do not
stretch or rotate the mark, add shadows or glows, recolour single rings, change
the ring opacities, or put letters inside it. Leave at least 20% of the mark's
width clear around it.

## Palette

| Role | Color |
|---|---|
| Voice rose | `#F47FA3` |
| Soft highlight | `#FFD0DB` |
| Creative amber | `#F7AE73` |
| Spark | `#FFE5B5` |
| Plum tile | `#211B2B` → `#120F18` |

The mark may render in one color inside app chrome. Keep the waveform and spark
together; do not put text inside the icon or add another enclosing ring.

## Name and copy

- Product name: **Sado**—one word, capital V and S.
- Voice: concise, professional, warm, and direct.
- Promise: local-first creation without a subscription or usage meter.
- Avoid absolute privacy claims: network-backed engines, downloads, analytics,
  and cloud integrations are explicit opt-ins, not nonexistent.
- Attribute the bundled default model as **k2-fsa/OmniVoice** where model lineage
  matters. OmniVoice is an upstream model/runtime name, not the product name.

## Compatibility names

The rebrand must not break existing installations. Keep these identifiers until
a separately tested migration exists:

- `omnivoice` Python imports and package name
- `omnivoice-studio` binary/package, Docker Hub path, and legacy GHCR alias
- `OMNIVOICE_*` environment variables and `X-OmniVoice-*` API headers
- existing OmniVoice data/cache directories and uninstall aliases
- upstream repositories, model IDs, classes, and engine IDs

Visible copy can explain those compatibility names, but must not silently rename
them on disk or over the wire.

Electron uses the shared multi-resolution ICO for Windows window/taskbar and tray
icons, the shared PNG for Linux and macOS runtime icons, and the ICNS for the macOS
bundle. The tray icon restores the window; closing the app retains its existing
quit behavior. Installed executable icons are applied when building the installer.
