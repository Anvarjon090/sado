import { WorkspaceSidebar } from './workspace-sidebar';
import { CommandPalette } from '@/components/command-palette';
import { useState } from 'react';
import { Outlet, useRouterState } from '@tanstack/react-router';
import { BackendGate } from '../backend-gate';
import { RepairAgentDock } from './repair-agent-dock';
import { AppTitlebar, TitlebarSlotProvider } from './app-titlebar';
import { EdgePaneSlotProvider } from './edge-pane-slot';

export function AppShell() {
  const [titlebarSlot, setTitlebarSlot] = useState<HTMLDivElement | null>(null);
  const [paneSlot, setPaneSlot] = useState<HTMLDivElement | null>(null);
  const [leftSlot, setLeftSlot] = useState<HTMLDivElement | null>(null);
  // `contents` keeps the pane a direct flex child of the window row, so its
  // resize limit is measured against the window, not the slot.
  const edge = <div ref={setPaneSlot} data-slot="edge-panes" className="contents" />;
  const leftEdge = <div ref={setLeftSlot} data-slot="edge-panes-left" className="contents" />;
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  });
  const shellOnly = pathname.startsWith('/settings') || pathname === '/pro';
  const SettingsWorkspace = pathname === '/settings/openapi' ? 'div' : 'main';
  return (
    <TitlebarSlotProvider value={titlebarSlot}>
      <EdgePaneSlotProvider value={{ left: leftSlot, right: paneSlot }}>
        <div className="app-surface relative flex h-full flex-col bg-background text-foreground">
          <AppTitlebar slotRef={setTitlebarSlot} />
          <div className="flex min-h-0 flex-1">
            {shellOnly ? (
              <>
                <CommandPalette />
                {/* The main sidebar (navigation, library, status) stays where it is
                on Settings too, so the app never swaps its left column. */}
                <WorkspaceSidebar />
                {leftEdge}
                <SettingsWorkspace
                  data-slot="workspace-content"
                  role={pathname === '/settings/openapi' ? 'main' : undefined}
                  className="@container relative flex min-w-0 flex-1 flex-col overflow-hidden"
                >
                  <div className="min-h-0 flex-1 overflow-hidden">
                    <Outlet />
                  </div>
                  <RepairAgentDock />
                </SettingsWorkspace>
                {edge}
              </>
            ) : (
              <BackendGate repairDock={<RepairAgentDock />}>
                <CommandPalette />
                <WorkspaceSidebar />
                {leftEdge}
                <main
                  data-slot="workspace-content"
                  className="@container relative flex min-w-0 flex-1 flex-col overflow-hidden"
                >
                  <div className="min-h-0 flex-1 overflow-hidden">
                    <Outlet />
                  </div>
                  <RepairAgentDock />
                </main>
                {edge}
              </BackendGate>
            )}
          </div>
        </div>
      </EdgePaneSlotProvider>
    </TitlebarSlotProvider>
  );
}
