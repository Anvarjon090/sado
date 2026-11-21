import { LoadingOrb } from '@/components/motion-fx';
import { CheckCircle2Icon, CopyIcon, ExternalLinkIcon, RefreshCwIcon } from 'lucide-react';
import { lazy, Suspense, useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { getBridge } from '@/components/bridge';
import { useBackendStatus } from '@/hooks/use-backend-status';
import { isBackendReachable } from '@shared/utils/backendStage';
import { apiJson, apiPath, describeError } from '@/lib/api/client';
import { SettingsActionError } from './settings-action-error';

const ScalarApiReference = lazy(() => import('./scalar-api-reference'));

/**
 * How long the spec may stay pending before the page gives up waiting. A
 * pending query covers both a request that never answers (no fetch timeout)
 * and one paused because the backend is not reachable yet; either way the user
 * gets the error state instead of an endless spinner. A late answer still
 * replaces the error with the reference.
 */
const SPEC_DEADLINE_MS = 15_000;

function LoadingReference() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-72 items-center justify-center gap-2 text-sm text-muted-foreground">
      <LoadingOrb className="size-4" />
      {t('common.loading')}
    </div>
  );
}

export function OpenApiSettings() {
  const { t } = useTranslation();
  const backend = useBackendStatus();
  const baseUrl = backend.baseUrl.replace(/\/+$/, '');
  const displayedBaseUrl = baseUrl || window.location.origin;
  const rawUrl = `${displayedBaseUrl}/openapi.json`;
  const queryClient = useQueryClient();
  const specKey = ['openapi-spec', rawUrl];
  const spec = useQuery({
    queryKey: specKey,
    queryFn: async ({ signal }) => {
      const data = await apiJson<Record<string, unknown>>('/openapi.json', { signal });
      return {
        ...data,
        servers: [{ url: `${window.location.origin}${apiPath('')}` }],
      };
    },
    staleTime: 60_000,
  });
  // Keyed by URL so switching backends starts a fresh deadline.
  const [timedOutFor, setTimedOutFor] = useState<string | null>(null);
  const timedOut = spec.isPending && timedOutFor === rawUrl;
  useEffect(() => {
    if (!spec.isPending || timedOutFor === rawUrl) return;
    const timer = window.setTimeout(() => setTimedOutFor(rawUrl), SPEC_DEADLINE_MS);
    return () => window.clearTimeout(timer);
  }, [spec.isPending, timedOutFor, rawUrl]);

  const retry = async () => {
    setTimedOutFor(null);
    // refetch() joins a request that is still in flight when there is no data
    // yet, so a hung request must be cancelled first or Retry does nothing.
    await queryClient.cancelQueries({ queryKey: specKey });
    void spec.refetch();
  };

  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(rawUrl);
      toast.success(t('openapi.copied'));
    } catch {
      toast.error(t('openapi.copy_failed'));
    }
  };

  const openRaw = () => {
    const bridge = getBridge();
    if (bridge)
      void bridge.files.openExternal(rawUrl).catch((error) => toast.error(describeError(error)));
    else window.open(rawUrl, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <div className="flex min-h-12 shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-border/50 bg-muted/15 px-4 py-2">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <CheckCircle2Icon
            aria-hidden="true"
            className={
              isBackendReachable(backend.stage)
                ? 'size-4 shrink-0 text-emerald-500'
                : 'size-4 shrink-0 text-muted-foreground'
            }
          />
          <span className="shrink-0 text-xs font-medium">{t(`backend.${backend.stage}`)}</span>
          <code
            title={rawUrl}
            className="min-w-0 truncate rounded-md border border-border/50 bg-background/50 px-2 py-1 font-mono text-[11px] text-muted-foreground"
          >
            {displayedBaseUrl}
          </code>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            variant="ghost"
            size="sm"
            aria-label={t('common.refresh')}
            title={t('common.refresh')}
            disabled={spec.isFetching && !timedOut}
            onClick={() => void retry()}
          >
            <RefreshCwIcon className={spec.isFetching && !timedOut ? 'animate-spin' : undefined} />
            <span className="hidden @2xl:inline">{t('common.refresh')}</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            aria-label={t('openapi.copy_url')}
            title={t('openapi.copy_url')}
            onClick={() => void copyUrl()}
          >
            <CopyIcon />
            <span className="hidden @2xl:inline">{t('openapi.copy_url')}</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            aria-label={t('openapi.open_raw')}
            title={t('openapi.open_raw')}
            onClick={openRaw}
          >
            <ExternalLinkIcon />
            <span className="hidden @2xl:inline">{t('openapi.open_raw')}</span>
          </Button>
        </div>
      </div>
      {spec.isPending && !timedOut ? (
        <main className="min-h-0 flex-1">
          <LoadingReference />
        </main>
      ) : spec.isPending || spec.isError ? (
        <main className="min-h-0 flex-1 p-4">
          <SettingsActionError
            title={t('openapi.unreachable_title')}
            detail={[
              t('openapi.unreachable_body', { url: rawUrl }),
              spec.isError ? describeError(spec.error) : '',
            ]
              .filter(Boolean)
              .join(' ')}
            action={
              <>
                <Button variant="ghost" size="xs" onClick={openRaw}>
                  <ExternalLinkIcon />
                  {t('openapi.open_raw')}
                </Button>
                <Button variant="ghost" size="xs" onClick={() => void retry()}>
                  <RefreshCwIcon />
                  {t('common.retry')}
                </Button>
              </>
            }
          />
        </main>
      ) : (
        <div className="isolate min-h-0 min-w-0 flex-1 overflow-auto bg-background [&_.scalar-app]:min-h-full">
          <Suspense fallback={<LoadingReference />}>
            <ScalarApiReference spec={spec.data} />
          </Suspense>
        </div>
      )}
    </div>
  );
}
