import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const fetchMock = vi.fn(async (_path: string, _init?: RequestInit) => new Response('{}'));
vi.mock('@/lib/api/client', () => ({
  apiFetch: (path: string, init?: RequestInit) => fetchMock(path, init),
}));

import {
  pingTtsWarm,
  resetTtsWarmThrottle,
  TTS_WARM_INTERVAL_MS,
  TTS_WARM_MIN_GAP_MS,
  useKeepTtsWarm,
} from './use-keep-tts-warm';

let focused = true;

beforeEach(() => {
  vi.useFakeTimers();
  focused = true;
  vi.spyOn(document, 'hasFocus').mockImplementation(() => focused);
  resetTtsWarmThrottle();
  fetchMock.mockClear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('useKeepTtsWarm', () => {
  it('warms on open and again while the screen stays in use', () => {
    const { unmount } = renderHook(() => useKeepTtsWarm());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith('/tts/warm', { method: 'POST' });

    vi.advanceTimersByTime(TTS_WARM_INTERVAL_MS);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    unmount();
    vi.advanceTimersByTime(TTS_WARM_INTERVAL_MS * 3);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('pings on typing, but not more often than the minimum gap', () => {
    renderHook(() => useKeepTtsWarm());
    document.dispatchEvent(new Event('input'));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(TTS_WARM_MIN_GAP_MS);
    document.dispatchEvent(new Event('input'));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('sends nothing while the window is not focused, so the idle unload can free the GPU', () => {
    focused = false;
    renderHook(() => useKeepTtsWarm());
    vi.advanceTimersByTime(TTS_WARM_INTERVAL_MS * 5);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('does nothing when disabled', () => {
    renderHook(() => useKeepTtsWarm(false));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('swallows a backend without the route', async () => {
    fetchMock.mockRejectedValueOnce(new Error('404'));
    expect(() => pingTtsWarm()).not.toThrow();
    await Promise.resolve();
  });
});
