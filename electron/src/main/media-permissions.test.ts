import { describe, expect, it, vi } from 'vitest';
import { allowsRendererPermission, installRendererPermissions } from './media-permissions';

describe('renderer permissions', () => {
  it('grants trusted audio and denies camera or foreign origins', () => {
    expect(allowsRendererPermission('media', 'app://sado/#/capture', ['audio'])).toBe(
      true,
    );
    expect(allowsRendererPermission('media', 'app://sado/#/capture', ['video'])).toBe(
      false,
    );
    expect(allowsRendererPermission('media', 'https://example.com', ['audio'])).toBe(false);
    expect(
      allowsRendererPermission('media', 'app://sado/frame.html', ['audio'], undefined, false),
    ).toBe(false);
    expect(
      allowsRendererPermission('media', 'http://localhost:3902/#/capture', ['audio'], 'http://localhost:3902'),
    ).toBe(true);
  });

  it('allows only the trusted browser permissions used by the renderer', () => {
    expect(allowsRendererPermission('clipboard-read', 'app://sado/index.html', undefined)).toBe(
      true,
    );
    expect(allowsRendererPermission('fullscreen', 'app://sado/index.html', undefined)).toBe(
      true,
    );
    expect(allowsRendererPermission('notifications', 'app://sado/index.html', undefined)).toBe(
      false,
    );
  });

  it('installs matching check and request handlers', () => {
    let check: (...args: any[]) => boolean = () => false;
    let request: (...args: any[]) => void = () => {};
    const fakeSession = {
      setPermissionCheckHandler: vi.fn((handler) => {
        check = handler;
      }),
      setPermissionRequestHandler: vi.fn((handler) => {
        request = handler;
      }),
    };
    installRendererPermissions(fakeSession as never);

    expect(
      check(null, 'media', 'app://sado', {
        isMainFrame: true,
        requestingUrl: 'app://sado/#/capture',
        mediaType: 'audio',
      }),
    ).toBe(true);
    const callback = vi.fn();
    request(
      { getURL: () => 'app://sado/#/capture' },
      'media',
      callback,
      { isMainFrame: true, requestingUrl: 'app://sado/#/capture', mediaTypes: ['video'] },
    );
    expect(callback).toHaveBeenCalledWith(false);
  });
});
