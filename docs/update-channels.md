# Desktop updates

Sado's desktop app offers **stable releases only**. It checks for an
update about 10 seconds after launch and every six hours while it stays open;
**Settings → Updates** also has a manual check. An available update is only
offered, never forced.

Updates are **manual installs**. Since 0.5.11 a release carries four
installers and their checksums, nothing else — macOS Apple Silicon and Intel
`.dmg`, Windows x64 `.exe`, Linux x64 `.AppImage`, and `SHA256SUMS.txt`. When a
newer version exists, **Download installer** opens this computer's installer in
your browser; run it over the current app. Windows on ARM opens the release
page and runs the x64 installer under emulation.

| Build | Where it comes from | Who it's for |
|-------|--------------------|--------------|
| **Stable** | The latest published `vX.Y.Z` GitHub Release. | Everyone. This is the only update channel. |

There is no Preview update channel and no preview desktop feed. To try changes
before they are released:

- **Run `main` from source** — see the platform install guides
  ([macOS](install/macos.md#building-from-source) ·
  [Windows](install/windows.md#building-from-source) ·
  [Linux](install/linux.md#building-from-source)), or build and install a
  package from `main` with the [install script's `--main` mode](install/script.md#building-main).
- **Docker** — `ghcr.io/anvarjon090/sado:latest` follows `main`; see
  [image tags](install/docker.md#image-tags).

There are **no accounts or updater telemetry**. A check is one request to the
GitHub Releases API (`api.github.com/repos/Anvarjon090/sado/releases/latest`)
for the newest version number, its notes and its installer links; nothing about
your machine or projects is sent. The installer opens only from
`github.com/Anvarjon090/sado/`. Compare a download with the release's
`SHA256SUMS.txt`, as the [install scripts](install/script.md) do. Installs from
releases before 0.5.11 still look for the retired update feed and will not see
newer versions; download 0.5.11 once by hand. Source checkouts do not
self-update.

The archived Tauri app keeps its frozen, signed `latest.json` feeds at
immutable URLs; they never offer Electron installers. Move to Electron with the
[migration guide](electron-migration.md).

## Your data during updates

Your voices, projects, history, and settings live in a SQLite database
(`omnivoice.db`) outside the app bundle, so replacing the app never touches
them. On the **first launch of an updated build**, if the new version needs a
database schema upgrade, Sado:

1. **Backs up the database first** — a consistent snapshot is written next to
   it as `omnivoice.db.backup-<version>-<n>` before any migration runs. The
   newest **3** backups are kept; older ones are pruned automatically.
   A snapshot interrupted mid-copy leaves a `.part-<pid>` file that is never
   treated as a backup and is removed on the next snapshot.
   (Databases over 500 MB skip the snapshot, with a log line saying so.)
2. **Stops instead of guessing** — if a migration fails midway, the app does
   *not* start on a half-migrated database and does *not* silently restore
   anything. It shows an error naming the backup path so you (or a support
   thread) decide: retry, report the issue, or roll back by replacing
   `omnivoice.db` with the backup.

**Settings → Updates** shows the timestamp of the latest backup, the release
notes of any available update, and a **What's new** reader for the shipped
changelog — all local, no extra network calls.

The Python environment (`.venv`) is also updated non-destructively: dependency
drift after an app update is reconciled **in place** with `uv sync`, and a
failed sync keeps the previous environment working. The venv is only ever
rebuilt when its interpreter is *confirmed* broken (structural check + a
direct probe) or when you explicitly use **Clean & Retry**.
