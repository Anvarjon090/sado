import { join } from 'node:path';
import { expect, it } from 'vitest';
import { brandAssetPath, trayMarkFile, windowIconFile } from './brand-assets';

it('resolves brand files from build/brand in development and resources/brand when packaged', () => {
  const location = { resourcesPath: '/res', backendRoot: '/repo' };
  expect(brandAssetPath('tray/x.png', { ...location, packaged: true })).toBe(
    join('/res', 'brand', 'tray/x.png'),
  );
  expect(brandAssetPath('tray/x.png', { ...location, packaged: false })).toBe(
    join('/repo', 'electron', 'build', 'brand', 'tray/x.png'),
  );
});

it('uses the macOS template mark and a contrasting mark elsewhere', () => {
  expect(trayMarkFile('darwin', true)).toBe('tray/trayTemplate.png');
  expect(trayMarkFile('win32', true)).toBe('tray/tray-white-16.png');
  expect(trayMarkFile('win32', false)).toBe('tray/tray-dark-16.png');
  expect(trayMarkFile('linux', true)).toBe('tray/tray-white-16.png');
});

it('gives the Windows taskbar the multi-size icon and other systems the large PNG', () => {
  expect(windowIconFile('win32')).toBe('icon/app-icon.ico');
  expect(windowIconFile('darwin')).toBe('icon/png/app-icon-indigo-512.png');
  expect(windowIconFile('linux')).toBe('icon/png/app-icon-indigo-512.png');
});
