import React from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowRight, ExternalLink, Bug, Lightbulb, Heart, ShieldAlert, Globe } from 'lucide-react';
import { Button } from '../ui';
import { Card } from '@/components/ui/card';
import { buttonVariants } from '@/components/ui/button.tsx';
import { cn } from '@/lib/utils';
import { openExternal } from '../api/external';
import ReportBugButton from '../components/ReportBugButton';

// One home for every outward channel, shared with the bug reporter and
// SECURITY.md so a link change can never leave one surface stale (#contact).
import { REPO_URL, ISSUES_URL, SECURITY_URL } from '../utils/contactLinks';

// Compact action cards for every outward channel. `kind` picks CTA behaviour:
//   bug      → reuse ReportBugButton (prefilled GitHub issue + scrubbed diag)
//   external → open a URL in the browser (via openExternal / real <a rel>)
//   internal → route to another in-app page (Support), no duplication here
const SECTIONS = [
  {
    id: 'bug',
    icon: Bug,
    hue: '#fb4934',
    kind: 'bug',
    titleKey: 'contact.bug_title',
    titleDefault: 'Report a bug',
    ctaKey: 'contact.bug_cta',
    ctaDefault: 'Open bug reporter',
  },
  {
    id: 'feature',
    icon: Lightbulb,
    hue: '#8ec07c',
    kind: 'external',
    url: ISSUES_URL,
    titleKey: 'contact.feature_title',
    titleDefault: 'Request a feature or ask',
    ctaKey: 'contact.feature_cta',
    ctaDefault: 'Open GitHub Issues',
  },
  {
    id: 'support',
    icon: Heart,
    hue: 'var(--color-brand)',
    kind: 'internal',
    titleKey: 'contact.support_title',
    titleDefault: 'Support the project',
    ctaKey: 'contact.support_cta',
    ctaDefault: 'See ways to support',
  },
  {
    id: 'security',
    icon: ShieldAlert,
    hue: '#fabd2f',
    kind: 'external',
    url: SECURITY_URL,
    titleKey: 'contact.security_title',
    titleDefault: 'Report a security issue',
    ctaKey: 'contact.security_cta',
    ctaDefault: 'Report privately',
  },
];

/**
 * ExternalCta — a subtle-button-styled link that opens in the system browser.
 * Rendered as a real `<a rel="noreferrer">` (keyboard-focusable, right-click
 * "copy link", screen-reader "link"), but the actual open is routed through
 * `openExternal` so it works inside the Tauri webview too (window.open is
 * blocked there). `preventDefault` keeps the anchor from double-navigating.
 */
function ExternalCta({
  href,
  label,
  ariaLabel,
  leading = null,
  trailing = <ExternalLink size={13} />,
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      aria-label={ariaLabel || label}
      onClick={(e) => {
        e.preventDefault();
        openExternal(href);
      }}
      className={cn(buttonVariants({ variant: 'subtle', size: 'omniSm' }), 'gap-1.5')}
    >
      {leading}
      <span>{label}</span>
      {trailing}
    </a>
  );
}

// Small mono caption with a trailing hairline — matches the Support page's
// SectionTitle so the two pages read as one family.
/**
 * The contact channels, as a SECTION rather than a page.
 *
 * Sponsor, commercial licensing and contact were three separate destinations
 * for one question — "how do I reach these people / support this" — so they
 * now live together on SupportPage. This exports the body; the page shell
 * (back button, aurora, scroll container) belongs to the host.
 */
export function ContactSections({ onSupport }) {
  const { t } = useTranslation();

  const goSupport = () => {
    if (onSupport) onSupport();
    else document.getElementById('support-give')?.scrollIntoView({ block: 'start' });
  };

  const renderCta = (s) => {
    const label = t(s.ctaKey, { defaultValue: s.ctaDefault });
    if (s.kind === 'bug') return <ReportBugButton label={label} />;
    if (s.kind === 'internal') {
      return (
        <Button variant="subtle" size="sm" trailing={<ArrowRight size={13} />} onClick={goSupport}>
          {label}
        </Button>
      );
    }
    return <ExternalCta href={s.url} label={label} />;
  };

  return (
    <>
      <section
        className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-2.5"
        aria-label={t('contact.channels_label', { defaultValue: 'Ways to get in touch' })}
      >
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          return (
            <Card
              key={s.id}
              style={{ '--card-hue': s.hue }}
              className="h-full flex-row flex-wrap items-center gap-2.5 rounded-md border-border bg-transparent p-3 shadow-none transition-colors hover:border-border-strong hover:bg-[var(--chrome-hover-bg)]"
            >
              <span className="flex size-9 shrink-0 items-center justify-center rounded-md border border-transparent bg-[color-mix(in_srgb,var(--card-hue)_12%,transparent)] text-[var(--card-hue)]">
                <Icon size={17} />
              </span>
              <h3 className="min-w-[120px] flex-1 font-serif text-[1rem] font-medium leading-snug text-[var(--chrome-fg)]">
                {t(s.titleKey, { defaultValue: s.titleDefault })}
              </h3>
              <div className="shrink-0">{renderCta(s)}</div>
            </Card>
          );
        })}
      </section>

      <div className="flex flex-wrap items-center justify-center gap-2">
        <ExternalCta
          href={REPO_URL}
          label={t('contact.website', { defaultValue: 'Website' })}
          ariaLabel={t('contact.website_desc', {
            defaultValue: 'Website — more about the project',
          })}
          leading={<Globe size={13} />}
        />
      </div>
    </>
  );
}

export default ContactSections;
