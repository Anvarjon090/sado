import { useSyncExternalStore } from 'react';
import { useRouterState } from '@tanstack/react-router';
import { setWorkspace, useWorkspace } from '@/lib/store/workspace';

const SECONDARY_ROUTES = new Set([
  '/stories',
  '/audiobook',
  '/tools',
  '/batch',
  '/gallery',
  '/personas',
  '/projects',
  '/dub',
  '/design',
  '/transcriptions',
  '/calls',
  '/settings',
]);
// A local-controls pane needs enough room for the actual workspace. At the
// default desktop window, preserve navigation as a rail and restore the full
// voice library automatically once both it and a local-controls pane leave a
// useful editing canvas. Browser zoom and Windows display scaling are included
// in the CSS viewport width, so this threshold also covers high-DPI layouts.
const COMPACT_QUERY = '(max-width: 1680px)';

function routeHasSecondarySidebar(pathname: string): boolean {
  const normalized = pathname.replace(/\/+$/, '') || '/';
  return [...SECONDARY_ROUTES].some(
    (route) => normalized === route || normalized.startsWith(`${route}/`),
  );
}

// The voice library is only open where voices are picked: Home and Voice
// cloning. Every other workspace has its own side panel or none, so the
// library folds into the rail there; the title-bar toggle brings it back on
// that page when someone wants it.
function routeShowsLibrary(pathname: string): boolean {
  const normalized = pathname.replace(/\/+$/, '') || '/';
  return normalized === '/' || normalized === '/clone' || normalized.startsWith('/clone/');
}

function useCompactViewport(): boolean {
  return useSyncExternalStore(
    (notify) => {
      const query = window.matchMedia(COMPACT_QUERY);
      query.addEventListener('change', notify);
      return () => query.removeEventListener('change', notify);
    },
    () => window.matchMedia(COMPACT_QUERY).matches,
    () => false,
  );
}

export function useWorkspaceSidebarState() {
  const { libraryOpen, expandedLibraryContext } = useWorkspace();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const compactViewport = useCompactViewport();
  const compactContext = `${pathname}:${compactViewport}`;
  const forceExpanded = expandedLibraryContext === compactContext;
  const compact = !libraryOpen || (!routeShowsLibrary(pathname) && !forceExpanded);
  const setOpen = (open: boolean) =>
    setWorkspace({ libraryOpen: open, expandedLibraryContext: open ? compactContext : null });
  return {
    compact,
    compactViewport,
    forceExpanded,
    secondaryWorkspace: routeHasSecondarySidebar(pathname),
    setOpen,
  };
}
