import { useEffect } from 'react';
import { apiFetch } from '@/lib/api/client';

/** While a speech screen is open and focused, ask again this often. Well under
 * the backend's 15-minute idle unload, so the model never lapses mid-session. */
export const TTS_WARM_INTERVAL_MS = 120_000;
/** Typing, focus and visibility changes ping too, but never more often than this. */
export const TTS_WARM_MIN_GAP_MS = 30_000;

let lastPing = Number.NEGATIVE_INFINITY;

function screenInUse(): boolean {
  return document.visibilityState === 'visible' && document.hasFocus();
}

/**
 * Tell the backend a take is about to be asked for: it keeps the TTS model
 * resident, or starts loading it now if the idle sweep released it, so the
 * reload happens while the user types instead of after they click Generate.
 * Fire-and-forget; an older backend without the route simply answers 404.
 */
export function pingTtsWarm(now = Date.now()): void {
  if (now - lastPing < TTS_WARM_MIN_GAP_MS || !screenInUse()) return;
  lastPing = now;
  void apiFetch('/tts/warm', { method: 'POST' }).catch(() => {});
}

/** Test seam: forget the throttle between cases. */
export function resetTtsWarmThrottle(): void {
  lastPing = Number.NEGATIVE_INFINITY;
}

/**
 * Keep the TTS model warm while this screen is in use. A hidden or unfocused
 * window sends nothing, so the normal idle unload still frees the GPU once the
 * user is elsewhere (a game, another app).
 */
export function useKeepTtsWarm(enabled = true): void {
  useEffect(() => {
    if (!enabled) return;
    const ping = () => pingTtsWarm();
    ping();
    const timer = window.setInterval(ping, TTS_WARM_INTERVAL_MS);
    window.addEventListener('focus', ping);
    document.addEventListener('visibilitychange', ping);
    document.addEventListener('input', ping, true);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', ping);
      document.removeEventListener('visibilitychange', ping);
      document.removeEventListener('input', ping, true);
    };
  }, [enabled]);
}
