import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock('@/lib/api/client', () => ({
  apiJson: mocks.api,
  describeError: (cause: unknown) => (cause instanceof Error ? cause.message : String(cause)),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
import { StarterVoicesCard } from './starter-voices-card';
import { parseStarterVoicesOffer, starterVoicesStore } from '@/lib/store/starter-voices';

beforeEach(() => {
  starterVoicesStore.setState(() => ({ offer: 'pending' }));
  mocks.api.mockReset();
});
afterEach(cleanup);

function renderCard() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <StarterVoicesCard />
    </QueryClientProvider>,
  );
}

it('fetches nothing until asked, then installs the pack and steps aside', async () => {
  mocks.api.mockResolvedValue({
    installed: [{ item_id: 'sado_nilufar', profile_id: 'p1', name: 'Nilufar' }],
    failed: [],
  });
  renderCard();
  expect(mocks.api).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: /clone\.starter_install/ }));
  await waitFor(() =>
    expect(mocks.api).toHaveBeenCalledWith('/community/packs/sado-starter/install', {
      method: 'POST',
    }),
  );
  await waitFor(() => expect(screen.queryByText('clone.starter_title')).toBeNull());
  expect(starterVoicesStore.state.offer).toBe('installed');
});

it('stays out of the way after "not now"', () => {
  renderCard();
  fireEvent.click(screen.getByRole('button', { name: 'clone.starter_later' }));
  expect(screen.queryByText('clone.starter_title')).toBeNull();
  expect(starterVoicesStore.state.offer).toBe('dismissed');
});

it('reports a failed download and keeps offering', async () => {
  mocks.api.mockRejectedValue(new Error('offline'));
  renderCard();
  fireEvent.click(screen.getByRole('button', { name: /clone\.starter_install/ }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('clone.starter_failed'));
  expect(starterVoicesStore.state.offer).toBe('pending');
});

it('treats a pack where nothing installed as a failure', async () => {
  mocks.api.mockResolvedValue({
    installed: [],
    failed: [{ item_id: 'x', detail: 'gone' }],
  });
  renderCard();
  fireEvent.click(screen.getByRole('button', { name: /clone\.starter_install/ }));
  await waitFor(() => expect(screen.getByRole('alert')).toBeVisible());
  expect(starterVoicesStore.state.offer).toBe('pending');
});

it('ignores a malformed or foreign stored value', () => {
  expect(parseStarterVoicesOffer(null)).toBe('pending');
  expect(parseStarterVoicesOffer('not json')).toBe('pending');
  expect(parseStarterVoicesOffer('{"offer":"deleted"}')).toBe('pending');
  expect(parseStarterVoicesOffer('{"offer":"installed"}')).toBe('installed');
});
