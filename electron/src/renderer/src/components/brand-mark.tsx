import { useEffect, useState, type CSSProperties } from 'react';
import { cn } from '@/lib/utils';

export type BrandMarkState =
  | 'idle'
  | 'reveal'
  | 'listening'
  | 'processing'
  | 'speaking'
  | 'speaking-live'
  | 'success'
  | 'muted';

/* The brand mark: three rings that meet at one point on the left edge. It
   carries no letters, so it never depends on the product name. Colour comes
   from currentColor (the foreground token by default); motion comes from
   build/brand/motion/mark-motion.css, keyed by data-state. All three rings
   are drawn at every size (owner decision, 2026-11-11: no two-ring cut).
   Callers leave at least 20% of the mark's width clear around it. */
export function BrandMark({
  size = 24,
  state = 'idle',
  interactive = false,
  amplitude,
  className,
}: {
  size?: number;
  state?: BrandMarkState;
  interactive?: boolean;
  /** 0..1, drives the `speaking-live` state. */
  amplitude?: number;
  className?: string;
}) {
  const style = {
    width: size,
    height: size,
    ...(amplitude !== undefined ? { '--mark-amp': Math.max(0, Math.min(1, amplitude)) } : null),
  } as CSSProperties;
  return (
    <svg
      viewBox="0 0 140 140"
      aria-hidden="true"
      focusable="false"
      data-slot="brand-mark"
      data-state={state}
      data-interactive={interactive || undefined}
      className={cn('mark shrink-0 text-foreground', className)}
      style={style}
    >
      <circle className="mark__r3" cx="70" cy="70" r="64.5" />
      <circle className="mark__r2" cx="49" cy="70" r="43.5" />
      <circle className="mark__r1" cx="28" cy="70" r="22.5" />
    </svg>
  );
}

/** Plays the one-off reveal, then settles into `then` (processing by default). */
export function BrandMarkReveal({
  then = 'processing',
  ...props
}: Omit<Parameters<typeof BrandMark>[0], 'state'> & { then?: BrandMarkState }) {
  const [state, setState] = useState<BrandMarkState>('reveal');
  useEffect(() => {
    // 700ms reveal + 220ms stagger, as the motion sheet defines it.
    const timer = setTimeout(() => setState(then), 920);
    return () => clearTimeout(timer);
  }, [then]);
  return <BrandMark {...props} state={state} />;
}
