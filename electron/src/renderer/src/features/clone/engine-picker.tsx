import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { AlertCircleIcon, CpuIcon } from 'lucide-react';
import { toast } from 'sonner';
// Shared JSX controls are also consumed by the maintained shared UI modules.
// @ts-expect-error Shared JSX has no declaration file.
import SearchableSelect from '@shared/components/SearchableSelect';
import type { SearchOption } from '@shared/components/VirtualSearchableSelect';
import { apiJson, describeError } from '@/lib/api/client';
import {
  engineSelectionFeedback,
  type EngineSelectionResult,
} from '@/lib/engine-selection-feedback';
import { useEngines } from '@/hooks/use-engines';
import { queryKeys } from '@/lib/query';

/**
 * "Navoiy-TTS (Uzbek, 10 emotions)" → "Navoiy-TTS": a chip has no room for the
 * parenthetical. An entry without a display name (an older backend, a remote
 * worker) shows its id instead of taking the whole voice studio down.
 */
export function engineShortName(displayName: string | null | undefined, id = ''): string {
  return (displayName || id).replace(/\s*\(.*\)$/, '');
}

interface EngineOption extends SearchOption {
  value: string;
  label: string;
  disabled: boolean;
  reason: string | null;
}

/**
 * The TTS engine switch of the composer: the same `/engines/select` call as
 * Settings → Models, so saved projects, the sidebar and the language picker
 * all follow the choice. Engines that cannot run stay listed, greyed, with
 * the backend's own reason, and the footer leads to the full catalogue.
 */
export function EnginePicker({
  className,
  disabled = false,
}: {
  className?: string;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const { data, activeTts, isLoading } = useEngines();
  const [pending, setPending] = useState<string | null>(null);
  const backends = data?.tts?.backends ?? [];
  const options: EngineOption[] = backends.map((backend) => {
    const label = engineShortName(backend.display_name, backend.id);
    return {
      value: backend.id,
      label,
      search: [label.toLowerCase(), backend.id],
      disabled: !backend.available,
      reason: backend.reason ?? backend.hint ?? null,
    };
  });
  const active = activeTts?.id ?? data?.tts?.active ?? '';
  const current = options.find((option) => option.value === active);

  const switchTo = async (id: string) => {
    const target = options.find((option) => option.value === id);
    if (!target || target.disabled || id === active || pending) return;
    setPending(id);
    try {
      const result = await apiJson<EngineSelectionResult>('/engines/select', {
        method: 'POST',
        body: JSON.stringify({ family: 'tts', backend_id: id }),
      });
      await Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.engines }),
        client.invalidateQueries({ queryKey: ['performance-profile'] }),
      ]);
      const feedback = engineSelectionFeedback(result, 'tts');
      if (feedback.tone === 'warning') toast.warning(t(feedback.key, feedback.values));
      else toast.success(t(feedback.key, feedback.values));
    } catch (error) {
      toast.error(describeError(error));
    } finally {
      setPending(null);
    }
  };

  return (
    <SearchableSelect
      virtualized
      menuPortal
      value={active}
      options={options}
      disabled={disabled || isLoading || pending !== null || options.length === 0}
      ariaLabel={t('clone.engine')}
      buttonClassName={className}
      unavailableLabel={t('modelSettings.unavailable')}
      onChange={(next: string) => {
        void switchTo(next);
      }}
      renderOption={(entry: SearchOption) => {
        const option = entry as EngineOption;
        return (
          <span className="min-w-0 flex-1">
            <span className="block truncate leading-tight" title={option.label}>
              {option.label}
            </span>
            {option.disabled && option.reason && (
              <span className="block truncate text-[11px] leading-tight text-muted-foreground">
                {option.reason}
              </span>
            )}
          </span>
        );
      }}
      renderValue={() => (
        <>
          {current && !current.disabled ? (
            <CpuIcon className="size-4 text-muted-foreground" aria-hidden="true" />
          ) : (
            <AlertCircleIcon className="size-4 text-warning" aria-hidden="true" />
          )}
          <span className="max-w-40 truncate">
            {pending ? t('enginePicker.switching') : current?.label || t('clone.engine')}
          </span>
        </>
      )}
      header={<span className="min-w-0 truncate">{t('clone.engine')}</span>}
      footer={
        <div className="flex items-center justify-end gap-2">
          <a
            href="#/settings/models/tts"
            className="shrink-0 rounded text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring"
          >
            {t('languagePicker.changeModel')}
          </a>
        </div>
      }
    />
  );
}
