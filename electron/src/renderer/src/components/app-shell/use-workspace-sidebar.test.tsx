import { renderHook, act } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const state = vi.hoisted(() => ({
  path: '/stories',
  narrow: true,
  layout: {
    libraryOpen: true,
    expandedLibraryContext: null as string | null,
  },
}));
vi.mock('@tanstack/react-router', () => ({
  useRouterState: ({ select }: any) => select({ location: { pathname: state.path } }),
}));
vi.mock('@/lib/store/workspace', () => ({
  useWorkspace: () => state.layout,
  setWorkspace: (patch: object) => {
    Object.assign(state.layout, patch);
  },
}));
import { useWorkspaceSidebarState } from './use-workspace-sidebar';
beforeEach(() => {
  state.path = '/stories';
  state.narrow = true;
  state.layout = { libraryOpen: true, expandedLibraryContext: null };
  vi.stubGlobal('matchMedia', () => ({
    matches: state.narrow,
    addEventListener() {},
    removeEventListener() {},
  }));
});

it('keeps the voice library open only where voices are picked', () => {
  for (const path of ['/', '/clone']) {
    state.path = path;
    const { result } = renderHook(useWorkspaceSidebarState);
    expect(result.current.compact).toBe(false);
  }
  for (const path of ['/stories', '/dub', '/settings/appearance', '/personas', '/integrations']) {
    state.path = path;
    state.narrow = false;
    const { result } = renderHook(useWorkspaceSidebarState);
    expect(result.current.compact).toBe(true);
  }
});

it('lets the title-bar toggle open the library on a page that folds it', () => {
  const { result, rerender } = renderHook(useWorkspaceSidebarState);
  expect(result.current.compact).toBe(true);
  act(() => result.current.setOpen(true));
  rerender();
  expect(result.current.compact).toBe(false);
  act(() => result.current.setOpen(false));
  rerender();
  expect(result.current.compact).toBe(true);
});

it('does not carry a forced expansion to another workspace', () => {
  const { result, rerender } = renderHook(useWorkspaceSidebarState);
  act(() => result.current.setOpen(true));
  rerender();
  state.path = '/gallery';
  rerender();
  expect(result.current.compact).toBe(true);
});

it('keeps the clone workspace toggle in sync with explicit collapse', () => {
  state.path = '/clone';
  state.narrow = false;
  const { result, rerender } = renderHook(useWorkspaceSidebarState);
  expect(result.current.compact).toBe(false);
  act(() => result.current.setOpen(false));
  rerender();
  expect(result.current.compact).toBe(true);
});
