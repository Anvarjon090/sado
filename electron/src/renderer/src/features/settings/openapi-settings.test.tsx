import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider, onlineManager } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';

const mock = vi.hoisted(() => ({ api: vi.fn(), openExternal: vi.fn() }));

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => <a href="#logs">{children}</a>,
}));
vi.mock('@/components/motion-fx', () => ({ LoadingOrb: () => <span /> }));
vi.mock('@/components/bridge', () => ({
  getBridge: () => ({ files: { openExternal: mock.openExternal } }),
}));
vi.mock('@/hooks/use-backend-status', () => ({
  useBackendStatus: () => ({ baseUrl: 'http://127.0.0.1:3900', stage: 'ready' }),
}));
vi.mock('@shared/utils/backendStage', () => ({ isBackendReachable: () => true }));
vi.mock('@/lib/api/client', () => ({
  apiJson: mock.api,
  apiPath: (path: string) => `/api${path}`,
  describeError: (error: unknown) => String(error),
}));
vi.mock('./scalar-api-reference', () => ({ default: () => <p>reference rendered</p> }));

import { OpenApiSettings } from './openapi-settings';

const RAW_URL = 'http://127.0.0.1:3900/openapi.json';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.useRealTimers();
  onlineManager.setOnline(true);
});

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <OpenApiSettings />
    </QueryClientProvider>,
  );
}

async function passDeadline() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(15_000);
  });
}

it('stops spinning when the spec never answers and offers retry and the raw spec', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  mock.api.mockReturnValue(new Promise(() => {}));
  mock.openExternal.mockResolvedValue(undefined);
  renderIt();
  expect(screen.getByText('common.loading')).toBeInTheDocument();

  await passDeadline();
  const alert = screen.getByRole('alert');
  expect(alert).toHaveTextContent('openapi.unreachable_title');
  expect(screen.queryByText('common.loading')).not.toBeInTheDocument();

  fireEvent.click(within(alert).getByRole('button', { name: 'openapi.open_raw' }));
  expect(mock.openExternal).toHaveBeenCalledWith(RAW_URL);

  mock.api.mockResolvedValue({ openapi: '3.1.0' });
  fireEvent.click(within(alert).getByRole('button', { name: 'common.retry' }));
  expect(await screen.findByText('reference rendered')).toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('does not wait forever while the backend is offline, and recovers when it returns', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  onlineManager.setOnline(false);
  mock.api.mockResolvedValue({ openapi: '3.1.0' });
  renderIt();
  expect(mock.api).not.toHaveBeenCalled();

  await passDeadline();
  expect(screen.getByRole('alert')).toHaveTextContent('openapi.unreachable_title');

  act(() => onlineManager.setOnline(true));
  expect(await screen.findByText('reference rendered')).toBeInTheDocument();
});

it('shows the same retry and raw-spec actions when the request fails', async () => {
  mock.api.mockRejectedValue(new Error('connection refused'));
  renderIt();
  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent('openapi.unreachable_title');
  expect(within(alert).getByRole('button', { name: 'common.retry' })).toBeInTheDocument();
  expect(within(alert).getByRole('button', { name: 'openapi.open_raw' })).toBeInTheDocument();
});
