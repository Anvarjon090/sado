import { describe, expect, it } from 'vitest';
import { windowMaterial, windowMaterialOptions } from './window-material';

describe('windowMaterial', () => {
  it('uses vibrancy on macOS', () => {
    expect(windowMaterial('darwin', '24.1.0')).toBe('vibrancy');
  });

  it('uses acrylic only on Windows 11 builds', () => {
    expect(windowMaterial('win32', '10.0.26200')).toBe('acrylic');
    expect(windowMaterial('win32', '10.0.22000')).toBe('acrylic');
    expect(windowMaterial('win32', '10.0.19045')).toBeNull();
    expect(windowMaterial('win32', 'unknown')).toBeNull();
  });

  it('keeps Linux opaque', () => {
    expect(windowMaterial('linux', '6.8.0')).toBeNull();
  });

  it('only makes the window background transparent when a material exists', () => {
    expect(windowMaterialOptions(null)).toEqual({});
    expect(windowMaterialOptions('acrylic')).toMatchObject({
      backgroundMaterial: 'acrylic',
      backgroundColor: '#00000000',
    });
    expect(windowMaterialOptions('vibrancy')).toMatchObject({ vibrancy: 'under-window' });
  });
});
