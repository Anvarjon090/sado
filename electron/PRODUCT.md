# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

(Electron desktop shell around a React renderer; Windows, macOS, Linux.)

## Users

- Uzbek bloggers and content makers producing voice-overs and dubs for YouTube/Reels.
- Studio and dubbing work: film, cartoon and ad dubbing, audiobooks.
- The owner's own daily use.
- Backend engine for the Sado Telegram bot (the desktop UI is secondary there).

## Product Purpose

Sado is the Uzbek-adapted fork of VoiceStudio (AGPL-3.0): a fully local voice studio for
Uzbek text-to-speech, voice cloning, video dubbing, emotion presets, audiobooks and
dictation/transcription. Success: an Uzbek user reaches a natural-sounding Uzbek result
without leaving the machine and without fighting the interface.

## Positioning

Local-first Uzbek voice studio: Uzbek text normalization, the Navoiy-TTS model and an
Uzbek LoRA for OmniVoice, 10 emotion tones, Uzbek interface by default. No cloud, account
or API key.

## Operating Context

Desktop app used for long working sessions: writing/pasting Uzbek text, choosing a voice,
generating, listening, exporting; dubbing videos; managing cloned voices. Local FastAPI
backend on 127.0.0.1:3900 also serves an OpenAI-compatible API used by the Telegram bot.

## Capabilities and Constraints

- All VoiceStudio functions remain: TTS, clone, design, dub, longform/audiobook,
  transcriptions, gallery, projects, batch, settings, integrations.
- UI strings go through i18n (`uz` default, 21 other locales keep parity).
- Upstream conventions in CLAUDE.md apply (local-first, cross-platform parity).

## Brand Commitments

- Name: **Sado** ("echo"). Uzbek-first copy.
- Existing concept "Neon studiya" (`docs/design/`) is the confirmed base: graphite canvas,
  turquoise accent, 10 tone colors, live monitor. Owner wants it cleaned of slop, not replaced.
- Light and dark themes are equally important.
- No leftover VoiceStudio sponsor/Pro/contributor marketing in the app.

## Evidence on Hand

- `docs/design/sado-ui.html`, `sado-desktop.png`, `sado-mobile.png`, local fonts Onest +
  Unbounded in `docs/design/fonts/`. Names in that mock (Dilnoza, project titles) are sample
  content, never real users.
- Brand pack (mark, app icons, tray marks, motion) in `electron/build/brand/` (see its README); favicon `electron/public/brand/favicon.svg`; in-app mark `<BrandMark />` (`electron/src/renderer/src/components/brand-mark.tsx`).

## Product Principles

1. Work tool first: the text and the result are the stage; chrome recedes.
2. One place per thing: no duplicated navigation or repeated entry points.
3. Uzbek by default, honest numbers only (real metrics, never decorative stats).
4. Local and private is shown through behaviour, not banners.
