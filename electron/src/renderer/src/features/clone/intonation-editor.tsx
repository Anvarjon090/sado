import { useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PlayIcon, RotateCcwIcon, SaveIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { WaveformPlayer } from '@/components/waveform-player';
import { apiFetch, apiJson, describeError } from '@/lib/api/client';
import { createObjectUrl, revokeObjectUrl } from '@/lib/audio/object-url';
import { cn } from '@/lib/utils';

/** One script word on the take (backend `POST /audio/{id}/words`). */
export interface TakeWord {
  text: string;
  start: number;
  end: number;
}

interface WordsResponse {
  duration: number;
  approximate: boolean;
  words: TakeWord[];
}

/** A take stored by `POST /audio/{id}/intonation` with `save: true`. */
export interface SavedTake {
  id: string;
  audio_path: string;
  duration_seconds: number;
}

/** Each word moves up to this many semitones either way in the editor. */
export const WORD_SHIFT_RANGE = 6;

function formatShift(value: number): string {
  if (value === 0) return '0';
  return `${value > 0 ? '+' : '−'}${Math.abs(value)}`;
}

/**
 * Word-by-word intonation of a finished take: one vertical slider per word
 * of the script raises or lowers that word's melody in semitones. The words
 * are placed on the take by the backend (local ASR timings, or a syllable
 * estimate it flags as approximate). Listening renders without storing;
 * saving stores a new take beside the original, which stays untouched.
 */
export function IntonationEditor({
  audioPath,
  text,
  language,
  onSaved,
}: {
  /** Bare `<id>.wav` filename under `/audio/`. */
  audioPath: string;
  text: string;
  language?: string;
  onSaved: (take: SavedTake) => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const id = useId();
  const audioId = audioPath.replace(/\.wav$/i, '');
  const [words, setWords] = useState<WordsResponse | null>(null);
  const [shifts, setShifts] = useState<number[]>([]);
  const [busy, setBusy] = useState<'words' | 'preview' | 'save' | null>('words');
  const [failed, setFailed] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ blob: Blob; key: string } | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setBusy('words');
    setFailed(null);
    apiJson<WordsResponse>(`/audio/${encodeURIComponent(audioId)}/words`, {
      method: 'POST',
      body: JSON.stringify({ text, language: language && language !== 'Auto' ? language : null }),
      signal: controller.signal,
    })
      .then((response) => {
        setWords(response);
        setShifts(response.words.map(() => 0));
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setFailed(describeError(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(null);
      });
    return () => controller.abort();
  }, [audioId, text, language]);

  useEffect(() => {
    if (!preview) {
      setPreviewUrl(null);
      return;
    }
    const url = createObjectUrl(preview.blob);
    setPreviewUrl(url);
    return () => revokeObjectUrl(url);
  }, [preview]);

  const key = shifts.join(',');
  const edited = shifts.some((value) => value !== 0);
  const current = preview?.key === key ? preview : null;
  const edits = () =>
    (words?.words ?? [])
      .map((word, index) => ({ start: word.start, end: word.end, semitones: shifts[index] ?? 0 }))
      .filter((edit) => edit.semitones !== 0);

  const listen = async () => {
    setBusy('preview');
    setFailed(null);
    try {
      const response = await apiFetch(`/audio/${encodeURIComponent(audioId)}/intonation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ edits: edits(), save: false }),
      });
      setPreview({ blob: await response.blob(), key });
    } catch (error) {
      setFailed(describeError(error));
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    setBusy('save');
    setFailed(null);
    try {
      const take = await apiJson<SavedTake>(`/audio/${encodeURIComponent(audioId)}/intonation`, {
        method: 'POST',
        body: JSON.stringify({ edits: edits(), save: true }),
      });
      await onSaved(take);
    } catch (error) {
      setFailed(describeError(error));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-3 rounded-lg border border-border/60 bg-background/60 p-3">
      <div className="space-y-0.5">
        <p className="text-sm font-medium">{t('intonation.title')}</p>
        <p className="text-xs text-muted-foreground">{t('intonation.hint')}</p>
      </div>

      {busy === 'words' && (
        <p className="text-xs text-muted-foreground" role="status">
          {t('intonation.finding_words')}
        </p>
      )}

      {words && (
        <>
          {words.approximate && (
            <p role="note" className="text-xs text-warning">
              {t('intonation.approximate')}
            </p>
          )}
          <div className="overflow-x-auto pb-1">
            <div className="flex min-w-max items-end gap-1">
              {words.words.map((word, index) => {
                const value = shifts[index] ?? 0;
                return (
                  <div
                    key={`${index}-${word.start}`}
                    className={cn(
                      'flex w-14 flex-col items-center gap-1 rounded-md px-1 py-2',
                      value !== 0 && 'bg-primary/10',
                    )}
                  >
                    <output
                      className={cn(
                        'text-[11px] tabular-nums',
                        value !== 0 ? 'font-medium text-primary' : 'text-muted-foreground',
                      )}
                    >
                      {formatShift(value)}
                    </output>
                    <Slider
                      orientation="vertical"
                      className="h-28"
                      thumbProps={{
                        'aria-labelledby': `${id}-w${index}`,
                        'aria-describedby': `${id}-hint`,
                      }}
                      min={-WORD_SHIFT_RANGE}
                      max={WORD_SHIFT_RANGE}
                      step={0.5}
                      value={[value]}
                      disabled={busy !== null}
                      onValueChange={(next) => {
                        const shift = Array.isArray(next) ? next[0] : next;
                        setShifts((previous) =>
                          previous.map((item, position) => (position === index ? shift : item)),
                        );
                      }}
                    />
                    <span
                      id={`${id}-w${index}`}
                      className="w-full truncate text-center text-xs"
                      title={t('intonation.word_label', { word: word.text })}
                    >
                      {word.text}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
          <p id={`${id}-hint`} className="text-[11px] text-muted-foreground">
            {t('intonation.range_hint', { range: WORD_SHIFT_RANGE })}
          </p>
        </>
      )}

      {previewUrl && current ? (
        <WaveformPlayer
          key={previewUrl}
          src={previewUrl}
          source={'intonation-' + audioId}
          height={36}
          autoPlay
          compact
        />
      ) : null}

      {failed && (
        <p role="alert" className="text-xs text-destructive">
          {t('intonation.failed', { message: failed })}
        </p>
      )}

      {words && (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={busy !== null || !edited || Boolean(current)}
            onClick={() => void listen()}
          >
            <PlayIcon data-icon="inline-start" />
            {t(busy === 'preview' ? 'intonation.rendering' : 'intonation.listen')}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={busy !== null || !edited}
            onClick={() => setShifts((previous) => previous.map(() => 0))}
          >
            <RotateCcwIcon data-icon="inline-start" />
            {t('intonation.reset')}
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={busy !== null || !edited}
            onClick={() => void save()}
          >
            <SaveIcon data-icon="inline-start" />
            {t(busy === 'save' ? 'intonation.saving' : 'intonation.save')}
          </Button>
        </div>
      )}
    </div>
  );
}
