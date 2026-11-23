/**
 * OmniVoice's ceiling: time grows with every step, and 64 measured no better
 * than 32 while taking twice as long (backend OMNIVOICE_MAX_STEPS). A saved 64
 * — what the old Max preset wrote — is sent as 32.
 */
export const OMNIVOICE_MAX_STEPS = 32;

/** Engines whose adapters actually forward sampling steps to their model. */
export function samplingStepRange(engineId?: string | null): [number, number] | null {
  if (engineId === 'supertonic3') return [5, 12];
  if (engineId === 'omnivoice' || engineId === 'omnivoice-subprocess')
    return [8, OMNIVOICE_MAX_STEPS];
  if (engineId === 'voxcpm2' || engineId === 'dots-tts') return [8, 64];
  return null;
}

export function effectiveSamplingSteps(steps: number, engineId?: string | null): number {
  const range = samplingStepRange(engineId);
  return range ? Math.min(range[1], Math.max(range[0], steps)) : steps;
}
