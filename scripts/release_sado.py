"""Cut a Sado desktop release from this checkout.

One command does the whole release: bump the three version files in lockstep,
refresh the JS lockfile, run the version gate, commit, tag, push, build the
Windows installer locally (electron-builder + the Rust native helper) and upload
the installer, its blockmap and the update-feed manifest to a GitHub Release.

    python scripts/release_sado.py 0.5.8

The update feed is what installed copies poll
(``releases/latest/download/electron-stable-win32-x64.yml``), so a published
release is immediately live for everyone who already installed Sado.

Flags:
    --skip-build   bump/commit/tag/push only (build and upload are separate)
    --dry-run      print every step without touching anything
    --notes FILE   release body (default: the CHANGELOG section for this version)

The GitHub token comes from the credential helper git already uses for
github.com, so no token is stored in the repo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OWNER = "Anvarjon090"
REPO = "sado"
CHANNEL = "electron-stable-win32-x64"
VERSION_FILES = {
    "package.json": r'("version":\s*")([^"]+)(")',
    "pyproject.toml": r'(?m)^(version = ")([^"]+)(")',
    "backend/core/version.py": r'(_FALLBACK_VERSION = ")([^"]+)(")',
}


def run(cmd: list[str], *, env: dict[str, str] | None = None, check: bool = True):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, env=env, check=check, text=True)


def current_version() -> str:
    return json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]


def bump_version_files(version: str) -> list[str]:
    """Write ``version`` into every mirror; return the files that changed."""
    changed = []
    for name, pattern in VERSION_FILES.items():
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        new, count = re.subn(pattern, rf"\g<1>{version}\g<3>", text, count=1)
        if not count:
            raise SystemExit(f"{name}: version mirror not found")
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed.append(name)
    return changed


def git(*args: str) -> None:
    run(["git", *args])


def github_token() -> str:
    proc = subprocess.run(
        ["git", "credential", "fill"],
        cwd=ROOT,
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        check=True,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("no github.com credential found")


def api(url: str, token: str, *, method: str = "GET", data: bytes | None = None):
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "sado-release",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def release_notes(version: str, path: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"(?ms)^## \[{re.escape(version)}\].*?(?=^## \[|\Z)", changelog)
    return match.group(0).strip() if match else f"Sado {version}"


def upload_asset(token: str, release_id: int, asset: Path) -> None:
    url = (
        f"https://uploads.github.com/repos/{OWNER}/{REPO}/releases/"
        f"{release_id}/assets?name={urllib.parse.quote(asset.name)}"
    )
    print("uploading", asset.name)
    request = urllib.request.Request(
        url,
        data=asset.read_bytes(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/octet-stream",
            "User-Agent": "sado-release",
        },
    )
    with urllib.request.urlopen(request, timeout=1800) as response:
        payload = json.load(response)
    print("  ->", payload.get("state"), payload.get("size"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="new version, e.g. 0.5.8")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--notes", default=None)
    args = parser.parse_args()

    version = args.version.strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit(f"not a version: {version!r}")
    old = current_version()
    if version == old:
        raise SystemExit(f"version is already {version}")

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    if status:
        raise SystemExit("working tree is dirty; commit or stash first:\n" + status)

    print(f"Sado {old} -> {version}")
    if args.dry_run:
        print("dry run: bump", ", ".join(VERSION_FILES), "then commit/tag/build/upload")
        return 0

    changed = bump_version_files(version)
    print("bumped:", ", ".join(changed))
    run(["bun", "install"], check=False)

    tag = f"v{version}"
    git("add", *changed, "bun.lock")
    git("commit", "-m", f"chore(release): {tag}")
    git("tag", "-a", tag, "-m", f"Sado {tag}")
    git("push", "origin", "HEAD:main")
    git("push", "origin", tag)

    if args.skip_build:
        print(f"tagged {tag}; build/upload skipped")
        return 0

    env = dict(os.environ)
    cargo = Path.home() / ".cargo" / "bin"
    if cargo.is_dir():
        env["PATH"] = f"{cargo}{os.pathsep}{env.get('PATH', '')}"
    run(["bun", "run", "dist"], env=env)

    release_dir = ROOT / "electron" / "release"
    assets = [
        release_dir / f"Sado-Electron-{version}-win-x64.exe",
        release_dir / f"Sado-Electron-{version}-win-x64.exe.blockmap",
        release_dir / f"{CHANNEL}.yml",
    ]
    missing = [str(a) for a in assets if not a.is_file()]
    if missing:
        raise SystemExit("build produced no " + ", ".join(missing))

    token = github_token()
    release = api(
        f"https://api.github.com/repos/{OWNER}/{REPO}/releases",
        token,
        method="POST",
        data=json.dumps(
            {
                "tag_name": tag,
                "name": f"Sado {tag}",
                "body": release_notes(version, args.notes),
                "draft": False,
                "prerelease": False,
            }
        ).encode(),
    )
    print("release:", release["html_url"])
    for asset in assets:
        upload_asset(token, release["id"], asset)
    print("done:", release["html_url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
