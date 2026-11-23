import { LoadingOrb } from '@/components/motion-fx';
import { BrandMark } from '@/components/brand-mark';
import { Link } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ActivityIcon,
  AlertTriangleIcon,
  AudioLinesIcon,
  CheckCircle2Icon,
  CopyIcon,
  CpuIcon,
  DownloadIcon,
  ExternalLinkIcon,
  FolderOpenIcon,
  InfoIcon,
  LanguagesIcon,
  Mic2Icon,
  MonitorUpIcon,
  XCircleIcon,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { getBridge } from '@/components/bridge';
import { apiJson, describeError } from '@/lib/api/client';
import type { SystemInfo } from '@/lib/api/types';
import { SettingsActionError } from './settings-action-error';
import { SettingsSection } from './settings-layout';
import { SystemPreflight } from './system-preflight';
import { ReportBug } from '@/components/report-bug';

type CheckStatus = 'ok' | 'warn' | 'fail';

interface DiagnosticCheck {
  id: string;
  label: string;
  status: CheckStatus;
  detail: string;
  hint?: string | null;
}

interface DiagnosticReport {
  app_version: string;
  platform: string;
  checks: DiagnosticCheck[];
  summary: {
    ok: boolean;
    passed: number;
    warnings: number;
    failures: number;
  };
}

interface DiagnosticBundle {
  path: string;
  filename: string;
}

const FIX_ROUTES: Record<string, string> = {
  ffmpeg: '/settings/media',
  hf_token: '/settings/credentials',
  disk: '/settings/storage',
  data_dir: '/settings/storage',
  engines: '/settings/models',
  gpu_routing: '/settings/performance',
  device: '/settings/performance',
  ram: '/settings/performance',
  deep_synth: '/settings/logs',
};

function reportText(report: DiagnosticReport) {
  const marker: Record<CheckStatus, string> = { ok: '[ OK ]', warn: '[WARN]', fail: '[FAIL]' };
  const lines = [
    `Sado diagnostics - v${report.app_version} on ${report.platform}`,
    '',
    ...report.checks.flatMap((check) => [
      `${marker[check.status]} ${check.label}: ${check.detail}`,
      ...(check.hint ? [`       hint: ${check.hint}`] : []),
    ]),
    '',
    `${report.summary.passed} ok, ${report.summary.warnings} warning(s), ${report.summary.failures} failure(s)`,
  ];
  return lines.join('\n');
}

export function DiagnosticsSettings() {
  const { t } = useTranslation();
  const bridge = getBridge();
  const [report, setReport] = useState<DiagnosticReport | null>(null);
  const [action, setAction] = useState<'check' | 'bundle' | 'copy' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const info = useQuery({
    queryKey: ['system-info'],
    queryFn: ({ signal }) => apiJson<SystemInfo>('/system/info', { signal }),
  });

  const system = info.data;
  const platform = system
    ? [system.os_version || system.platform, system.arch].filter(Boolean).join(' · ')
    : bridge?.app.platform || navigator.platform;
  const cpu = system
    ? [system.cpu_model, system.cpu_count ? `${system.cpu_count}T` : ''].filter(Boolean).join(' · ')
    : '';
  const gpu = system
    ? [system.gpu_name, system.vram_total_gb ? `${system.vram_total_gb.toFixed(1)} GB` : '']
        .filter(Boolean)
        .join(' · ')
    : '';

  const runCheck = async (): Promise<DiagnosticReport | null> => {
    setAction('check');
    setError(null);
    try {
      const next = await apiJson<DiagnosticReport>('/system/diagnose?network=true');
      setReport(next);
      return next;
    } catch (cause) {
      setError(describeError(cause));
      return null;
    } finally {
      setAction(null);
    }
  };

  const copy = async () => {
    setAction('copy');
    setError(null);
    try {
      const current = report ?? (await apiJson<DiagnosticReport>('/system/diagnose?network=true'));
      setReport(current);
      await navigator.clipboard.writeText(reportText(current));
      toast.success(t('about.copy_diagnostics'));
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setAction(null);
    }
  };

  const buildBundle = async () => {
    setAction('bundle');
    setError(null);
    try {
      const bundle = await apiJson<DiagnosticBundle>('/system/diagnostic-bundle?network=false', {
        method: 'POST',
      });
      toast.success(t('about.bundle_saved', { filename: bundle.filename }));
      await getBridge()?.files.revealPath(bundle.path);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setAction(null);
    }
  };

  const loading = t('common.loading');
  const aboutItems: {
    id: string;
    label: string;
    Icon?: typeof InfoIcon;
    value: ReactNode;
    mono?: boolean;
  }[] = [
    {
      id: 'diagnostics-app',
      label: t('about.app'),
      value: (
        <span className="inline-flex items-center gap-2 font-medium" translate="no">
          <BrandMark size={18} />
          Sado{' '}
          <span className="font-mono text-[13px] font-normal text-muted-foreground">
            {bridge?.app.version ?? __APP_VERSION__}
          </span>
        </span>
      ),
    },
    { id: 'diagnostics-platform', label: t('about.platform'), value: platform, mono: true },
    {
      id: 'diagnostics-device',
      label: t('about.compute_device'),
      Icon: CpuIcon,
      value: system ? (
        <span className="space-y-0.5">
          <span className="block font-medium uppercase">{system.device}</span>
          {cpu && <span className="block text-[13px] text-muted-foreground">{cpu}</span>}
        </span>
      ) : (
        loading
      ),
    },
    ...(gpu
      ? [
          {
            id: 'diagnostics-gpu',
            label: t('about.gpu_active'),
            Icon: MonitorUpIcon,
            value: (
              <span className="space-y-0.5">
                <span className="block font-medium">
                  {t(system?.device && system.device !== 'cpu' ? 'about.yes' : 'about.no')}
                </span>
                <span className="block text-[13px] text-muted-foreground">{gpu}</span>
              </span>
            ),
          },
        ]
      : []),
    {
      id: 'diagnostics-memory',
      label: t('about.ram'),
      value: system?.ram_total_gb ? `${system.ram_total_gb.toFixed(1)} GB` : loading,
    },
    {
      id: 'diagnostics-python',
      label: t('about.python'),
      value: system?.python || loading,
      mono: true,
    },
    {
      id: 'diagnostics-tts',
      label: t('engineSidebar.tts'),
      Icon: AudioLinesIcon,
      value: system?.model_checkpoint || loading,
      mono: true,
    },
    {
      id: 'diagnostics-asr',
      label: t('engineSidebar.asr'),
      Icon: Mic2Icon,
      value: system?.asr_model || loading,
      mono: true,
    },
    {
      id: 'diagnostics-translator',
      label: t('about.translator'),
      Icon: LanguagesIcon,
      value: system?.translate_provider || loading,
    },
    {
      id: 'diagnostics-data-directory',
      label: t('settings.data_directory'),
      Icon: FolderOpenIcon,
      value: system?.data_dir || loading,
      mono: true,
    },
    {
      id: 'diagnostics-outputs',
      label: t('settings.storage_child_outputs'),
      value: system?.outputs_dir || loading,
      mono: true,
    },
  ];

  return (
    <>
      <SettingsSection icon={ActivityIcon} title={t('settingsNav.diagnostics')}>
        <div className="flex flex-wrap items-center gap-2 p-4">
          <Button size="sm" disabled={action !== null} onClick={() => void runCheck()}>
            {action === 'check' ? <LoadingOrb /> : <ActivityIcon />}
            {t('about.self_check')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={action !== null}
            onClick={() => void buildBundle()}
          >
            {action === 'bundle' ? <LoadingOrb /> : <DownloadIcon />}
            {t('about.save_bundle')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={action !== null}
            onClick={() => void copy()}
          >
            {action === 'copy' ? <LoadingOrb /> : <CopyIcon />}
            {t('about.copy_diagnostics')}
          </Button>
          <ReportBug />
        </div>

        {error && (
          <div className="p-4">
            <SettingsActionError
              title={t('about.self_check_failed', { message: '' }).trim()}
              detail={error}
              onDismiss={() => setError(null)}
            />
          </div>
        )}

        {report && (
          <div>
            <div className="flex flex-wrap items-center gap-3 px-4 py-3">
              {report.summary.ok ? (
                <CheckCircle2Icon className="size-5 text-success" aria-hidden="true" />
              ) : (
                <AlertTriangleIcon className="size-5 text-warning" aria-hidden="true" />
              )}
              <p className="text-sm font-medium">
                {t(report.summary.ok ? 'about.self_check_healthy' : 'about.self_check_attention', {
                  count: report.summary.failures,
                })}
              </p>
              <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                {report.summary.passed} / {report.checks.length}
              </span>
            </div>
            <ul className="divide-y divide-border/50">
              {report.checks.map((check) => {
                const Icon =
                  check.status === 'ok'
                    ? CheckCircle2Icon
                    : check.status === 'warn'
                      ? AlertTriangleIcon
                      : XCircleIcon;
                const fix = FIX_ROUTES[check.id];
                return (
                  <li key={check.id} className="flex min-w-0 items-start gap-3 px-4 py-3">
                    <Icon
                      aria-hidden="true"
                      className={
                        'mt-0.5 size-4 shrink-0 ' +
                        (check.status === 'ok'
                          ? 'text-success'
                          : check.status === 'warn'
                            ? 'text-warning'
                            : 'text-destructive')
                      }
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-medium">{check.label}</h3>
                        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                          {t(`about.self_check_${check.status}`)}
                        </span>
                      </div>
                      <p className="mt-1 break-words text-xs leading-5 text-muted-foreground">
                        {check.detail}
                      </p>
                      {check.hint && (
                        <p className="mt-1 break-words text-xs leading-5">{check.hint}</p>
                      )}
                    </div>
                    {check.status !== 'ok' && fix && (
                      <Button
                        render={<Link to={fix} />}
                        nativeButton={false}
                        size="xs"
                        variant="ghost"
                        className="shrink-0"
                      >
                        {t('common.open')}
                        <ExternalLinkIcon />
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </SettingsSection>

      <SystemPreflight />

      <SettingsSection icon={InfoIcon} title={t('about.title')}>
        {/* Facts read top to bottom: each value sits beside its label, not
            across the window. Monospace only for versions, ids and paths. */}
        <dl className="grid grid-cols-1 gap-x-6 px-4 py-2 @lg:grid-cols-[minmax(8.5rem,12rem)_minmax(0,1fr)]">
          {aboutItems.map(({ id, label, Icon, value, mono }) => (
            <div key={id} id={id} className="contents">
              <dt className="flex items-center gap-2 pt-3 text-[13px] text-muted-foreground @lg:py-2.5">
                {Icon && <Icon aria-hidden="true" className="size-4 shrink-0" />}
                {label}
              </dt>
              <dd
                className={
                  'min-w-0 pb-3 text-sm text-foreground [overflow-wrap:anywhere] @lg:py-2.5 ' +
                  (mono ? 'font-mono text-[13px]' : '')
                }
              >
                {value}
              </dd>
            </div>
          ))}
        </dl>
      </SettingsSection>
    </>
  );
}
