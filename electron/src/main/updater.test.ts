import { beforeEach, describe, expect, test, vi } from 'vitest';

const mocks = vi.hoisted(() => {
  const ipcHandlers = new Map<string, (...args: any[]) => unknown>();
  const fs = { rmSync: vi.fn() };
  return {
    app: {
      isPackaged: true,
      getVersion: vi.fn(() => '0.5.10'),
      getPath: vi.fn(() => 'C:\\Sado-test'),
    },
    fs,
    ipcHandlers,
    ipcMain: {
      handle: vi.fn((channel: string, handler: (...args: any[]) => unknown) => {
        ipcHandlers.set(channel, handler);
      }),
      removeHandler: vi.fn((channel: string) => ipcHandlers.delete(channel)),
    },
    shell: { openExternal: vi.fn(async () => undefined) },
    trusted: vi.fn(() => true),
  };
});

vi.mock('electron', () => ({
  app: mocks.app,
  BrowserWindow: class BrowserWindow {},
  ipcMain: mocks.ipcMain,
  shell: mocks.shell,
}));

vi.mock('node:fs', () => ({ ...mocks.fs, default: mocks.fs }));

vi.mock('./trusted-renderer', () => ({ isTrustedRenderer: mocks.trusted }));

import {
  DesktopUpdater,
  fetchLatestRelease,
  installerAssetName,
  isNewerVersion,
  listDesktopReleases,
  registerUpdateIpc,
  UPDATE_CHANNELS,
} from './updater';

const RELEASE_PAGE = 'https://github.com/Anvarjon090/sado/releases/tag/v0.5.11';

function release(overrides: Record<string, unknown> = {}) {
  const version = String(overrides.tag_name ?? 'v0.5.11').replace(/^v/, '');
  return {
    tag_name: `v${version}`,
    html_url: RELEASE_PAGE,
    body: 'Faster speech',
    assets: ['mac-arm64.dmg', 'mac-x64.dmg', 'win-x64.exe', 'linux-x64.AppImage'].map((suffix) => ({
      name: `Sado-Electron-${version}-${suffix}`,
      browser_download_url: `https://github.com/Anvarjon090/sado/releases/download/v${version}/Sado-Electron-${version}-${suffix}`,
    })),
    ...overrides,
  };
}

function respond(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.ipcHandlers.clear();
  mocks.app.isPackaged = true;
  mocks.app.getVersion.mockReturnValue('0.5.10');
  mocks.trusted.mockReturnValue(true);
});

describe('release lookup', () => {
  test('names the one installer each computer gets', () => {
    expect(installerAssetName('0.5.11', 'darwin', 'arm64')).toBe(
      'Sado-Electron-0.5.11-mac-arm64.dmg',
    );
    expect(installerAssetName('0.5.11', 'darwin', 'x64')).toBe('Sado-Electron-0.5.11-mac-x64.dmg');
    expect(installerAssetName('0.5.11', 'win32', 'x64')).toBe('Sado-Electron-0.5.11-win-x64.exe');
    expect(installerAssetName('0.5.11', 'linux', 'x64')).toBe(
      'Sado-Electron-0.5.11-linux-x64.AppImage',
    );
    expect(installerAssetName('0.5.11', 'win32', 'arm64')).toBeNull();
  });

  test('compares versions numerically', () => {
    expect(isNewerVersion('0.5.11', '0.5.10')).toBe(true);
    expect(isNewerVersion('v0.6.0', '0.5.99')).toBe(true);
    expect(isNewerVersion('0.5.10', '0.5.10')).toBe(false);
    expect(isNewerVersion('0.5.9', '0.5.10')).toBe(false);
    expect(isNewerVersion('0.5.10-beta', '0.5.10')).toBe(false);
  });

  test('points at this computer’s installer, and at the page when there is none', async () => {
    const latest = await fetchLatestRelease(respond(release()));
    expect(latest.version).toBe('0.5.11');
    expect(latest.downloadUrl).toMatch(
      new RegExp(`/v0\\.5\\.11/${installerAssetName('0.5.11')?.replace(/\./g, '\\.') ?? 'none'}$`),
    );

    const noInstaller = await fetchLatestRelease(respond(release({ assets: [] })));
    expect(noInstaller.downloadUrl).toBe(RELEASE_PAGE);
  });

  test('never opens a link outside the repository', async () => {
    const latest = await fetchLatestRelease(
      respond(
        release({
          html_url: 'https://evil.invalid/sado',
          assets: [
            {
              name: installerAssetName('0.5.11'),
              browser_download_url: 'https://evil.invalid/installer',
            },
          ],
        }),
      ),
    );
    expect(latest.downloadUrl).toBe('https://github.com/Anvarjon090/sado/releases/latest');
  });

  test('loads and validates release history without trusting GitHub response fields', async () => {
    const fetcher = respond([
      {
        tag_name: 'v0.5.2',
        name: 'Sado 0.5.2',
        published_at: '2026-09-12T12:00:00Z',
        prerelease: false,
        body: 'Ready',
      },
      { name: 'missing tag' },
    ]);
    await expect(listDesktopReleases(fetcher)).resolves.toEqual([
      {
        version: '0.5.2',
        name: 'Sado 0.5.2',
        date: '2026-09-12T12:00:00Z',
        prerelease: false,
        notes: 'Ready',
      },
    ]);
    expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining('/Anvarjon090/sado/releases?per_page=30'),
      expect.objectContaining({
        headers: expect.objectContaining({ 'User-Agent': 'Sado' }),
        signal: expect.any(AbortSignal),
      }),
    );
  });
});

describe('DesktopUpdater', () => {
  test('reports a newer release and opens its installer in the browser', async () => {
    const opened = vi.fn(async () => undefined);
    const updater = new DesktopUpdater(respond(release()), opened);
    const seen: string[] = [];
    updater.subscribe((state) => seen.push(state.status));

    await updater.check();
    expect(updater.snapshot()).toMatchObject({
      status: 'available',
      availableVersion: '0.5.11',
      notes: 'Faster speech',
      currentVersion: '0.5.10',
    });
    expect(seen).toEqual(['checking', 'available']);

    await updater.download();
    expect(opened).toHaveBeenCalledWith(expect.stringContaining('github.com/Anvarjon090/sado/'));
    // Nothing downloads in-app: the button stays usable for a cancelled download.
    expect(updater.snapshot().status).toBe('available');
  });

  test('stays idle when the running version is current', async () => {
    mocks.app.getVersion.mockReturnValue('0.5.11');
    const updater = new DesktopUpdater(respond(release()));
    await updater.check();
    expect(updater.snapshot()).toMatchObject({ status: 'idle', availableVersion: undefined });
    expect(updater.snapshot().lastCheckedAt).toEqual(expect.any(Number));
  });

  test('a background check fails quietly; a requested one says why', async () => {
    const offline = vi.fn().mockRejectedValue(new Error('fetch failed'));
    const updater = new DesktopUpdater(offline);
    await updater.check(true);
    expect(updater.snapshot()).toMatchObject({ status: 'idle', error: undefined });
    await updater.check();
    expect(updater.snapshot()).toMatchObject({ status: 'error', error: 'fetch failed' });
    expect(updater.dismiss()).toMatchObject({ status: 'idle' });
  });

  test('shares one request between overlapping checks', async () => {
    const fetcher = respond(release());
    const updater = new DesktopUpdater(fetcher);
    await Promise.all([updater.check(), updater.check(true)]);
    expect(fetcher).toHaveBeenCalledOnce();
  });

  test('stays unsupported when a package manager owns the install', async () => {
    vi.stubEnv('SADO_DISABLE_UPDATER', '1');
    try {
      const fetcher = respond(release());
      const updater = new DesktopUpdater(fetcher);
      expect(updater.snapshot()).toMatchObject({ status: 'unsupported' });
      await updater.check();
      await updater.download();
      expect(fetcher).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllEnvs();
    }
  });

  test('forgets the retired update-channel file', () => {
    new DesktopUpdater(respond(release()));
    expect(mocks.fs.rmSync).toHaveBeenCalledWith(expect.stringContaining('updates.json'), {
      force: true,
    });
  });
});

describe('update IPC', () => {
  test('serves state to the app window and rejects foreign renderers', async () => {
    const updater = new DesktopUpdater(
      respond(release()),
      vi.fn(async () => undefined),
    );
    const webContents = {
      mainFrame: { url: 'app://sado/index.html' },
      send: vi.fn(),
      isDestroyed: () => false,
    };
    const owner = { webContents, isDestroyed: () => false } as any;
    const dispose = registerUpdateIpc(
      updater,
      () => owner,
      vi.fn(async () => undefined),
    );
    const event = { sender: webContents, senderFrame: webContents.mainFrame };

    await mocks.ipcHandlers.get(UPDATE_CHANNELS.check)!(event);
    expect(mocks.ipcHandlers.get(UPDATE_CHANNELS.getState)!(event)).toMatchObject({
      status: 'available',
    });
    expect(() =>
      mocks.ipcHandlers.get(UPDATE_CHANNELS.getState)!({
        sender: {},
        senderFrame: { url: 'https://attacker.invalid' },
      }),
    ).toThrow('Untrusted update request');

    dispose();
    expect(mocks.ipcMain.removeHandler).toHaveBeenCalledTimes(6);
  });
});
