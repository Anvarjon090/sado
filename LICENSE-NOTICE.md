# Sado — License Notice

## Abbreviation

AGPL-3.0-only

## Notice

Sado is a modified version of VoiceStudio.

Copyright 2024-present Palash Debnath and VoiceStudio contributors.
Modifications copyright 2026-present Anvarjon090 and Sado contributors.

Sado is **free and open-source software, licensed under the GNU Affero General
Public License, Version 3 (AGPL-3.0)**. You are free to use, copy, modify, and
redistribute it. That **includes commercial and internal business use** of the
application itself. Model weights, tokenizers, and other third-party assets
retain their own terms; this application license does not grant or summarize
rights under those separate terms.

Because this is the **Affero** GPL, one additional obligation applies: if you
modify Sado and make that modified version available to others over a network,
you must also offer those users the complete corresponding source code of your
modified version under these same AGPL-3.0 terms. See the full text in
[`LICENSE`](LICENSE). Sado itself meets this by publishing its complete source
at <https://github.com/Anvarjon090/sado>.

The upstream VoiceStudio code is licensed to Sado under the AGPL-3.0 only. A
license to use that code outside the AGPL-3.0 can come only from its copyright
holders; the Sado maintainer cannot grant one. For questions about Sado, open
an issue at <https://github.com/Anvarjon090/sado/issues>.

Contributors license their contributions to the Sado maintainer under the
[Contributor License Agreement 2.0](.github/CLA-2.0.md). While a contribution
is in the public repository, it stays available there under the AGPL-3.0 or
another OSI-approved licence (CLA section 4).

(This Notice is a plain-language summary; the binding terms are the full GNU
AGPL-3.0 text in [`LICENSE`](LICENSE).)

### Scope

These terms cover the Sado application — the Electron desktop and web
app (`electron/`), its native desktop helper (`native/`), the FastAPI backend
(`backend/`), and supporting build / packaging files (`scripts/`, `deploy/`,
`.github/`). Electron components adapted from T3 Code keep their MIT notice in
`electron/T3CODE-LICENSE.txt`.

The bundled `omnivoice/` Python package — the underlying TTS model by Han Zhu —
is **separately licensed under Apache License 2.0** by its upstream authors and
is not relicensed here. Apache License 2.0 is compatible with, and may be
combined under, the GNU AGPL-3.0. See `pyproject.toml`.

Downloaded model weights are not relicensed by Sado. The default
`k2-fsa/OmniVoice` model card identifies its code as Apache-2.0 and pretrained
weights as CC-BY-NC (non-commercial). Its `audio_tokenizer/LICENSE` contains
separate Boson Higgs Audio 2 and Meta Llama community terms. No license for the
application code replaces any of those terms.

Third-party dependencies retain their own licenses. See `bun.lock`, `uv.lock`,
and `native/desktop-bridge/Cargo.lock` for the resolved set.

### Reference

The full canonical text of the GNU Affero General Public License, Version 3 is
reproduced verbatim in [`LICENSE`](LICENSE). The authoritative copy lives at
<https://www.gnu.org/licenses/agpl-3.0.txt>.

> **Why this notice is a separate file:** `LICENSE` must contain the verbatim
> AGPL-3.0 text and nothing else, so GitHub's license detection (and the
> corporate license scanners that gate adoption) can identify it as
> `AGPL-3.0-only` rather than falling back to "Other" / `NOASSERTION`.
