import { createContext, useContext } from 'react';
import { PanelLeftIcon, SearchIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { isMac } from '@/components/bridge';
import { cn } from '@/lib/utils';
import { useWorkspace } from '@/lib/store/workspace';
import { useWorkspaceSidebarState } from './use-workspace-sidebar';

/* One title bar spans the whole window, above the rail, the library and the
   workspace: the library toggle on the left, the current page's title and
   actions in the middle, search on the right. Pages put their title and
   actions here through <WorkspaceHeader>, which portals into the slot. */
const TitlebarSlot = createContext<HTMLElement | null>(null);
export const TitlebarSlotProvider = TitlebarSlot.Provider;
export function useTitlebarSlot() {
  return useContext(TitlebarSlot);
}

export function AppTitlebar({ slotRef }: { slotRef: (node: HTMLDivElement | null) => void }) {
  const { t } = useTranslation();
  const mac = isMac();
  const { libraryOpen } = useWorkspace();
  const { compact, setOpen } = useWorkspaceSidebarState();
  const panelOpen = libraryOpen && !compact;
  return (
    <header
      data-slot="app-titlebar"
      className={cn(
        'workspace-titlebar app-titlebar flex shrink-0 items-center gap-3.5 border-b border-border/50 pl-[18px]',
        mac ? 'pr-3.5' : 'native-controls-right',
      )}
    >
      <div className={cn('flex w-[286px] shrink-0 items-center', mac && 'pl-[72px]')}>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={t('clone.toggle_sidebar')}
          title={t('clone.toggle_sidebar')}
          aria-expanded={panelOpen}
          onClick={() => setOpen(!panelOpen)}
          className="-ml-1.5 shrink-0"
        >
          <PanelLeftIcon className="size-[17px]" aria-hidden="true" />
        </Button>
      </div>
      <div
        ref={slotRef}
        data-slot="titlebar-content"
        className="flex min-w-0 flex-1 items-center gap-2.5"
      />
      <button
        type="button"
        data-slot="titlebar-search"
        aria-label={t('preferences.search')}
        title={mac ? 'Command + K' : 'Ctrl + K'}
        onClick={() => window.dispatchEvent(new Event('sado:commands'))}
        className="flex h-[30px] shrink-0 items-center gap-2 rounded-lg border border-border/60 bg-foreground/[0.06] px-2.5 text-xs text-muted-foreground outline-none transition-colors hover:bg-foreground/10 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
      >
        <SearchIcon className="size-3.5" aria-hidden="true" />
        <span className="hidden sm:inline">{t('preferences.search')}</span>
        <kbd className="font-sans font-medium tabular-nums">{mac ? '⌘K' : 'Ctrl K'}</kbd>
      </button>
    </header>
  );
}
