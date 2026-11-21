import { EdgePane } from '@/components/app-shell/edge-pane-slot';
import { WorkspaceHeader } from '@/components/app-shell/workspace-header';
import { UpdateSettings } from './update-settings';
import { MirrorSettings } from './mirror-settings';
import { StorageSettings } from './storage-settings';
import { PrivacySettings } from './privacy-settings';
import { PerformanceSettings, SpeedQualitySettings } from './performance-settings';
import { CredentialSettings } from './credential-settings';
import { NetworkSettings } from './network-settings';
import { SharingSettings } from './sharing-settings';
import { MediaTools } from './media-tools';
import { LogSettings } from './log-settings';
import { PronunciationSettings } from './pronunciation-settings';
import { PermissionsSettings } from './permissions-settings';
import { UsageSettings } from './usage-settings';
import { WorkersSettings } from './workers-settings';
import { OpenApiSettings } from './openapi-settings';
import { DiagnosticsSettings } from './diagnostics-settings';
import { ModelSettings } from './model-settings';
import { familyIcons, modelFamilies, type ModelFamily } from './model-family';
import { Link, useRouterState } from '@tanstack/react-router';
import {
  ArrowLeftIcon,
  BarChart3Icon,
  BoxesIcon,
  BracesIcon,
  ChevronRightIcon,
  ClipboardCheckIcon,
  CpuIcon,
  FileTextIcon,
  GaugeIcon,
  HardDriveIcon,
  KeyRoundIcon,
  LanguagesIcon,
  MonitorIcon,
  MoonIcon,
  PaletteIcon,
  RefreshCwIcon,
  RotateCcwIcon,
  SearchIcon,
  Settings2Icon,
  SettingsIcon,
  Share2Icon,
  ShieldCheckIcon,
  SpellCheckIcon,
  StethoscopeIcon,
  SunIcon,
  WifiIcon,
  WrenchIcon,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { PalettePicker } from './palette-picker';
import { useTheme } from '@/hooks/use-theme';
import { appearanceScales, useAppearance } from '@/hooks/use-appearance';
import { cn } from '@/lib/utils';
import { SettingsContent, SettingsRow, SettingsSection } from './settings-layout';
import i18n, { APP_LANGUAGE_ITEMS, APP_LANGUAGES, setAppLanguage, type AppLocale } from '@/i18n';
import { setReviewMode, useReviewMode } from '@/hooks/use-review-mode';
import { readLastWorkspaceRoute, rememberSettingsRoute } from '@/lib/settings-route';

type PageId =
  | 'general'
  | 'appearance'
  | 'pronunciation'
  | 'updates'
  | 'models'
  | 'speed'
  | 'media'
  | 'performance'
  | 'usage'
  | 'privacy'
  | 'storage'
  | 'network'
  | 'credentials'
  | 'sharing'
  | 'diagnostics'
  | 'logs'
  | 'openapi';

interface NavItem {
  id: PageId;
  to: string;
  /** Older paths that open this page (deep links, notifications). */
  aliases?: Record<string, string>;
  label: string;
  Icon: LucideIcon;
  /** i18n keys of the settings on the page, so search finds what is inside. */
  keywords: string[];
  /** Untranslated technical terms people type: ffmpeg, GPU, Tailscale… */
  terms?: string[];
}

interface NavGroup {
  id: string;
  label: string;
  /** Folded until opened, searched or visited: support tools, not daily ones. */
  foldable?: boolean;
  items: NavItem[];
}

/* One home per setting (DESIGN.md "One Place"): every page appears once, in the
   group a person would look for it in. Old paths stay valid as aliases. */
const NAV: NavGroup[] = [
  {
    id: 'app',
    label: 'settingsNav.group_app',
    items: [
      {
        id: 'general',
        to: '/settings/general',
        label: 'preferences.general',
        Icon: Settings2Icon,
        keywords: ['settings.language', 'settings.language_desc', 'settings.review_mode'],
      },
      {
        id: 'appearance',
        to: '/settings/appearance',
        label: 'preferences.appearance',
        Icon: PaletteIcon,
        keywords: [
          'preferences.theme',
          'preferences.font',
          'preferences.ui_scale',
          'themeAppearance.glass',
          'themeAppearance.light',
          'themeAppearance.dark',
        ],
      },
      {
        id: 'pronunciation',
        to: '/settings/pronunciation',
        label: 'pronunciation.title',
        Icon: SpellCheckIcon,
        keywords: ['pronunciation.help', 'pronunciation.test_label', 'pronunciation.backup_title'],
      },
      {
        id: 'updates',
        to: '/settings/updates',
        label: 'updates.tab',
        Icon: RefreshCwIcon,
        keywords: ['updates.check_now', 'update.whats_new', 'updates.releases'],
      },
    ],
  },
  {
    id: 'voices',
    label: 'settingsNav.group_voices',
    items: [
      {
        id: 'models',
        to: '/settings/models',
        label: 'modelSettings.models',
        Icon: BoxesIcon,
        keywords: modelFamilies.map((family) => 'engineSidebar.' + family),
        terms: ['TTS', 'ASR', 'OmniVoice', 'Navoiy', 'Whisper', 'LLM', 'shortcut', 'hotkey'],
      },
      {
        id: 'speed',
        to: '/settings/speed',
        label: 'performanceProfile.title',
        Icon: GaugeIcon,
        keywords: [
          'performanceProfile.fast',
          'performanceProfile.quality',
          'settings.perf_torch_compile',
          'settings.generate_budget_title',
        ],
        terms: ['torch.compile', 'Triton', 'timeout'],
      },
      {
        id: 'media',
        to: '/settings/media',
        label: 'settings.audio_tools',
        Icon: WrenchIcon,
        keywords: ['settings.ffmpeg'],
        terms: ['ffmpeg', 'ffprobe', 'yt-dlp', 'YouTube'],
      },
    ],
  },
  {
    id: 'device',
    label: 'settingsNav.group_device',
    items: [
      {
        id: 'performance',
        to: '/settings/performance',
        label: 'settingsNav.device',
        Icon: CpuIcon,
        keywords: [
          'settings.compute_device_title',
          'header.memory_management',
          'engineSidebar.localDevice',
        ],
        terms: ['GPU', 'CUDA', 'MPS', 'ROCm', 'CPU', 'VRAM', 'RAM'],
      },
      {
        id: 'usage',
        to: '/settings/usage',
        label: 'settings.usage',
        Icon: BarChart3Icon,
        keywords: ['settings.usage_takes', 'settings.usage_audio', 'settings.usage_by_language'],
      },
    ],
  },
  {
    id: 'data',
    label: 'settingsNav.group_data',
    items: [
      {
        id: 'privacy',
        to: '/settings/privacy',
        aliases: { '/settings/permissions': 'settings-permissions' },
        label: 'settings.privacy',
        Icon: ShieldCheckIcon,
        keywords: [
          'privacy.analytics_title',
          'privacy.watermark_title',
          'permissions.title',
          'permissions.microphone',
          'permissions.accessibility',
        ],
      },
      {
        id: 'storage',
        to: '/settings/storage',
        label: 'settings.storage',
        Icon: HardDriveIcon,
        keywords: [
          'settings.data_directory',
          'settings.storage_usage',
          'settings.history_retention',
          'updates.backup_line',
        ],
        terms: ['backup', 'reset', 'uninstall', 'cache'],
      },
    ],
  },
  {
    id: 'connections',
    label: 'settingsNav.group_connections',
    items: [
      {
        id: 'network',
        to: '/settings/network',
        label: 'settings.network',
        Icon: WifiIcon,
        keywords: ['settings.proxy'],
        terms: ['proxy', 'mirror', 'hf-mirror', 'Hugging Face'],
      },
      {
        id: 'credentials',
        to: '/settings/credentials',
        label: 'settings.credentials',
        Icon: KeyRoundIcon,
        keywords: ['settings.hf_token_input', 'settings.translation_providers'],
        terms: ['token', 'API key', 'DeepL', 'Hugging Face'],
      },
      {
        id: 'sharing',
        to: '/settings/sharing',
        aliases: { '/settings/workers': 'settings-workers' },
        label: 'sharing.title',
        Icon: Share2Icon,
        keywords: [
          'sharing.local_network',
          'sharing.tailscale_title',
          'settings.remote_backend_title',
          'settings.workers_title',
        ],
        terms: ['LAN', 'Tailscale', 'MCP', 'worker', 'port'],
      },
    ],
  },
  {
    id: 'developer',
    label: 'settingsNav.group_developer',
    foldable: true,
    items: [
      {
        id: 'diagnostics',
        to: '/settings/diagnostics',
        label: 'settingsNav.diagnostics',
        Icon: StethoscopeIcon,
        keywords: ['about.title', 'about.diagnostics', 'about.self_check', 'about.save_bundle'],
        terms: ['preflight', 'bug'],
      },
      {
        id: 'logs',
        to: '/settings/logs',
        label: 'settings.logs',
        Icon: FileTextIcon,
        keywords: [],
        terms: ['log'],
      },
      {
        id: 'openapi',
        to: '/settings/openapi',
        label: 'openapi.title',
        Icon: BracesIcon,
        keywords: ['openapi.copy_url'],
        terms: ['API', 'OpenAPI', 'REST'],
      },
    ],
  },
];

const ITEMS = NAV.flatMap((group) => group.items.map((item) => ({ ...item, group: group.id })));

function resolvePage(pathname: string) {
  const family = modelFamilies.find((value) => pathname === '/settings/models/' + value);
  for (const item of ITEMS) {
    if (pathname === item.to) return { item, family: undefined, anchor: undefined };
    if (item.id === 'models' && family) return { item, family, anchor: undefined };
    const anchor = item.aliases?.[pathname];
    if (anchor) return { item, family: undefined, anchor };
  }
  return {
    item: ITEMS.find((item) => item.id === 'appearance')!,
    family: undefined,
    anchor: undefined,
  };
}

const navRow =
  'group flex h-8 min-w-0 items-center gap-2 rounded-lg px-2 text-sm text-sidebar-foreground/75 outline-none transition-colors duration-150 hover:bg-[var(--sidebar-row-hover)] hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-ring/40 aria-[current=page]:bg-[var(--sidebar-row-active)] aria-[current=page]:font-medium aria-[current=page]:text-sidebar-foreground motion-reduce:transition-none';
const navIcon =
  'size-4 shrink-0 text-muted-foreground transition-colors duration-150 group-hover:text-sidebar-foreground group-aria-[current=page]:text-primary';

export function SettingsPage() {
  const { t } = useTranslation();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const { item: page, family, anchor } = resolvePage(pathname);
  const [query, setQuery] = useState('');
  const [developerOpen, setDeveloperOpen] = useState(false);
  useEffect(() => rememberSettingsRoute(pathname), [pathname]);
  // An old path (Remote workers, Permissions) opens the page it moved into and
  // brings its section into view.
  useEffect(() => {
    if (!anchor) return;
    const frame = requestAnimationFrame(() =>
      document.getElementById(anchor)?.scrollIntoView({ block: 'start' }),
    );
    return () => cancelAnimationFrame(frame);
  }, [anchor]);

  const needle = query.trim().toLocaleLowerCase();
  const matches = useMemo(() => {
    if (!needle) return null;
    const hit = (text: string) => text.toLocaleLowerCase().includes(needle);
    return new Set(
      ITEMS.filter(
        (item) =>
          hit(t(item.label)) || item.keywords.some((key) => hit(t(key))) || item.terms?.some(hit),
      ).map((item) => item.id),
    );
  }, [needle, t]);

  const pageTitle = family ? t('engineSidebar.' + family) : t(page.label);
  const fullBleed = page.id === 'openapi' || page.id === 'logs';

  return (
    <div className="flex h-full min-h-0">
      <EdgePane side="left">
        <aside className="flex h-full min-h-0 w-[clamp(13.5rem,19vw,16.5rem)] shrink-0 flex-col border-r border-sidebar-border/50 bg-sidebar text-sidebar-foreground">
          <header className="workspace-titlebar flex h-12 shrink-0 items-center gap-2.5 border-b border-sidebar-border/45 px-3.5">
            {/* The brand and window controls live in the main sidebar to the
              left; this column is the Settings section list. */}
            <SettingsIcon aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
            <span className="truncate text-sm font-semibold tracking-[-0.014em]">
              {t('nav.settings')}
            </span>
          </header>
          <div className="studio-scrollbar flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain px-3 pt-3 pb-2 [scrollbar-gutter:stable]">
            <div className="sticky top-0 z-10 -mx-1 bg-sidebar px-1 pb-2">
              <div className="flex h-8 items-center gap-2 rounded-lg border border-sidebar-border/60 bg-background/40 px-2.5 transition-[border-color,box-shadow] focus-within:border-primary/40 focus-within:ring-2 focus-within:ring-ring/20">
                <SearchIcon aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
                <Input
                  type="search"
                  aria-label={t('preferences.search')}
                  placeholder={t('preferences.search')}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') setQuery('');
                  }}
                  className="h-auto min-w-0 border-0 bg-transparent p-0 text-sm shadow-none focus-visible:ring-0 dark:bg-transparent"
                />
              </div>
            </div>
            <nav aria-label={t('nav.settings')} className="flex flex-col">
              {NAV.map((group) => {
                const items = matches
                  ? group.items.filter((item) => matches.has(item.id))
                  : group.items;
                if (items.length === 0) return null;
                const holdsPage = group.items.some((item) => item.id === page.id);
                const open = !group.foldable || Boolean(matches) || holdsPage || developerOpen;
                const headingId = 'settings-group-' + group.id;
                return (
                  <section key={group.id} aria-labelledby={headingId} className="pb-2">
                    {group.foldable && !matches && !holdsPage ? (
                      <button
                        type="button"
                        id={headingId}
                        aria-expanded={open}
                        onClick={() => setDeveloperOpen((value) => !value)}
                        className="flex h-7 w-full items-center gap-1 rounded-md px-2 text-[11px] font-medium tracking-[0.02em] text-muted-foreground outline-none hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-ring/40"
                      >
                        {t(group.label)}
                        <ChevronRightIcon
                          aria-hidden="true"
                          className={cn(
                            'size-3.5 transition-transform duration-150 motion-reduce:transition-none',
                            open && 'rotate-90',
                          )}
                        />
                      </button>
                    ) : (
                      <h2
                        id={headingId}
                        className="flex h-7 items-center px-2 text-[11px] font-medium tracking-[0.02em] text-muted-foreground"
                      >
                        {t(group.label)}
                      </h2>
                    )}
                    {open && (
                      <div className="flex flex-col gap-px">
                        {items.map((item) => (
                          <NavEntry
                            key={item.id}
                            item={item}
                            current={item.id === page.id && !family}
                            expanded={
                              item.id === 'models' && (page.id === 'models' || Boolean(matches))
                            }
                            family={family}
                          />
                        ))}
                      </div>
                    )}
                  </section>
                );
              })}
            </nav>
            {matches?.size === 0 && (
              <p role="status" className="px-2 py-6 text-center text-xs text-muted-foreground">
                {t('preferences.no_matches')}
              </p>
            )}
          </div>
          <div className="shrink-0 border-t border-sidebar-border/50 p-3">
            <Link to={readLastWorkspaceRoute()} title={t('preferences.back')} className={navRow}>
              <ArrowLeftIcon aria-hidden="true" className={navIcon} />
              <span data-slot="settings-nav-label" className="min-w-0 flex-1 truncate text-left">
                {t('preferences.back')}
              </span>
            </Link>
          </div>
        </aside>
      </EdgePane>
      <section className="flex min-w-0 flex-1 flex-col bg-background">
        <WorkspaceHeader>
          <h1>{t('nav.settings')}</h1>
          <span className="truncate text-sm text-muted-foreground">{pageTitle}</span>
        </WorkspaceHeader>
        <SettingsContent fullBleed={fullBleed} title={pageTitle} key={family ?? page.id}>
          <PageBody id={page.id} family={family} />
        </SettingsContent>
      </section>
    </div>
  );
}

function NavEntry({
  item,
  current,
  expanded,
  family,
}: {
  item: NavItem;
  current: boolean;
  expanded: boolean;
  family?: ModelFamily;
}) {
  const { t } = useTranslation();
  const { Icon } = item;
  return (
    <>
      <Link
        to={item.to}
        title={t(item.label)}
        aria-current={current ? 'page' : undefined}
        className={navRow}
      >
        <Icon aria-hidden="true" className={navIcon} />
        <span data-slot="settings-nav-label" className="min-w-0 flex-1 truncate text-left">
          {t(item.label)}
        </span>
      </Link>
      {expanded &&
        modelFamilies.map((value) => {
          const FamilyIcon = familyIcons[value];
          return (
            <Link
              key={value}
              to="/settings/models/$family"
              params={{ family: value }}
              title={t('engineSidebar.' + value)}
              aria-current={family === value ? 'page' : undefined}
              className={cn(navRow, 'h-7 pl-8 text-[13px]')}
            >
              <FamilyIcon aria-hidden="true" className={cn(navIcon, 'size-3.5')} />
              <span data-slot="settings-nav-label" className="min-w-0 flex-1 truncate text-left">
                {t('engineSidebar.' + value)}
              </span>
            </Link>
          );
        })}
    </>
  );
}

function PageBody({ id, family }: { id: PageId; family?: ModelFamily }) {
  switch (id) {
    case 'general':
      return <GeneralSettings />;
    case 'appearance':
      return <AppearanceSettings />;
    case 'pronunciation':
      return <PronunciationSettings />;
    case 'updates':
      return <UpdateSettings />;
    case 'models':
      return <ModelSettings key={family ?? 'all'} family={family} />;
    case 'speed':
      return <SpeedQualitySettings />;
    case 'media':
      return <MediaTools />;
    case 'performance':
      return <PerformanceSettings />;
    case 'usage':
      return <UsageSettings />;
    case 'privacy':
      return (
        <>
          <PrivacySettings />
          <div id="settings-permissions" className="flex scroll-mt-6 flex-col gap-8">
            <PermissionsSettings />
          </div>
        </>
      );
    case 'storage':
      return <StorageSettings />;
    case 'network':
      return (
        <>
          <NetworkSettings />
          <MirrorSettings />
        </>
      );
    case 'credentials':
      return <CredentialSettings />;
    case 'sharing':
      return (
        <>
          <SharingSettings />
          <div id="settings-workers" className="flex scroll-mt-6 flex-col gap-8">
            <WorkersSettings />
          </div>
        </>
      );
    case 'diagnostics':
      return <DiagnosticsSettings />;
    case 'logs':
      return <LogSettings />;
    case 'openapi':
      return <OpenApiSettings />;
  }
}

/** Mutually exclusive choices as one compact segmented control. */
function Choice<T extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: ReactNode; icon?: ReactNode }[];
  onChange: (value: T) => void;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="inline-flex max-w-full flex-wrap rounded-lg border border-border bg-muted/40 p-0.5"
    >
      {options.map((option) => (
        <button
          key={String(option.value)}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className="inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium text-muted-foreground outline-none transition-colors duration-150 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/40 aria-pressed:bg-background aria-pressed:text-foreground aria-pressed:shadow-xs motion-reduce:transition-none [&_svg]:size-3.5"
        >
          {option.icon}
          {option.label}
        </button>
      ))}
    </div>
  );
}

function GeneralSettings() {
  const { t } = useTranslation();
  const reviewMode = useReviewMode();
  return (
    <SettingsSection icon={Settings2Icon} title={t('preferences.general')}>
      <SettingsRow
        id="language-label"
        title={t('settings.language')}
        description={t('settings.language_desc')}
      >
        <Select
          items={APP_LANGUAGE_ITEMS}
          value={i18n.resolvedLanguage || i18n.language}
          onValueChange={(value) => void setAppLanguage(value as AppLocale)}
        >
          <SelectTrigger aria-labelledby="language-label" className="min-w-44">
            <LanguagesIcon className="size-4 text-muted-foreground" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent align="end">
            {APP_LANGUAGES.map(({ code, label }) => (
              <SelectItem key={code} value={code}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </SettingsRow>
      <SettingsRow
        id="review-mode-label"
        title={t('settings.review_mode')}
        description={t('settings.review_mode_desc')}
      >
        <Choice
          label={t('settings.review_mode')}
          value={reviewMode}
          onChange={setReviewMode}
          options={(['on', 'off'] as const).map((value) => ({
            value,
            label: t(`settings.review_mode_${value}`),
            icon: value === 'on' ? <ClipboardCheckIcon aria-hidden="true" /> : undefined,
          }))}
        />
      </SettingsRow>
    </SettingsSection>
  );
}

function AppearanceSettings() {
  const { t } = useTranslation();
  const { mode, setTheme, updateTheme } = useTheme();
  const appearance = useAppearance();
  return (
    <>
      <SettingsSection icon={PaletteIcon} title={t('preferences.appearance')}>
        <SettingsRow id="theme-label" title={t('preferences.theme')}>
          <Choice
            label={t('preferences.theme')}
            value={mode}
            onChange={setTheme}
            options={[
              {
                value: 'light',
                label: t('themeAppearance.light'),
                icon: <SunIcon aria-hidden="true" />,
              },
              {
                value: 'dark',
                label: t('themeAppearance.dark'),
                icon: <MoonIcon aria-hidden="true" />,
              },
              {
                value: 'system',
                label: t('themeAppearance.system'),
                icon: <MonitorIcon aria-hidden="true" />,
              },
            ]}
          />
        </SettingsRow>
        <SettingsRow id="glass-label" title={t('themeAppearance.glass')}>
          <Switch
            aria-labelledby="glass-label"
            checked={appearance.glass}
            onCheckedChange={(glass) => appearance.update({ glass })}
          />
        </SettingsRow>
        <SettingsRow id="font-label" title={t('preferences.font')}>
          {/* `inter` is the stored id of the bundled interface face, Onest. */}
          <Choice
            label={t('preferences.font')}
            value={appearance.font}
            onChange={(font) => appearance.update({ font })}
            options={[
              {
                value: 'inter' as const,
                label: <span style={{ fontFamily: 'Onest, sans-serif' }}>Onest</span>,
              },
              {
                value: 'system' as const,
                label: (
                  <span style={{ fontFamily: 'system-ui' }}>{t('themeAppearance.system')}</span>
                ),
              },
            ]}
          />
        </SettingsRow>
        <SettingsRow id="scale-label" title={t('preferences.ui_scale')}>
          <Choice
            label={t('preferences.ui_scale')}
            value={appearance.scale}
            onChange={(scale) => appearance.update({ scale })}
            options={appearanceScales.map((scale) => ({ value: scale, label: `${scale}%` }))}
          />
        </SettingsRow>
        <PalettePicker appearance="light" />
        <PalettePicker appearance="dark" />
      </SettingsSection>
      <div className="flex justify-end">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            appearance.update({ font: 'inter', scale: 100, glass: true });
            updateTheme({ mode: 'system', light: 'default', dark: 'default' });
          }}
        >
          <RotateCcwIcon />
          {t('preferences.reset')}
        </Button>
      </div>
    </>
  );
}
