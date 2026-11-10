import { toast } from 'sonner';
import type { GenerateResult } from '@/lib/api/types';
import { tr } from '@/lib/i18n-text';

const DROPPED_TOAST_MS = 8000;
const SSML_TOAST_MS = 10000;
const DROPPED_TEXT_PREVIEW_CHARS = 120;

/**
 * Tell the user when part of the text rendered to no audio. The take still
 * plays, so nothing else would reveal the gap. Every surface that shows a
 * generation result must call this; `source` names which result was affected
 * when one view shows several (for example Compare voices A/B).
 */
export function announceDroppedSpeech(
  dropped: GenerateResult['dropped'] | undefined,
  source?: string,
): void {
  if (!dropped || !(dropped.count > 0)) return;
  const preview = dropped.text.trim().slice(0, DROPPED_TEXT_PREVIEW_CHARS);
  const count = dropped.count;
  toast.warning(
    preview
      ? tr('tts.droppedChunksWithText', { count, text: preview })
      : tr('tts.droppedChunks', { count }),
    { duration: DROPPED_TOAST_MS, ...(source ? { description: source } : {}) },
  );
}

/**
 * SSML the engine could not honour (pitch, phonemes, an unknown voice …) is
 * reported by the backend instead of being dropped silently; show it once.
 */
export function announceSsmlWarnings(warnings: string[] | null | undefined, source?: string): void {
  if (!warnings || warnings.length === 0) return;
  toast.warning(tr('tts.ssmlWarnings', { count: warnings.length, list: warnings.join(' · ') }), {
    duration: SSML_TOAST_MS,
    ...(source ? { description: source } : {}),
  });
}
