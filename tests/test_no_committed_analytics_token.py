"""No PostHog project token is committed to the tree.

History: upstream committed its publishable PostHog key as an in-repo default
(#1193), so every source build and installer sent consenting users' events to
the upstream project. Sado owner decision (2026-11-21): the in-repo default is
EMPTY in both files that implement analytics:

    backend/core/analytics.py        (_PUBLIC_PROJECT_TOKEN)
    electron/src/shared/utils/analytics.ts  (PUBLIC_PROJECT_TOKEN)

A destination comes only from the build/run-time override chain (repo secret ->
VITE_POSTHOG_KEY / POSTHOG_PROJECT_TOKEN), which stays pinned below. Without it
a build has no destination and never shows the consent ask. Same file-scanning
idiom as test_no_hardcoded_cjk / test_no_literal_borders.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

# A PostHog project key. Deliberately matched by SHAPE, not by the specific value.
_POSTHOG_KEY_RE = re.compile(r"phc_[A-Za-z0-9]{20,}")

# The two files that implement analytics; their in-repo defaults must be empty.
_ANALYTICS_FILES = {
    "backend/core/analytics.py": re.compile(r'^_PUBLIC_PROJECT_TOKEN = ""$', re.M),
    "electron/src/shared/utils/analytics.ts": re.compile(
        r"^const PUBLIC_PROJECT_TOKEN = '';$", re.M
    ),
}

# Files that must name a key literally: this guard, and the gitleaks allowlist
# test, which pins upstream's historical key (still in git history).
_EXEMPT = {
    "tests/test_no_committed_analytics_token.py",
    "tests/test_gitleaks_allowlist.py",
}

_SKIP_DIRS = {"node_modules", ".git", "target", "dist", "build", ".venv", "zig-out"}
_SCAN_EXT = {".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".json", ".yml", ".yaml", ".md", ".env"}


def _tracked_files():
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=_REPO, capture_output=True, text=True, check=True
    ).stdout
    for name in (n for n in out.split("\0") if n):
        p = Path(name)
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in _SCAN_EXT:
            yield name, _REPO / p


def test_no_posthog_token_literal_is_committed():
    offenders = []
    for name, path in _tracked_files():
        if name in _EXEMPT:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if _POSTHOG_KEY_RE.search(text):
            offenders.append(name)

    assert not offenders, (
        "A PostHog token literal is committed: " + ", ".join(offenders) + ". "
        "Sado ships no in-repo destination; builds take the token via "
        "VITE_POSTHOG_KEY / POSTHOG_PROJECT_TOKEN at build/run time."
    )


def test_both_analytics_files_ship_an_empty_default_token():
    """A non-empty default would send consenting users' events to whoever owns
    that key, and would make every source build show the consent ask."""
    for name, pattern in _ANALYTICS_FILES.items():
        src = (_REPO / name).read_text(encoding="utf-8")
        assert pattern.search(src), f"{name} must keep its in-repo default token empty"


# ── the OVERRIDE chain must stay wired ───────────────────────────────────────
#
# There is no in-repo default; release builds get the token from the repo
# secret, and a developer's process env overrides everything:
#
#     repo secret -> release.yml -> tauri-action -> option_env! in backend.rs
#                 -> spawned backend process env -> analytics._resolved_token()
#
# Every link is invisible when it breaks (a release build silently ends up with
# no destination). These pin the links that live in files a
# future change could quietly drop.


def test_the_frontend_reads_its_token_override_from_the_build_env():
    """The build-time override mechanism must stay in place."""
    src = (_REPO / "electron/src/shared/utils/analytics.ts").read_text(encoding="utf-8")
    assert "VITE_POSTHOG_KEY" in src


def test_release_workflow_still_passes_the_secret_to_the_build():
    wf = (_REPO / ".github/workflows/electron-release.yml").read_text(encoding="utf-8")
    assert "VITE_POSTHOG_KEY" in wf, "the build no longer receives the analytics token override"
    assert "secrets.POSTHOG_PROJECT_TOKEN" in wf, "the override must come from the repo secret"


def test_the_shell_hands_the_token_to_the_backend_it_spawns():
    """Without this a baked release token could never reach the backend."""
    src = (_REPO / "electron/src/main/backend.ts").read_text(encoding="utf-8")
    assert "__POSTHOG_PROJECT_TOKEN__" in src, "the shell no longer bakes in the token"
    assert "POSTHOG_PROJECT_TOKEN" in src, "the backend process is no longer given the override"
    # #1193: the shell marks everything it spawns as the "installer" channel.

    # option_env! is resolved at COMPILE time, so cargo must rebuild when the
    # secret changes — otherwise a cached build keeps the token it first saw.
    config = (_REPO / "electron/electron.vite.config.ts").read_text(encoding="utf-8")
    assert "VITE_POSTHOG_KEY" in config
