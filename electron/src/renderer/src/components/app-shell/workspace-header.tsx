import { createPortal } from 'react-dom';
import type { ReactNode } from 'react';
import { useTitlebarSlot } from './app-titlebar';

/* A page's title and actions. Inside the app shell they render in the
   window-wide title bar; on their own (tests, isolated previews) they keep a
   plain header so the page still reads correctly. */
export function WorkspaceHeader({ children }: { children: ReactNode }) {
  const slot = useTitlebarSlot();
  if (slot) return createPortal(children, slot);
  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border/50 px-5">
      {children}
    </header>
  );
}
