import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import '@/i18n';
import { EnginePicker, engineShortName } from './engine-picker';

const api = vi.hoisted(() => ({ apiJson: vi.fn() }));
const toasts = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }));
vi.mock('@/lib/api/client', () => ({
  apiJson: api.apiJson,
  describeError: (error: unknown) => String(error),
}));
vi.mock('sonner', () => ({ toast: toasts }));
vi.mock('@/hooks/use-engines', () => ({
  useEngines: () => ({
    isLoading: false,
    activeTts: { id: 'navoiy', display_name: 'Navoiy-TTS (Uzbek, 10 emotions)', available: true },
    data: {
      tts: {
        active: 'navoiy',
        backends: [
          {
            id: 'navoiy',
            display_name: 'Navoiy-TTS (Uzbek, 10 emotions)',
            available: true,
            reason: null,
          },
          { id: 'omnivoice', display_name: 'Sado Pro', available: true, reason: null },
          {
            id: 'kittentts',
            display_name: 'KittenTTS (preset voices)',
            available: false,
            reason: 'install kittentts',
          },
        ],
      },
    },
  }),
}));

function renderPicker() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <EnginePicker />
    </QueryClientProvider>,
  );
}

it('drops the parenthetical from engine names', () => {
  expect(engineShortName('Navoiy-TTS (Uzbek, 10 emotions)')).toBe('Navoiy-TTS');
  expect(engineShortName('Sado Pro')).toBe('Sado Pro');
});

it('lists the engines and switches through /engines/select like Settings does', async () => {
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(320);
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(340);
  api.apiJson.mockResolvedValue({ active: 'omnivoice', routing_status: 'accelerated' });
  renderPicker();
  const button = screen.getByRole('button', { name: 'Engine' });
  expect(button).toHaveTextContent('Navoiy-TTS');
  fireEvent.click(button);
  expect(await screen.findByRole('option', { name: /Sado Pro/ })).toBeEnabled();
  expect(screen.getByRole('option', { name: /KittenTTS/ })).toBeDisabled();
  fireEvent.click(screen.getByRole('option', { name: /Sado Pro/ }));
  await waitFor(() =>
    expect(api.apiJson).toHaveBeenCalledWith('/engines/select', {
      method: 'POST',
      body: JSON.stringify({ family: 'tts', backend_id: 'omnivoice' }),
    }),
  );
  await waitFor(() => expect(toasts.success).toHaveBeenCalled());
});

it('reports a failed switch instead of pretending it worked', async () => {
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(320);
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(340);
  api.apiJson.mockRejectedValue(new Error('Backend omnivoice not ready: loading'));
  renderPicker();
  fireEvent.click(screen.getByRole('button', { name: 'Engine' }));
  fireEvent.click(await screen.findByRole('option', { name: /Sado Pro/ }));
  await waitFor(() =>
    expect(toasts.error).toHaveBeenCalledWith('Error: Backend omnivoice not ready: loading'),
  );
});
