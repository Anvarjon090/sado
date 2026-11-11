import { createContext, useContext, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

/* Side panes belong to the window edge, not the work card: like the library,
   they sit on the frosted edge beside the card. The shell provides a slot on
   each side of the card; panes portal into it. The right side takes the
   voice sample, recent take and profile editor; the left side takes a
   page's own section list (Settings). */
type EdgeSlots = { left: HTMLElement | null; right: HTMLElement | null };
const EdgePaneSlot = createContext<EdgeSlots>({ left: null, right: null });
export const EdgePaneSlotProvider = EdgePaneSlot.Provider;
export function useEdgePaneSlot(side: 'left' | 'right' = 'right') {
  return useContext(EdgePaneSlot)[side];
}

/** Renders `children` on the given window edge, or in place without a shell. */
export function EdgePane({ side, children }: { side: 'left' | 'right'; children: ReactNode }) {
  const slot = useEdgePaneSlot(side);
  return slot ? createPortal(children, slot) : children;
}
