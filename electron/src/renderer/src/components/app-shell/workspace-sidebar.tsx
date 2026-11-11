import { BrandMark } from '@/components/brand-mark';
import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { SettingsIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { buttonVariants } from '@/components/ui/button';
import { usePaneResize } from '@/hooks/use-pane-resize';
import { useWorkspace } from '@/lib/store/workspace';
import { useWorkspaceSidebarState } from './use-workspace-sidebar';
import { VoicesSidebar } from '@/features/clone/voices-sidebar';
import { WorkspaceNavigation } from './workspace-menu';
import { StatusBar } from './status-bar';
import { SystemNotifications } from './system-notifications';
import { useBackendStatus } from '@/hooks/use-backend-status';
import { isBackendReachable } from '@shared/utils/backendStage';

/* The main sidebar is two columns, like ChatGPT/Codex: a permanent icon rail
   with every workspace, and beside it the library panel (saved voices, recent
   takes, engine card) that the title bar's toggle closes back into the rail. */
export function WorkspaceSidebar() {
  const backend = useBackendStatus();
  const { t } = useTranslation();
  const { libraryOpen, libraryTab } = useWorkspace();
  // One source of truth for "rail or full sidebar": the header toggle and the
  // sidebar's own buttons used to keep separate copies of this state.
  const { compact, compactViewport, forceExpanded, secondaryWorkspace, setOpen } =
    useWorkspaceSidebarState();
  const panelOpen = libraryOpen && !compact;
  const sidebarResize = usePaneResize({
    storageKey: 'sado.library-width',
    side: 'left',
    minimum: 220,
    initial: 248,
    maximum: 360,
    reserve: compactViewport && secondaryWorkspace && forceExpanded ? 520 : 640,
    enabled: panelOpen,
  });
  const notifications = <SystemNotifications enabled={isBackendReachable(backend.stage)} compact />;
  return (
    <>
      <aside
        aria-label={t('clone.saved_profiles')}
        data-slot="compact-main-sidebar"
        onDoubleClick={() => !panelOpen && setOpen(true)}
        className="brand-sidebar relative isolate grid h-full min-h-0 w-16 shrink-0 grid-rows-[minmax(0,1fr)_auto] overflow-hidden border-r border-border/50 bg-sidebar"
      >
        <WorkspaceNavigation compact />
        <div className="flex shrink-0 flex-col items-center gap-1.5 pt-1.5 pb-3">
          {!panelOpen && <StatusBar compact inline />}
          {notifications}
          <Link
            to="/settings"
            aria-label={t('nav.settings')}
            title={t('nav.settings')}
            className={cn(
              buttonVariants({ variant: 'ghost', size: 'icon' }),
              'workspace-nav-item workspace-rail-item',
            )}
            activeProps={{ 'aria-current': 'page' }}
          >
            <SettingsIcon
              className="workspace-nav-icon size-5"
              data-tone="settings"
              data-motion="turn"
            />
          </Link>
        </div>
      </aside>
      {panelOpen && (
        <aside
          ref={sidebarResize.host}
          style={{ width: sidebarResize.width }}
          aria-label={t('clone.saved_profiles')}
          className="brand-sidebar relative isolate grid h-full min-h-0 min-w-0 shrink-0 grid-cols-[minmax(0,1fr)] grid-rows-[auto_minmax(3.25rem,1fr)_auto] overflow-hidden border-r border-border/50 bg-sidebar"
        >
          <header className="flex h-[50px] shrink-0 items-end px-[18px] pb-1">
            <Link
              to="/"
              aria-label={t('app.name')}
              className="flex min-w-0 items-center gap-2 rounded outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <BrandMark size={22} interactive className="text-sidebar-foreground" />
              <span className="truncate font-sans text-[15px] font-semibold tracking-[-0.01em]">
                {t('app.name')}
              </span>
            </Link>
          </header>
          <div
            {...sidebarResize.separatorProps}
            aria-label={t('clone.saved_profiles')}
            className="absolute inset-y-0 right-0 z-20 w-2 cursor-col-resize touch-none outline-none hover:bg-primary/15 focus-visible:bg-primary/30"
          />
          <VoicesSidebar key={libraryTab} initialTab={libraryTab} />
          <div className="flex min-w-0 shrink-0 flex-col">
            <StatusBar />
          </div>
        </aside>
      )}
    </>
  );
}
