import { useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CopyPlusIcon, PlayIcon, RotateCcwIcon, WandSparklesIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { WaveformPlayer } from '@/components/waveform-player';
import { useCreateCloneProfile } from '@/hooks/use-profiles';
import { apiFetch, describeError } from '@/lib/api/client';
import type { Profile } from '@/lib/api/types';
import { createObjectUrl, revokeObjectUrl } from '@/lib/audio/object-url';

/** Semitones for pitch and timbre, a speed factor for tempo (backend `VoiceTune`). */
export interface TuneSettings {
  pitch: number;
  timbre: number;
  tempo: number;
}

export const NEUTRAL_TUNE: TuneSettings = { pitch: 0, timbre: 0, tempo: 1 };

/**
 * One-click starting points. Raising pitch and timbre together turns a male
 * reference into a convincing female one (and the reverse): pitch alone gives
 * a "sped-up" voice, because the vocal tract stays the size it was.
 */
export const TUNE_PRESETS = {
  female: { pitch: 5, timbre: 3, tempo: 1 },
  male: { pitch: -5, timbre: -3, tempo: 1 },
} as const satisfies Record<string, TuneSettings>;

const CONTROLS = [
  { key: 'pitch', min: -12, max: 12, step: 0.5 },
  { key: 'timbre', min: -6, max: 6, step: 0.5 },
  { key: 'tempo', min: 0.75, max: 1.25, step: 0.05 },
] as const;

const TUNED_FILE_NAME = 'tuned.wav';

function formatValue(key: keyof TuneSettings, value: number): string {
  if (key === 'tempo') return `${value.toFixed(2)}×`;
  if (value === 0) return '0';
  return `${value > 0 ? '+' : '−'}${Math.abs(value)}`;
}

function sameTune(a: TuneSettings, b: TuneSettings): boolean {
  return a.pitch === b.pitch && a.timbre === b.timbre && a.tempo === b.tempo;
}

/**
 * Manual voice tuning for a recorded voice: pitch, timbre and tempo of its
 * reference sample. The backend renders the tuned clip without storing it;
 * the user previews it, then either hands it to the editor as this voice's
 * new reference (saved with the rest of the edits) or saves it as a separate
 * voice so the original stays untouched.
 */
export function VoiceTune({
  profile,
  disabled = false,
  onApply,
}: {
  profile: Profile;
  disabled?: boolean;
  onApply: (file: File) => void;
}) {
  const { t } = useTranslation();
  const id = useId();
  const createProfile = useCreateCloneProfile();
  const [settings, setSettings] = useState<TuneSettings>(NEUTRAL_TUNE);
  const [rendered, setRendered] = useState<{ blob: Blob; settings: TuneSettings } | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [rendering, setRendering] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    if (!rendered) {
      setPreviewUrl(null);
      return;
    }
    const url = createObjectUrl(rendered.blob);
    setPreviewUrl(url);
    return () => revokeObjectUrl(url);
  }, [rendered]);

  const neutral = sameTune(settings, NEUTRAL_TUNE);
  const busy = disabled || rendering || createProfile.isPending;
  const current = rendered && sameTune(rendered.settings, settings) ? rendered : null;

  /** The clip for the sliders as they stand; reuses the preview when it matches. */
  const render = async (): Promise<Blob | null> => {
    if (current) return current.blob;
    setRendering(true);
    setFailed(null);
    try {
      const response = await apiFetch(`/profiles/${encodeURIComponent(profile.id)}/tune`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      const blob = await response.blob();
      setRendered({ blob, settings });
      return blob;
    } catch (error) {
      setFailed(describeError(error));
      return null;
    } finally {
      setRendering(false);
    }
  };

  const apply = async () => {
    const blob = await render();
    if (blob) onApply(new File([blob], TUNED_FILE_NAME, { type: 'audio/wav' }));
  };

  const saveAsNew = async () => {
    const blob = await render();
    if (!blob) return;
    try {
      await createProfile.mutateAsync({
        name: t('voiceTune.new_name', { name: profile.name }),
        refAudio: blob,
        refAudioName: TUNED_FILE_NAME,
        // Pitch, timbre and tempo do not change the words, so the clip keeps
        // the original transcript instead of being transcribed again.
        refText: profile.ref_text ?? '',
        instruct: profile.instruct ?? '',
        language: profile.language || 'Auto',
      });
    } catch {
      /* The shared mutation reports the error and keeps the preview for retry. */
    }
  };

  return (
    <div className="space-y-3 rounded-md border border-border/60 bg-background/60 p-3">
      <div className="space-y-0.5">
        <p className="text-sm font-medium">{t('voiceTune.title')}</p>
        <p className="text-xs text-muted-foreground">{t('voiceTune.hint')}</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {(Object.keys(TUNE_PRESETS) as (keyof typeof TUNE_PRESETS)[]).map((preset) => (
          <Button
            key={preset}
            type="button"
            variant="secondary"
            size="sm"
            disabled={busy}
            aria-pressed={sameTune(settings, TUNE_PRESETS[preset])}
            onClick={() => setSettings(TUNE_PRESETS[preset])}
          >
            {t(`voiceTune.preset_${preset}`)}
          </Button>
        ))}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={busy || neutral}
          onClick={() => setSettings(NEUTRAL_TUNE)}
        >
          <RotateCcwIcon data-icon="inline-start" />
          {t('voiceTune.reset')}
        </Button>
      </div>

      {CONTROLS.map(({ key, min, max, step }) => (
        <div key={key} className="space-y-2">
          <div className="flex justify-between gap-2 text-xs">
            <span id={`${id}-${key}`} className="font-medium">
              {t(`voiceTune.${key}`)}
            </span>
            <output className="text-primary tabular-nums" aria-labelledby={`${id}-${key}`}>
              {formatValue(key, settings[key])}
            </output>
          </div>
          <Slider
            thumbProps={{
              'aria-labelledby': `${id}-${key}`,
              'aria-describedby': `${id}-${key}-hint`,
            }}
            min={min}
            max={max}
            step={step}
            value={[settings[key]]}
            disabled={busy}
            onValueChange={(value) => {
              const next = Array.isArray(value) ? value[0] : value;
              setSettings((previous) => ({ ...previous, [key]: next }));
            }}
          />
          <p id={`${id}-${key}-hint`} className="text-[11px] text-muted-foreground">
            {t(`voiceTune.${key}_hint`)}
          </p>
        </div>
      ))}

      {previewUrl && current ? (
        <WaveformPlayer
          key={previewUrl}
          src={previewUrl}
          source={'voice-tune-' + profile.id}
          height={44}
          autoPlay
          compact
        />
      ) : null}

      {failed && (
        <p role="alert" className="text-xs text-destructive">
          {t('voiceTune.failed', { message: failed })}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={busy || neutral || Boolean(current)}
          onClick={() => void render()}
        >
          <PlayIcon data-icon="inline-start" />
          {t(rendering ? 'voiceTune.rendering' : 'voiceTune.preview')}
        </Button>
        <Button type="button" size="sm" disabled={busy || neutral} onClick={() => void apply()}>
          <WandSparklesIcon data-icon="inline-start" />
          {t('voiceTune.apply')}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={busy || neutral}
          onClick={() => void saveAsNew()}
        >
          <CopyPlusIcon data-icon="inline-start" />
          {t('voiceTune.save_new')}
        </Button>
      </div>
    </div>
  );
}
