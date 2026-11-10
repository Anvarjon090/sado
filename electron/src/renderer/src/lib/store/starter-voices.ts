import { Store } from '@tanstack/store';
import { useStore } from '@tanstack/react-store';

/**
 * Whether the Voices page still offers Sado's starter pack. The offer is a
 * per-device convenience: declined or installed once, it stays out of the
 * way. The voices themselves live in the backend's profile library.
 */
export const STARTER_VOICES_STORAGE_KEY = 'sado.starter-voices.v1';

export type StarterVoicesOffer = 'pending' | 'dismissed' | 'installed';

const OFFERS: readonly StarterVoicesOffer[] = ['pending', 'dismissed', 'installed'];

export function parseStarterVoicesOffer(raw: string | null | undefined): StarterVoicesOffer {
  if (!raw) return 'pending';
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return 'pending';
  }
  const offer =
    parsed && typeof parsed === 'object' ? (parsed as { offer?: unknown }).offer : undefined;
  return OFFERS.includes(offer as StarterVoicesOffer) ? (offer as StarterVoicesOffer) : 'pending';
}

function readStorage(): string | null {
  try {
    return typeof localStorage === 'undefined'
      ? null
      : localStorage.getItem(STARTER_VOICES_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStorage(state: { offer: StarterVoicesOffer }): void {
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(STARTER_VOICES_STORAGE_KEY, JSON.stringify(state));
    }
  } catch {
    // Quota / privacy mode — the in-memory store is still authoritative.
  }
}

export const starterVoicesStore = new Store<{ offer: StarterVoicesOffer }>({
  offer: parseStarterVoicesOffer(readStorage()),
});
starterVoicesStore.subscribe(() => writeStorage(starterVoicesStore.state));

export function useStarterVoicesOffer(): StarterVoicesOffer {
  return useStore(starterVoicesStore, (state) => state.offer);
}

export function setStarterVoicesOffer(offer: StarterVoicesOffer): void {
  starterVoicesStore.setState((prev) => (prev.offer === offer ? prev : { offer }));
}
