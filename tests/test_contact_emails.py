"""Sado publishes exactly three contact addresses (owner-set 2026-10-02).

    hi@sado.sh        general, business, licensing, collaboration
    partner@sado.sh   brand and company partnerships
    security@sado.sh  vulnerability reports

Any other real address in a shipped file (docs, UI, locales, package metadata,
legal text) is a stale or personal contact. Tests and fixtures may use
reserved example domains (RFC 2606 / RFC 6761) or fake addresses, and docs may
show GitHub no-reply commit addresses.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_CONTACTS = {"hi@sado.sh", "partner@sado.sh", "security@sado.sh"}
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_RESERVED_DOMAIN = re.compile(r"(^|\.)(example\.(com|net|org)|example|test|invalid|localhost|local)$", re.I)
# GitHub no-reply commit addresses are identities, not contact addresses.
_NOREPLY_DOMAIN = "users.noreply.github.com"
_TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|fixtures)/|\.test\.[a-z]+$|_test\.py$")
# Licence notices quote the licensor's own contact (the upstream company), not ours.
_LICENSE_PATH = re.compile(r"(^|/)LICENSE[^/]*$")
# Retina asset names (trayTemplate@2x.png) look like addresses to the regex.
_RETINA_ASSET = re.compile(r"@[1-4]x\.(?:png|jpe?g|webp|gif|svg)$", re.I)


def _tracked_text_files():
    names = subprocess.run(
        ["git", "-C", str(_REPO), "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout.split("\0")
    for name in filter(None, names):
        try:
            yield name, (_REPO / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError, PermissionError):
            # A submodule gitlink is listed but is a directory: IsADirectoryError
            # on POSIX, PermissionError on Windows.
            continue


def test_only_project_contact_addresses_are_published():
    stray = []
    for name, text in _tracked_text_files():
        if _LICENSE_PATH.search(name):
            continue
        for address in _EMAIL.findall(text):
            if _RETINA_ASSET.search(address):
                continue
            domain = address.rsplit("@", 1)[1]
            if (address.lower() in _CONTACTS or _RESERVED_DOMAIN.search(domain) or domain.lower() == _NOREPLY_DOMAIN
                    or _TEST_PATH.search(name)):
                continue
            stray.append(f"{name}: {address}")
    assert not stray, "Use hi@, partner@ or security@sado.sh:\n" + "\n".join(stray)
