---
version: 1
slug: "src-renderer-src-features-home-home-page-tsx"
primary_target: "src/renderer/src/features/home/home-page.tsx"
related_targets: ["src/renderer/src/components/app-shell/workspace-sidebar.tsx"]
---

Scope: Sado desktop app shell (sidebar navigation, theme tokens, type) and Home route. Mode: Operate.
Audience/job: Uzbek bloggers, dubbing studios and the owner; write Uzbek text, pick a voice, generate; dub videos.
Constraints: all existing routes and functions kept; i18n for every string; light and dark equal; owner pinned the "Neon studiya" concept (docs/design) as the base world.

## Direction contract
THESIS: Sado is a working voice studio, not a feature catalogue. The text people voice and their own voices lead; chrome recedes. Refuses the category default of a hero plus nine identical icon cards, per-item rainbow icons, gradients and glow.
OWN-WORLD: Graphite studio (#07090c canvas, #0d1117 panels, #111721 overlays, hairlines rgb(233 240 249/8%)) with one neon turquoise #35f0c6 that only marks action and the current place; light twin is cool studio paper oklch(0.982 0.004 215) with deep turquoise oklch(0.55 0.11 175). Onest for interface, Unbounded only for the SADO wordmark. Monochrome line icons. Radii 12-16px, flat surfaces, no glass.
STORY: User lands, sees one question and a script box (same text the studio edits), picks or confirms a voice, opens the studio; their recent projects (or a way in when there are none) close the page; destinations and voices live only in the sidebar.
FIRST VIEWPORT: Left sidebar: SADO wordmark, "Yaratish" group (6 links), "Kutubxona" group (3), "Ko'proq" fold, then saved-voice library and engine status. Main column max 60rem: H2 question ~38px, lede, script composer full width with voice chip, language and engine meta, character count and turquoise "Studiyada ochish" button bottom-right; below, list rows of recent projects or an empty-state line linking Dubbing and Audiobook. A "Bosh sahifa" row tops the sidebar.
FORM: Pinned by owner (Neon studiya base, docs/design/sado-ui.html); no concept roll; seed key: none (owner-pinned).
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
