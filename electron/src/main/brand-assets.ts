import { join } from 'node:path';

/* Brand pack files (app icon, tray marks). They live in electron/build/brand
   during development and ship to resources/brand in packaged builds. */
export function brandAssetPath(
  relative: string,
  location: { packaged: boolean; resourcesPath: string; backendRoot: string },
): string {
  return location.packaged
    ? join(location.resourcesPath, 'brand', relative)
    : join(location.backendRoot, 'electron', 'build', 'brand', relative);
}

/** Window and taskbar icon. Windows gets the multi-size .ico so the taskbar
    picks a hand-tuned 16-48 px frame instead of blurring a 512 px PNG. */
export function windowIconFile(platform: NodeJS.Platform): string {
  return platform === 'win32' ? 'icon/app-icon.ico' : 'icon/png/app-icon-indigo-512.png';
}

/** The idle tray mark: a template image on macOS (the menu bar tints it),
    otherwise the variant that reads on the taskbar or panel colour. */
export function trayMarkFile(platform: NodeJS.Platform, darkPanel: boolean): string {
  if (platform === 'darwin') return 'tray/trayTemplate.png';
  return darkPanel ? 'tray/tray-white-16.png' : 'tray/tray-dark-16.png';
}
