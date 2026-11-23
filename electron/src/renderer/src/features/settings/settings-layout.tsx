import { Beam } from '@/components/motion-fx';
// Adapted from T3 Code's settingsLayout and WorkspacePageContainer (MIT).
// See electron/T3CODE-LICENSE.txt.
import { createContext, useContext, type ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

/* A heading that repeats the heading above it says nothing new. The page title
   lives in the window title bar; a section titled the same as the page, or a
   row titled the same as its section, keeps its heading for assistive
   technology only. */
const PageTitleContext = createContext<string | null>(null);
const SectionTitleContext = createContext<string | null>(null);

const sameTitle = (a: ReactNode, b: string | null) =>
  typeof a === 'string' &&
  b !== null &&
  a.trim().toLocaleLowerCase() === b.trim().toLocaleLowerCase();

export function SettingsContent({
  children,
  fullBleed = false,
  title = null,
}: {
  children: ReactNode;
  fullBleed?: boolean;
  /** The page title shown in the title bar; matching section headings hide. */
  title?: string | null;
}) {
  return (
    <PageTitleContext.Provider value={title}>
      <div
        className={cn(
          '@container min-h-0 min-w-0 flex-1',
          fullBleed ? 'overflow-hidden' : 'overflow-y-auto [scrollbar-gutter:stable]',
        )}
      >
        <div
          className={cn(
            'flex w-full min-w-0 flex-col',
            // One readable column (DESIGN.md content-max): values stay close
            // to the labels they belong to on wide windows.
            fullBleed ? 'h-full min-h-0' : 'mx-auto max-w-[60rem] gap-8 px-4 pt-6 pb-12 @xl:px-6',
          )}
        >
          {children}
        </div>
      </div>
    </PageTitleContext.Provider>
  );
}

export function SettingsSection({
  title,
  children,
  icon: Icon,
  contentVariant = 'rows',
  id,
}: {
  title: string;
  children: ReactNode;
  icon?: LucideIcon;
  contentVariant?: 'rows' | 'cards';
  id?: string;
}) {
  const pageTitle = useContext(PageTitleContext);
  const repeatsPage = sameTitle(title, pageTitle);
  return (
    <SectionTitleContext.Provider value={title}>
      <section id={id} className="min-w-0 scroll-mt-6 space-y-3">
        <h2
          className={
            repeatsPage
              ? 'sr-only'
              : 'flex min-h-7 items-center gap-2 px-1 text-[15px] font-semibold tracking-[-0.01em] text-foreground'
          }
        >
          {Icon && <Icon aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />}
          {title}
        </h2>
        <div
          className={cn(
            contentVariant === 'rows'
              ? 'rounded-xl border border-border bg-card [&>*+*]:border-t [&>*+*]:border-border'
              : 'grid grid-cols-[repeat(auto-fill,minmax(min(100%,17rem),1fr))] gap-3',
          )}
        >
          {children}
        </div>
      </section>
    </SectionTitleContext.Provider>
  );
}

export function SettingsRow({
  className,
  id,
  title,
  titleHidden = false,
  description,
  children,
  variant = 'row',
  layout = 'inline',
  active = false,
}: {
  className?: string;
  id: string;
  title: ReactNode;
  titleHidden?: boolean;
  description?: ReactNode;
  children: ReactNode;
  variant?: 'row' | 'card';
  /** `stacked` puts a multi-field form under its title instead of beside it. */
  layout?: 'inline' | 'stacked';
  active?: boolean;
}) {
  const sectionTitle = useContext(SectionTitleContext);
  const pageTitle = useContext(PageTitleContext);
  const hideTitle =
    titleHidden ||
    (variant === 'row' && (sameTitle(title, sectionTitle) || sameTitle(title, pageTitle)));
  const row = (
    <div
      data-slot="settings-row"
      data-active={active || undefined}
      className={cn(
        'px-4 py-3.5',
        variant === 'card' &&
          'h-full min-h-40 rounded-xl border border-border bg-card transition-colors duration-150 hover:border-foreground/20 data-[active]:border-primary/55 motion-reduce:transition-none',
        className,
      )}
    >
      <div
        className={cn(
          'flex min-w-0 flex-col items-stretch gap-3',
          // Inline rows wrap their controls under the title rather than
          // squeezing the title to nothing when the controls are wide.
          variant === 'row' && layout === 'inline'
            ? '@2xl:flex-row @2xl:flex-wrap @2xl:items-center @2xl:justify-between @2xl:gap-x-8'
            : variant === 'card'
              ? 'h-full'
              : '',
        )}
      >
        <div
          className={cn(
            'min-w-0 flex-1 space-y-1',
            // A floor for the title beside wide controls; horizontal rows only.
            variant === 'row' && layout === 'inline' && '@2xl:basis-56',
          )}
        >
          <h3
            tabIndex={-1}
            id={id}
            className={hideTitle ? 'sr-only' : 'min-h-5 text-sm font-medium tracking-[-0.005em]'}
          >
            {title}
          </h3>
          {description && (
            <div className="max-w-[62ch] text-[13px] leading-[1.45] text-muted-foreground [overflow-wrap:anywhere]">
              {description}
            </div>
          )}
        </div>
        {/* Controls never outgrow the row: a flex item's default minimum is its
            min-content width, so a long one-line notice used to push past the
            card edge. */}
        <div
          role="group"
          aria-labelledby={id}
          className={cn(
            'flex min-w-0 max-w-full flex-wrap items-center gap-2 [&>*]:min-w-0 [&>*]:max-w-full [&_input]:max-w-full [&_button]:max-w-full',
            variant === 'card'
              ? 'mt-auto justify-start'
              : layout === 'stacked'
                ? 'justify-start'
                : '@2xl:justify-end',
          )}
        >
          {children}
        </div>
      </div>
    </div>
  );
  // A chosen card (the selected model, the active engine) breathes softly.
  return variant === 'card' ? (
    <Beam size="pulse-inner" active={active} className="h-full min-w-0">
      {row}
    </Beam>
  ) : (
    row
  );
}

export function SettingsRowsSkeleton({ label, rows = 2 }: { label: string; rows?: number }) {
  return (
    <div role="status" aria-label={label} className="divide-y divide-border">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} aria-hidden="true" className="flex min-h-14 items-center gap-6 px-4 py-3">
          <div className="min-w-0 flex-1 space-y-2">
            <div className="h-3.5 w-full max-w-52 animate-pulse rounded bg-muted motion-reduce:animate-none" />
            <div className="h-2.5 w-full max-w-72 animate-pulse rounded bg-muted/70 motion-reduce:animate-none" />
          </div>
          <div className="h-7 w-20 shrink-0 animate-pulse rounded-lg bg-muted motion-reduce:animate-none" />
        </div>
      ))}
    </div>
  );
}
