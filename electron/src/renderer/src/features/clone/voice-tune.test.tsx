import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { Profile } from '@/lib/api/types';

const mock = vi.hoisted(() => ({ fetch: vi.fn(), create: vi.fn(), players: [] as string[] }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) =>
      values?.name ? `${key}:${values.name}` : values?.message ? `${key}:${values.message}` : key,
  }),
}));
vi.mock('@/lib/api/client', () => ({
  apiFetch: mock.fetch,
  describeError: (error: Error) => error.message,
}));
vi.mock('@/hooks/use-profiles', () => ({
  useCreateCloneProfile: () => ({ isPending: false, mutateAsync: mock.create }),
}));
vi.mock('@/lib/audio/object-url', () => ({
  createObjectUrl: () => 'blob:tuned',
  revokeObjectUrl: vi.fn(),
}));
vi.mock('@/components/waveform-player', () => ({
  WaveformPlayer: ({ src }: { src: string }) => {
    mock.players.push(src);
    return <div data-testid="player">{src}</div>;
  },
}));
import { VoiceTune } from './voice-tune';

const profile = {
  id: 'v1',
  name: 'Nodira',
  kind: 'clone',
  ref_audio_path: 'v1.wav',
  ref_text: 'salom dunyo',
  instruct: '',
  language: 'Uzbek',
  created_at: 1,
} as unknown as Profile;

function renderTune(onApply = vi.fn()) {
  render(<VoiceTune profile={profile} onApply={onApply} />);
  return onApply;
}

const button = (name: string) => screen.getByRole('button', { name: new RegExp(name) });

function answerWith(body = 'wav-bytes') {
  mock.fetch.mockResolvedValue({ blob: async () => new Blob([body], { type: 'audio/wav' }) });
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mock.players.length = 0;
});

it('offers nothing to render until a setting moves', () => {
  renderTune();
  for (const name of ['voiceTune.preview', 'voiceTune.apply', 'voiceTune.save_new'])
    expect(button(name)).toBeDisabled();
  expect(mock.fetch).not.toHaveBeenCalled();
});

it('previews the female preset through the tune route', async () => {
  answerWith();
  renderTune();

  fireEvent.click(button('voiceTune.preset_female'));
  expect(screen.getByText('+5')).toBeInTheDocument();
  expect(screen.getByText('+3')).toBeInTheDocument();
  fireEvent.click(button('voiceTune.preview'));

  expect(await screen.findByTestId('player')).toHaveTextContent('blob:tuned');
  expect(mock.fetch).toHaveBeenCalledWith(
    '/profiles/v1/tune',
    expect.objectContaining({ method: 'POST' }),
  );
  expect(JSON.parse(mock.fetch.mock.calls[0][1].body)).toEqual({ pitch: 5, timbre: 3, tempo: 1 });
  // The preview matches the sliders, so there is nothing new to render.
  expect(button('voiceTune.preview')).toBeDisabled();
});

it('hands the previewed clip to the editor without rendering it again', async () => {
  answerWith();
  const onApply = renderTune();

  fireEvent.click(button('voiceTune.preset_male'));
  fireEvent.click(button('voiceTune.preview'));
  await screen.findByTestId('player');
  fireEvent.click(button('voiceTune.apply'));

  await waitFor(() => expect(onApply).toHaveBeenCalledOnce());
  const file = onApply.mock.calls[0][0] as File;
  expect(file.name).toBe('tuned.wav');
  expect(file.type).toBe('audio/wav');
  expect(mock.fetch).toHaveBeenCalledOnce();
});

it('saves a separate voice that keeps the original transcript and language', async () => {
  answerWith();
  mock.create.mockResolvedValue({ ...profile, id: 'v2' });
  renderTune();

  fireEvent.click(button('voiceTune.preset_female'));
  fireEvent.click(button('voiceTune.save_new'));

  await waitFor(() => expect(mock.create).toHaveBeenCalledOnce());
  expect(mock.create).toHaveBeenCalledWith(
    expect.objectContaining({
      name: 'voiceTune.new_name:Nodira',
      refAudioName: 'tuned.wav',
      refText: 'salom dunyo',
      language: 'Uzbek',
    }),
  );
});

it('reports a failed render and lets the user retry', async () => {
  mock.fetch.mockRejectedValueOnce(new Error('recording missing'));
  const onApply = renderTune();

  fireEvent.click(button('voiceTune.preset_female'));
  fireEvent.click(button('voiceTune.apply'));

  expect(await screen.findByRole('alert')).toHaveTextContent('voiceTune.failed:recording missing');
  expect(onApply).not.toHaveBeenCalled();
  expect(button('voiceTune.apply')).toBeEnabled();
});

it('resets to the untouched voice', () => {
  renderTune();
  fireEvent.click(button('voiceTune.preset_female'));
  fireEvent.click(button('voiceTune.reset'));
  expect(button('voiceTune.apply')).toBeDisabled();
});
