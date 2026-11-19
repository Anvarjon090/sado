import { Beam, Orb } from '@/components/motion-fx';
import { useState } from 'react';
import { AudioLinesIcon, SlidersVerticalIcon, XIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { SaveAudioButton } from '@/components/save-audio-button';
import { WaveformPlayer } from '@/components/waveform-player';
import { apiFetch, audioUrl } from '@/lib/api/client';
import { clearLatestOutput, setLatestOutput, useLatestOutput } from '@/lib/store/output';
import { useCloneSetting } from '@/lib/store/clone-settings';
import { useProfiles } from '@/hooks/use-profiles';
import { activePlaybackSource, stopActivePlayback, usePlaybackSource } from '@/lib/audio/playback';
import { formatSeconds } from './format';
import { AudioQuality } from './audio-quality';
import { AudioFileDetails } from './audio-file-details';
import { SectionLabel } from './section-label';
import { IntonationEditor, type SavedTake } from './intonation-editor';

export function OutputPanel() {
  const { t } = useTranslation();
  const { result, objectUrl, text } = useLatestOutput();
  const playingOutput = usePlaybackSource() === 'output';
  const chosenLanguage = useCloneSetting('language');
  const selectedProfileId = useCloneSetting('selectedProfileId');
  const profiles = useProfiles();
  // "Auto" means the voice's own language, which is also what the take was
  // spoken in; the recogniser placing the words should hear it the same way.
  const language =
    chosenLanguage && chosenLanguage !== 'Auto'
      ? chosenLanguage
      : profiles.data?.find((profile) => profile.id === selectedProfileId)?.language || undefined;
  const [editing, setEditing] = useState<string | null>(null);
  if (!result || !objectUrl) return null;
  // The editor belongs to the take it was opened on; a new take closes it.
  const editingThis = editing !== null && editing === result.audioPath;

  const adoptEditedTake = async (take: SavedTake) => {
    const response = await apiFetch(`/audio/${encodeURIComponent(take.audio_path)}`);
    setLatestOutput(
      {
        ...result,
        blob: await response.blob(),
        id: take.id,
        audioPath: take.audio_path,
        durationSeconds: take.duration_seconds,
        genTimeSeconds: 0,
      },
      text,
    );
    setEditing(null);
    toast.success(t('intonation.saved'));
  };

  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');

  return (
    <section
      aria-label={t('clone.output_title')}
      className="w-full border-t border-border/60 bg-muted/15 px-6 py-3"
    >
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <SectionLabel>
            {playingOutput ? (
              <Orb state="listening" size={20} aria-hidden="true" className="shrink-0" />
            ) : (
              <AudioLinesIcon aria-hidden="true" />
            )}
            {t('clone.output_title')}
          </SectionLabel>
          <div className="flex items-center gap-1">
            {result.audioPath && (
              <Button
                variant={editingThis ? 'secondary' : 'ghost'}
                size="sm"
                aria-expanded={editingThis}
                onClick={() => setEditing(editingThis ? null : result.audioPath)}
              >
                <SlidersVerticalIcon data-icon="inline-start" />
                {t('intonation.open')}
              </Button>
            )}
            <SaveAudioButton
              url={result.audioPath ? audioUrl(result.audioPath) : undefined}
              suggestedName={`sado-${result.id ?? stamp}.wav`}
            />
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t('common.close')}
              title={t('common.close')}
              onClick={() => {
                if (activePlaybackSource() === 'output') stopActivePlayback();
                clearLatestOutput();
              }}
            >
              <XIcon />
            </Button>
          </div>
        </div>
        {result && objectUrl ? (
          <>
            <Beam size="line" active={playingOutput} strength={0.9}>
              <div className="rounded-xl">
                <WaveformPlayer key={objectUrl} src={objectUrl} source="output" height={36} />
              </div>
            </Beam>
            {editingThis && result.audioPath && (
              <IntonationEditor
                audioPath={result.audioPath}
                text={text}
                language={language}
                onSaved={adoptEditedTake}
              />
            )}
            <AudioFileDetails blob={result.blob} />
            {result.audioPath && <AudioQuality key={objectUrl} audioPath={result.audioPath} />}
            <div className="flex flex-wrap items-start justify-between gap-3">
              <p
                className="line-clamp-2 min-w-40 flex-1 text-sm text-muted-foreground"
                title={text}
              >
                {text}
              </p>
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                {t('clone.output_meta', {
                  duration: formatSeconds(result.durationSeconds),
                  gen: formatSeconds(result.genTimeSeconds),
                })}
              </span>
            </div>
          </>
        ) : (
          <div className="flex min-h-24 items-center justify-center rounded-lg border border-dashed text-[length:var(--text-label)] text-muted-foreground">
            {t('clone.output_empty')}
          </div>
        )}
      </div>
    </section>
  );
}
