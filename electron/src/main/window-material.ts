/* Native window material for Sado's frosted edges.

   The sidebar and toolbar let the desktop behind the window show through, the
   way macOS sidebars and Windows 11 apps do. That needs the operating system's
   own material: macOS vibrancy, or Mica/Acrylic on Windows 11 (build 22000+).
   Everywhere else (Windows 10, Linux) the window stays opaque and the renderer
   paints its normal background, so the app looks and behaves the same, just
   without the see-through effect. */

export type WindowMaterial = 'vibrancy' | 'acrylic' | null;

const WINDOWS_11_BUILD = 22000;

export function windowMaterial(platform: NodeJS.Platform, release: string): WindowMaterial {
  if (platform === 'darwin') return 'vibrancy';
  if (platform === 'win32') {
    const build = Number(release.split('.')[2]);
    return Number.isFinite(build) && build >= WINDOWS_11_BUILD ? 'acrylic' : null;
  }
  return null;
}

/** BrowserWindow options for the chosen material; empty when unsupported. */
export function windowMaterialOptions(material: WindowMaterial) {
  if (material === 'vibrancy') {
    return {
      vibrancy: 'under-window' as const,
      visualEffectState: 'active' as const,
      backgroundColor: '#00000000',
    };
  }
  if (material === 'acrylic') {
    return { backgroundMaterial: 'acrylic' as const, backgroundColor: '#00000000' };
  }
  return {};
}
