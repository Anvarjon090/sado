import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

const mock = vi.hoisted(() => ({ json: vi.fn(), fetch: vi.fn() }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, string>) =>
      values?.word ? `${key}:${values.word}` : values?.message ? `${key}:${values.message}` : key,
  }),
}));
vi.mock('@/lib/api/client', () => ({
  apiJson: mock.json,
  apiFetch: mock.fetch,
  describeError: (error: Error) => error.message,
}));
vi.mock('@/lib/audio/object-url', () => ({
  createObjectUrl: () => 'blob:edited',
  revokeObjectUrl: vi.fn(),
}));
vi.mock('@/components/waveform-player', () => ({
  WaveformPlayer: ({ src }: { src: string }) => <div data-testid="player">{src}</div>,
}));
import { IntonationEditor } from './intonation-editor';

const words = {
  duration: 2.4,
  approximate: false,
  words: [
    { text: 'Salom,', start: 0.2, end: 1.2 },
    { text: 'dunyo!', start: 1.2, end: 2.2 },
  ],
};

function renderEditor(onSaved = vi.fn()) {
  render(
    <IntonationEditor
      audioPath="abcd1234.wav"
      text="Salom, dunyo!"
      language="Uzbek"
      onSaved={onSaved}
    />,
  );
  return onSaved;
}

const button = (name: string) => screen.getByRole('button', { name: new RegExp(name) });

async function raiseSecondWord(steps = 2) {
  await screen.findByText('dunyo!');
  const slider = screen.getAllByRole('slider', { hidden: true })[1];
  for (let step = 0; step < steps; step += 1) fireEvent.keyDown(slider, { key: 'ArrowUp' });
}

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it('asks for the words of this take in its language and shows one control per word', async () => {
  mock.json.mockResolvedValueOnce(words);
  renderEditor();

  expect(await screen.findByText('Salom,')).toBeInTheDocument();
  expect(screen.getByText('dunyo!')).toBeInTheDocument();
  expect(screen.getAllByRole('slider', { hidden: true })).toHaveLength(2);
  expect(mock.json.mock.calls[0][0]).toBe('/audio/abcd1234/words');
  expect(JSON.parse(mock.json.mock.calls[0][1].body)).toEqual({
    text: 'Salom, dunyo!',
    language: 'Uzbek',
  });
  expect(screen.queryByRole('note')).toBeNull();
  for (const name of ['intonation.listen', 'intonation.reset', 'intonation.save'])
    expect(button(name)).toBeDisabled();
});

it('warns when the word positions are only estimated', async () => {
  mock.json.mockResolvedValueOnce({ ...words, approximate: true });
  renderEditor();
  expect(await screen.findByRole('note')).toHaveTextContent('intonation.approximate');
});

it('previews only the moved words without storing anything', async () => {
  mock.json.mockResolvedValueOnce(words);
  mock.fetch.mockResolvedValue({ blob: async () => new Blob(['wav']) });
  renderEditor();

  await raiseSecondWord();
  expect(screen.getByText('+1')).toBeInTheDocument();
  fireEvent.click(button('intonation.listen'));

  expect(await screen.findByTestId('player')).toHaveTextContent('blob:edited');
  expect(mock.fetch.mock.calls[0][0]).toBe('/audio/abcd1234/intonation');
  expect(JSON.parse(mock.fetch.mock.calls[0][1].body)).toEqual({
    edits: [{ start: 1.2, end: 2.2, semitones: 1 }],
    save: false,
  });
});

it('saves a new take and hands it back', async () => {
  const take = { id: 'ffff0000', audio_path: 'ffff0000.wav', duration_seconds: 2.4 };
  mock.json.mockResolvedValueOnce(words).mockResolvedValueOnce(take);
  const onSaved = renderEditor();

  await raiseSecondWord();
  fireEvent.click(button('intonation.save'));

  await waitFor(() => expect(onSaved).toHaveBeenCalledWith(take));
  expect(JSON.parse(mock.json.mock.calls[1][1].body)).toEqual({
    edits: [{ start: 1.2, end: 2.2, semitones: 1 }],
    save: true,
  });
});

it('resets every word and reports a failed render', async () => {
  mock.json.mockResolvedValueOnce(words);
  mock.fetch.mockRejectedValueOnce(new Error('Audio file not found'));
  renderEditor();

  await raiseSecondWord();
  fireEvent.click(button('intonation.listen'));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'intonation.failed:Audio file not found',
  );
  fireEvent.click(button('intonation.reset'));
  expect(button('intonation.save')).toBeDisabled();
});
