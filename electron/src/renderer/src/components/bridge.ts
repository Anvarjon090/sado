/** The preload contract, reached through the global augmentation in src/preload/index.d.ts. */
export type SadoBridge = Window['sado'];

/** The preload bridge, or null outside Electron (vitest, a plain browser tab). */
export function getBridge(): SadoBridge | null {
  if (typeof window === 'undefined') return null;
  return 'sado' in window && window.sado ? window.sado : null;
}

export function appVersion(): string {
  return getBridge()?.app.version ?? __APP_VERSION__;
}

export function isMac(): boolean {
  return getBridge()?.app.platform === 'darwin';
}
