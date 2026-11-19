import '@testing-library/jest-dom/vitest';

// jsdom has no matchMedia or ResizeObserver; the motion libraries (border-beam,
// voice-glow, thinking-orbs) read both on mount. Tests that need a specific
// media result still stub matchMedia themselves.
if (typeof window !== 'undefined') {
  if (!window.matchMedia) {
    window.matchMedia = (query: string) =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener() {},
        removeEventListener() {},
        addListener() {},
        removeListener() {},
        dispatchEvent: () => false,
      }) as MediaQueryList;
  }
  const host = window as { ResizeObserver?: typeof ResizeObserver };
  if (!host.ResizeObserver) {
    host.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver;
  }
}
