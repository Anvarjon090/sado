import { app, BrowserWindow, ipcMain, shell } from 'electron';
import { rmSync } from 'node:fs';
import { join } from 'node:path';
import { isTrustedRenderer } from './trusted-renderer';
import type { UpdateReleaseInfo, UpdateState } from '../preload/index.d';
import { sendToLiveWindow } from './window-safety';

// A Sado release carries four installers and nothing else (owner decision,
// 2026-11-23): no electron-updater feeds, blockmaps or zips. So the app does not
// update itself in place any more. It asks GitHub Releases whether a newer
// version exists — the same sanctioned call the release history already makes
// — and "Download" opens this computer's installer in the user's browser.
const REPOSITORY = 'Anvarjon090/sado';
const RELEASES_API = `https://api.github.com/repos/${REPOSITORY}/releases?per_page=30`;
const LATEST_RELEASE_API = `https://api.github.com/repos/${REPOSITORY}/releases/latest`;
const RELEASES_PAGE = `https://github.com/${REPOSITORY}/releases/latest`;
/** Only pages and downloads of this repository may be opened from an update. */
const TRUSTED_URL_PREFIX = `https://github.com/${REPOSITORY}/`;

const GITHUB_HEADERS = {
  Accept: 'application/vnd.github+json',
  'User-Agent': 'Sado',
};

export const UPDATE_CHANNELS = {
  getState: 'updates:getState',
  check: 'updates:check',
  download: 'updates:download',
  dismiss: 'updates:dismiss',
  install: 'updates:install',
  listReleases: 'updates:listReleases',
  state: 'updates:state',
} as const;

/** The release's installer for this computer, or null where none is built
 * (Windows on ARM opens the release page and can run the x64 installer). */
export function installerAssetName(
  version: string,
  platform: NodeJS.Platform = process.platform,
  arch: string = process.arch,
): string | null {
  if (platform === 'darwin')
    return `Sado-Electron-${version}-mac-${arch === 'arm64' ? 'arm64' : 'x64'}.dmg`;
  if (platform === 'win32' && arch === 'x64') return `Sado-Electron-${version}-win-x64.exe`;
  if (platform === 'linux' && arch === 'x64') return `Sado-Electron-${version}-linux-x64.AppImage`;
  return null;
}

/** Numeric x.y.z comparison; a pre-release suffix never makes a version newer. */
export function isNewerVersion(candidate: string, current: string): boolean {
  const parts = (value: string) =>
    value
      .replace(/^v/, '')
      .split(/[-+]/)[0]
      .split('.')
      .map((part) => Number.parseInt(part, 10) || 0);
  const a = parts(candidate);
  const b = parts(current);
  for (let index = 0; index < Math.max(a.length, b.length); index++) {
    const difference = (a[index] || 0) - (b[index] || 0);
    if (difference !== 0) return difference > 0;
  }
  return false;
}

function trustedUrl(value: unknown): string | null {
  return typeof value === 'string' && value.startsWith(TRUSTED_URL_PREFIX) ? value : null;
}

export interface LatestRelease {
  version: string;
  notes: string;
  /** This computer's installer, or the release page when there is none. */
  downloadUrl: string;
}

/** The newest published, non-pre-release release of Sado. */
export async function fetchLatestRelease(fetcher: typeof fetch = fetch): Promise<LatestRelease> {
  const response = await fetcher(LATEST_RELEASE_API, {
    headers: GITHUB_HEADERS,
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error(`Release check failed (${response.status})`);
  const item = (await response.json()) as Record<string, unknown> | null;
  const tag = typeof item?.tag_name === 'string' ? item.tag_name.trim() : '';
  if (!item || !tag) throw new Error('Release check returned no version');
  const version = tag.replace(/^v/, '');
  const wanted = installerAssetName(version);
  const assets = Array.isArray(item.assets) ? (item.assets as Record<string, unknown>[]) : [];
  const installer = wanted
    ? assets.find((asset) => asset && asset.name === wanted)?.browser_download_url
    : undefined;
  return {
    version,
    notes: typeof item.body === 'string' ? item.body : '',
    downloadUrl: trustedUrl(installer) || trustedUrl(item.html_url) || RELEASES_PAGE,
  };
}

export async function listDesktopReleases(
  fetcher: typeof fetch = fetch,
): Promise<UpdateReleaseInfo[]> {
  const response = await fetcher(RELEASES_API, {
    headers: GITHUB_HEADERS,
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error(`Releases request failed (${response.status})`);
  const payload: unknown = await response.json();
  if (!Array.isArray(payload)) throw new Error('Releases response was not a list');
  return payload.flatMap((value): UpdateReleaseInfo[] => {
    if (!value || typeof value !== 'object') return [];
    const item = value as Record<string, unknown>;
    const tag = typeof item.tag_name === 'string' ? item.tag_name.trim() : '';
    if (!tag) return [];
    const name = typeof item.name === 'string' && item.name.trim() ? item.name.trim() : tag;
    return [
      {
        version: tag.replace(/^v/, ''),
        name,
        date: typeof item.published_at === 'string' ? item.published_at : '',
        prerelease: item.prerelease === true,
        notes: typeof item.body === 'string' ? item.body : '',
      },
    ];
  });
}

/**
 * updates.json only ever stored the retired channel choice. Forget it so a
 * saved "preview" cannot linger.
 */
export function forgetSavedUpdateChannel(userData: string = app.getPath('userData')): void {
  try {
    rmSync(join(userData, 'updates.json'), { force: true });
  } catch {
    // Best effort: an unreadable leftover is ignored either way.
  }
}

/** Packaged builds look for updates unless a package manager owns the install. */
function updatesSupported(): boolean {
  return app.isPackaged && process.env.SADO_DISABLE_UPDATER !== '1';
}

export class DesktopUpdater {
  private listeners = new Set<(state: UpdateState) => void>();
  private state: UpdateState;
  private checkInFlight: Promise<UpdateState> | null = null;
  private downloadUrl: string = RELEASES_PAGE;

  constructor(
    private readonly fetcher: typeof fetch = fetch,
    private readonly openExternal: (url: string) => Promise<void> = (url) =>
      shell.openExternal(url),
  ) {
    this.state = {
      status: updatesSupported() ? 'idle' : 'unsupported',
      currentVersion: app.getVersion(),
      progress: 0,
    };
    forgetSavedUpdateChannel();
  }

  snapshot(): UpdateState {
    return { ...this.state };
  }

  subscribe(listener: (state: UpdateState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async check(quiet = false): Promise<UpdateState> {
    if (!updatesSupported()) return this.snapshot();
    if (this.checkInFlight) return this.checkInFlight;
    const operation = (async () => {
      this.patch({ status: 'checking', progress: 0, error: undefined });
      try {
        const latest = await fetchLatestRelease(this.fetcher);
        if (isNewerVersion(latest.version, this.state.currentVersion)) {
          this.downloadUrl = latest.downloadUrl;
          this.patch({
            status: 'available',
            availableVersion: latest.version,
            notes: latest.notes || null,
            lastCheckedAt: Date.now(),
            error: undefined,
          });
        } else {
          this.patch({
            status: 'idle',
            availableVersion: undefined,
            notes: null,
            lastCheckedAt: Date.now(),
            error: undefined,
          });
        }
      } catch (error) {
        if (quiet) this.patch({ status: 'idle', error: undefined });
        else
          this.patch({
            status: 'error',
            error: error instanceof Error ? error.message : String(error),
          });
      }
      return this.snapshot();
    })();
    this.checkInFlight = operation;
    try {
      return await operation;
    } finally {
      if (this.checkInFlight === operation) this.checkInFlight = null;
    }
  }

  /** Opens the installer in the browser; the state stays "available" so the
   * button can be used again if the download was cancelled. */
  async download(): Promise<UpdateState> {
    if (!updatesSupported() || this.state.status !== 'available') return this.snapshot();
    try {
      await this.openExternal(this.downloadUrl);
    } catch (error) {
      this.patch({
        status: 'error',
        error: error instanceof Error ? error.message : String(error),
      });
    }
    return this.snapshot();
  }

  dismiss(): UpdateState {
    if (this.state.status !== 'error') return this.snapshot();
    this.state = {
      status: 'idle',
      currentVersion: this.state.currentVersion,
      progress: 0,
      lastCheckedAt: this.state.lastCheckedAt,
    };
    this.emit();
    return this.snapshot();
  }

  /** Nothing is downloaded in-app any more, so there is nothing to install. */
  install(): void {}

  private patch(value: Partial<UpdateState>): void {
    this.state = { ...this.state, ...value };
    this.emit();
  }

  private emit(): void {
    const state = this.snapshot();
    for (const listener of this.listeners) listener(state);
  }
}

export function registerUpdateIpc(
  updater: DesktopUpdater,
  getMainWindow: () => BrowserWindow | null,
  beforeInstall: () => Promise<void>,
): () => void {
  const trusted = (event: Electron.IpcMainInvokeEvent) => {
    const owner = getMainWindow();
    if (
      !owner ||
      event.sender !== owner.webContents ||
      event.senderFrame !== owner.webContents.mainFrame ||
      !isTrustedRenderer(event.senderFrame.url, process.env.ELECTRON_RENDERER_URL)
    )
      throw new Error('Untrusted update request');
  };
  ipcMain.handle(UPDATE_CHANNELS.getState, (event) => {
    trusted(event);
    return updater.snapshot();
  });
  ipcMain.handle(UPDATE_CHANNELS.check, (event) => {
    trusted(event);
    return updater.check();
  });
  ipcMain.handle(UPDATE_CHANNELS.download, (event) => {
    trusted(event);
    return updater.download();
  });
  ipcMain.handle(UPDATE_CHANNELS.dismiss, (event) => {
    trusted(event);
    return updater.dismiss();
  });
  ipcMain.handle(UPDATE_CHANNELS.install, async (event) => {
    trusted(event);
    if (updater.snapshot().status !== 'downloaded') return;
    await beforeInstall();
    updater.install();
  });
  ipcMain.handle(UPDATE_CHANNELS.listReleases, (event) => {
    trusted(event);
    return listDesktopReleases();
  });
  const unsubscribe = updater.subscribe((state) => {
    sendToLiveWindow(getMainWindow(), UPDATE_CHANNELS.state, state);
  });
  return () => {
    unsubscribe();
    Object.values(UPDATE_CHANNELS)
      .filter((channel) => channel !== UPDATE_CHANNELS.state)
      .forEach((channel) => ipcMain.removeHandler(channel));
  };
}
