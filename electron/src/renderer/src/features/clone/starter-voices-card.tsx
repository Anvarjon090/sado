import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { DownloadIcon, SparklesIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { apiJson, describeError } from '@/lib/api/client';
import { queryKeys } from '@/lib/query';
import { setStarterVoicesOffer, useStarterVoicesOffer } from '@/lib/store/starter-voices';

/** The pack id in the Sado gallery manifest (`backend/api/routers/community.py`). */
export const STARTER_PACK_ID = 'sado-starter';
/** Shown on the static card; the real list comes from the manifest after the click. */
export const STARTER_VOICE_COUNT = 6;
export const STARTER_PACK_MB = 3;

interface InstallResult {
  installed: { item_id: string; profile_id: string; name: string }[];
  failed: { item_id: string; detail: string }[];
}

/**
 * The one place a fresh install meets Sado's ready-made voices. The card is
 * plain text until the user clicks Download: that click is the consent the
 * local-first rule asks for, and only then does the backend fetch the
 * gallery manifest and the six clips.
 */
export function StarterVoicesCard() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const offer = useStarterVoicesOffer();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (offer !== 'pending') return null;

  const install = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await apiJson<InstallResult>(
        '/community/packs/' + STARTER_PACK_ID + '/install',
        { method: 'POST' },
      );
      await queryClient.invalidateQueries({ queryKey: queryKeys.profiles });
      if (result.installed.length === 0) {
        setError(
          t('clone.starter_failed', {
            message: result.failed[0]?.detail ?? '',
          }),
        );
        return;
      }
      setStarterVoicesOffer('installed');
    } catch (cause) {
      setError(t('clone.starter_failed', { message: describeError(cause) }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      aria-labelledby="starter-voices-title"
      className="mt-6 w-full max-w-md rounded-2xl border border-border/60 bg-card p-4 text-left"
    >
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <SparklesIcon className="size-4" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <h2 id="starter-voices-title" className="text-sm font-medium">
            {t('clone.starter_title')}
          </h2>
          <p className="mt-1 text-[length:var(--text-label)] leading-relaxed text-muted-foreground">
            {t('clone.starter_body', {
              count: STARTER_VOICE_COUNT,
              size: STARTER_PACK_MB,
            })}
          </p>
          {error && (
            <p role="alert" className="mt-2 text-[length:var(--text-label)] text-destructive">
              {error}
            </p>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" disabled={busy} onClick={() => void install()}>
              <DownloadIcon aria-hidden="true" />
              {busy
                ? t('clone.starter_installing')
                : t('clone.starter_install', { size: STARTER_PACK_MB })}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => setStarterVoicesOffer('dismissed')}
            >
              {t('clone.starter_later')}
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
