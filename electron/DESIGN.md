---
name: Sado
description: Local-first Uzbek voice studio. Graphite studio with one indigo signal and frosted edges; light daylight-paper twin.
colors:
  indigo: "#5e5ce6"
  indigo-ink: "#ffffff"
  indigo-deep: "#5856d6"
  graphite-canvas: "#0e1013"
  graphite-sidebar: "#0e1013"
  graphite-panel: "#15181c"
  graphite-overlay: "#1b1e23"
  frost-ink: "#e9ecef"
  slate-mute: "#8b929a"
  hairline-dark: "rgb(255 255 255 / 8%)"
  hairline-strong-dark: "rgb(255 255 255 / 14%)"
  wash-dark: "rgb(255 255 255 / 8%)"
  studio-paper: "#eef2f8"
  paper-sidebar: "#eef2f8"
  paper-card: "#ffffff"
  graphite-ink: "#0a0c10"
  slate-mute-light: "#464c57"
  hairline-light: "rgb(14 17 22 / 10%)"
  hairline-strong-light: "rgb(14 17 22 / 16%)"
  wash-light: "rgb(14 17 22 / 6%)"
typography:
  display:
    fontFamily: "Unbounded, Onest, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    letterSpacing: "0.14em"
  headline:
    fontFamily: "Onest, Inter Variable, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "clamp(1.75rem, 1.3rem + 1.4vw, 2.375rem)"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Onest, Inter Variable, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: "1.25rem"
  body-editor:
    fontFamily: "Onest, Inter Variable, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: "1.75rem"
  body:
    fontFamily: "Onest, Inter Variable, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: "1.25rem"
  lede:
    fontFamily: "Onest, Inter Variable, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Onest, Inter Variable, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 500
    lineHeight: "1.25rem"
  caption:
    fontFamily: "Onest, Inter Variable, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: "1rem"
  nav-group:
    fontFamily: "Onest, Inter Variable, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 500
    letterSpacing: "0.02em"
rounded:
  sm: "8px"
  button: "10px"
  md: "12px"
  lg: "16px"
  pill: "999px"
spacing:
  row-x: "8px"
  gap: "16px"
  inset: "24px"
  section: "44px"
  content-max: "60rem"
components:
  button-primary:
    backgroundColor: "{colors.indigo}"
    textColor: "{colors.indigo-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.button}"
    padding: "0 16px"
    height: "36px"
  button-primary-light:
    backgroundColor: "{colors.indigo-deep}"
    textColor: "{colors.paper-card}"
    rounded: "{rounded.button}"
    padding: "0 16px"
    height: "36px"
  chip-voice:
    backgroundColor: "transparent"
    textColor: "{colors.frost-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "4px 12px 4px 5px"
  chip-voice-hover:
    backgroundColor: "{colors.wash-dark}"
  composer:
    backgroundColor: "{colors.graphite-panel}"
    textColor: "{colors.frost-ink}"
    typography: "{typography.body-editor}"
    rounded: "{rounded.lg}"
    padding: "18px 20px 8px"
  composer-light:
    backgroundColor: "{colors.paper-card}"
    textColor: "{colors.graphite-ink}"
    rounded: "{rounded.lg}"
  list-row:
    backgroundColor: "transparent"
    textColor: "{colors.frost-ink}"
    typography: "{typography.body}"
    padding: "6px 8px"
    height: "44px"
  list-row-hover:
    backgroundColor: "{colors.wash-dark}"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.frost-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 10px"
    height: "32px"
  nav-item-active:
    backgroundColor: "rgb(233 240 249 / 8%)"
    textColor: "{colors.frost-ink}"
  nav-item-active-light:
    backgroundColor: "{colors.paper-card}"
    textColor: "{colors.graphite-ink}"
---

# Design System: Sado

## Overview

**Creative North Star: "The Graphite Studio"**

Sado is a working voice studio, not a feature catalogue. The text a person is about to voice and their own voices and projects are the stage; chrome recedes into graphite (dark) or cool studio paper (light). One indigo signal marks exactly two things: the action you can take and the place you are. Everything else is ink, muted ink, and hairlines.

The world was redesigned with the owner in November 2026: graphite canvas, indigo accent, Onest interface type, Unbounded wordmark, a permanent icon rail with a library panel beside it, and frosted window edges. Light and dark are equal citizens; each token has a twin, and both indigo values carry white text above 4.5:1.

Density is calm working density: 14px interface text, 16px editor text on a 28px line, 44px list rows, a single content column capped at 60rem beside a persistent sidebar. The work area is an opaque card; separation inside it comes from hairlines and one-step tonal shifts, never glow or gradient. Only the window edges (rail, library panel, toolbars) are frosted: with Glass mode on (the default) they use the operating system's own material, macOS vibrancy or Windows 11 acrylic, so the user's real desktop shows through (dark 5px blur at 55% fill, light 15px at 79%). The app never paints a picture in place of the desktop; without the OS material (Windows 10, Linux, browser) the edges sit on the plain canvas. One window-wide title bar, frosted like the other edges, runs above everything: the library toggle on the left, the current page's title and actions in the middle (pages place them there through `WorkspaceHeader`), search on the right, and the native caption buttons (52px on macOS, 44px on Windows and Linux) at the window corner.

**Key Characteristics:**
- One accent, used only for action and current place.
- Graphite tonal stack in dark (canvas, sidebar, panel, overlay); paper stack in light.
- Hairline borders at 8% ink carry structure.
- Monochrome line icons; the active icon alone turns indigo.
- Onest everywhere; Unbounded only in the SADO wordmark.

## Colors

A near-black graphite stack with cool frost ink and one indigo; the light twin is cool daylight paper with crisp graphite ink and a deeper indigo.

### Primary
- **Indigo** (`indigo`): dark theme's only accent. Primary button fill, voice-chip dot, active nav icon, focus ring, caret, selection tint (26-35% mix), range inputs.
- **Indigo Ink** (`indigo-ink`): white text on both indigo values.
- **Deep Indigo** (`indigo-deep`): the light theme's accent in all the same roles, with white text.

### Neutral
- **Graphite Canvas** (`graphite-canvas`): dark app background.
- **Graphite Sidebar** (`graphite-sidebar`): sidebar surface, one step above canvas.
- **Graphite Panel** (`graphite-panel`): cards and the script composer.
- **Graphite Overlay** (`graphite-overlay`): popovers, menus, raised surfaces.
- **Frost Ink** (`frost-ink`): dark-theme primary text.
- **Slate Mute** (`slate-mute`): dark-theme secondary text, resting icons, placeholders, metadata.
- **Hairline** (`hairline-dark`): every dark border and divider. **Strong Hairline** (`hairline-strong-dark`): input strokes.
- **Wash** (`wash-dark`): hover fill for rows, chips, menu items.
- **Studio Paper** (`studio-paper`), **Paper Sidebar** (`paper-sidebar`), **Paper Card** (`paper-card`): light background, sidebar, and card/popover surfaces.
- **Graphite Ink** (`graphite-ink`), **Slate Mute Light** (`slate-mute-light`): light primary and secondary text.
- **Hairline Light** (`hairline-light`), **Strong Hairline Light** (`hairline-strong-light`), **Wash Light** (`wash-light`): light borders, input strokes, hover fill.

Status colours (error, warning, success, info) come from the Tailwind red/amber/emerald/blue scales and appear only for status, never as decoration.

### Reserved: Navoiy emotion tones
The concept defines ten tone colours for the emotion control: calm `#35f0c6`, happy `#ffd166`, sad `#6aa8ff`, angry `#ff5d6c`, fearful `#c084fc`, surprised `#f472b6`, whisper `#7dd3fc`, tender `#ff9f7a`, tired `#94a3b8`, ironic `#a3e635`. They are **reserved** for the Navoiy-TTS emotion control (tones work only on that engine) and are **not in use** on Home or the shell. Use them only to label a tone inside that control; never as general UI colour. The concept's violet secondary (`#8b5cf6`) and amber (`#f5b544`) are not shipped.

### Named Rules
**The One Signal Rule.** Indigo marks only an available action or the current place. If an element is neither, it is ink, muted ink, or hairline.

**The Twin Rule.** Every colour role ships a dark and a light value. Never add a role in one theme only.

## Typography

**Display Font:** Unbounded (with Onest, system-ui)
**Body Font:** Onest (with Inter Variable, -apple-system, Segoe UI, system-ui)
**Label/Mono Font:** ui-monospace stack for code only

**Character:** Onest is a warm, slightly geometric grotesque that renders Uzbek Latin (o', g', sh) cleanly; Unbounded's wide caps give the SADO wordmark its one moment of personality. Both are bundled locally (Latin and Latin Extended subsets, `font-display: swap`); there are no network font requests. A user appearance option swaps Onest for the system stack and scales the root (90/100/110/125%).

### Hierarchy
- **Display** (Unbounded 600, 15px, 0.14em tracking, uppercase): the SADO wordmark in the sidebar head, nothing else.
- **Headline** (600, clamp 28-38px, 1.1, -0.03em, balanced wrap): the single page question on Home.
- **Title** (600, 14px): list and section heads.
- **Body Editor** (400, 16px / 28px): the script textarea; text people voice gets the most generous size.
- **Lede** (400, 15px, 1.55, max 62ch, muted): one sentence under the headline.
- **Body** (400, 14px / 20px): interface default, nav items, list rows.
- **Label** (500, 13px): chips and compact controls.
- **Caption** (400, 12px, muted, tabular numerals for counts): metadata, character count, row meta.
- **Nav Group** (500, 11px, 0.02em, sentence case, muted): sidebar group names.

### Named Rules
**The One Wordmark Rule.** Unbounded appears only in the SADO wordmark. Headings, numerals and counts use Onest.

## Layout

A persistent left sidebar (resizable, collapsible to an icon rail with tooltips) holds all navigation: Home, a "Create" group of six, a "Library" group of three, a "More" fold, then the saved-voice library and engine status. The main area is one scrolling column below the window title bar, centred at max 60rem with 24px side inset (`spacing.inset`) and top padding `clamp(2rem, 6vh, 4.5rem)`.

Vertical rhythm on Home: headline, 10px to lede, 28px to composer, 44px (`spacing.section`) to the recent-work list. Lists are full-width rows separated by hairlines with 8px horizontal inset. The composer bar collapses under a 40rem container query: metadata and count hide, the primary button keeps the right edge.

### Named Rules
**The One Place Rule.** Each destination and each saved voice lives in exactly one place (the sidebar). Pages do not repeat navigation as card grids or shortcut strips.

## Elevation & Depth

Flat by default. Depth comes from the tonal stack (canvas, sidebar, panel, overlay) and 8% hairlines. Shadows are near-invisible structure: in light, the composer and the active nav item carry a 1-2px ambient shadow; in dark, the composer carries a 1px inner top highlight instead. Focus is the only "glow": a 4px 12% indigo halo around the focused composer. Glass mode in Appearance is on by default and frosts only the window edges over the OS material (see Overview); turning it off gives fully opaque edges.

### Shadow Vocabulary
- **Paper lift** (`box-shadow: 0 1px 2px rgb(8 12 18 / 5%)`): light composer at rest.
- **Graphite edge** (`box-shadow: inset 0 1px 0 rgb(233 240 249 / 4%)`): dark composer at rest.
- **Active paper tab** (`box-shadow: 0 1px 2px rgb(15 23 42 / 6%), inset 0 0 0 1px var(--border)`): current nav item, light theme.
- **Focus halo** (`box-shadow: 0 0 0 4px color-mix(in srgb, var(--primary) 12%, transparent)`): composer `:focus-within`.

### Named Rules
**The No-Glow Rule.** No coloured glows, gradients or glass at rest. The only coloured shadow is the focus halo.

## Shapes

Soft rectangles. Base radius 12px (`rounded.md`, the `--radius` root) for nav items and cards; 16px (`rounded.lg`) for the composer, the largest container; 10px (`rounded.button`) for the primary button; 8px (`rounded.sm`) for compact controls; full pills (`rounded.pill`) for the voice chip, status dots and avatars. Borders are 1px hairlines. Avatars are circles with a hairline ring and letter initials (two letters, letters only) when no image exists.

## Components

### Buttons
- **Shape:** gently rounded (10px), 36px tall, 16px horizontal padding, 600 weight, trailing arrow icon.
- **Primary:** indigo fill with white text (dark) / deep indigo with white (light).
- **Hover / Focus:** hover brightens 6% (`filter: brightness(1.06)`); press nudges down 1px; focus shows a 2px canvas gap then a 2px indigo ring. 150ms ease-out.
- **Text links:** foreground text, 30%-ink underline at 3px offset; underline turns indigo on hover/focus.

### Chips
- **Voice chip:** pill, hairline border, transparent fill, 13px label; leading avatar (20px) or a 8px indigo dot when no voice is chosen. Hover fills with wash; focus shows a 2px ring.

### Cards / Containers
- **Script composer:** the signature container. 16px radius, panel/card fill, hairline border, ambient shadow per theme. Borderless textarea (min 7.5rem, max 40vh, grows with content) above a bar with voice chip, language and engine meta, character count and primary button. Focus-within tints the border 55% toward indigo and adds the focus halo. Ctrl/Cmd+Enter submits.

### Inputs / Fields
- **Style:** borderless text on the container surface; indigo caret; muted placeholder. Standalone inputs use the strong hairline stroke and 8-12px radius.
- **Focus:** container-level border tint plus halo (composer) or 2px indigo ring.

### Navigation
- **Sidebar items:** 32px rows, 12px radius, 14px text at 75% ink, 16px monochrome line icon in muted ink. Hover: sidebar wash and full ink. Current page: raised fill (8% ink in dark, white tab with ambient shadow and hairline in light), 500 weight, icon turns indigo. Group names in Nav Group style. The icon rail is permanent and 64px wide: icon-only 40px targets with 20px icons and right-side tooltips, thin rules between Home, Create, Library and More, notifications and Settings at the foot; the current place gets full-ink icon, raised fill and a 3px indigo bar on the window edge. Beside it the library panel (wordmark, Saved/Recent takes segment, search, All/Clone/Design filter, the list, and an engine card with device, state and TTS/ASR/Translation rows whose chevron opens the device, speed and tool settings); the title bar's left button opens and closes the panel. A workspace's own side panels never sit inside the work card: its controls or section list (Settings, Dubbing, Voice design, Stories, Audiobook, Transcribe, Projects, Gallery, Tools, Batch) sit on the frosted left edge beside the card, and inspectors (voice sample, recent take, profile editor) on the right edge. The voice library is open only where voices are picked, Home and Voice cloning; everywhere else it folds into the rail, and the title-bar toggle brings it back on that page.

### Recent-work list
- Hairline-topped list of 44px rows: muted 16px kind icon, name (500, ellipsis), caption meta on the right. Row hover fills with wash and lifts meta to full ink; focus is an inset 2px ring. Empty state is one muted sentence with inline text links.

## Do's and Don'ts

### Do:
- **Do** keep indigo to actions and the current place (The One Signal Rule).
- **Do** ship every colour role as a dark/light pair; use indigo-ink, never white, on neon indigo.
- **Do** separate surfaces with 1px hairlines and one tonal step before reaching for shadow.
- **Do** use monochrome line icons in muted ink; only the active icon takes the accent.
- **Do** give the text being voiced the largest reading size (16px / 28px).
- **Do** route every string through i18n; Uzbek is the default copy.

### Don't:
- **Don't** use the ten emotion tone colours outside the Navoiy emotion control.
- **Don't** colour icons per item or per destination.
- **Don't** add gradients, glass or coloured glows to default surfaces.
- **Don't** repeat sidebar destinations or saved voices as card grids on a page.
- **Don't** use Unbounded for headings or numerals; it is the wordmark face only.
- **Don't** show decorative or placeholder statistics; numbers come from real measurements.
