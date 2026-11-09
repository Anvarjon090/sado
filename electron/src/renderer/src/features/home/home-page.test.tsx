import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

const navigate = vi.hoisted(() => vi.fn());
vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children, ...props }: { to: string; children: ReactNode }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  useNavigate: () => navigate,
}));
vi.mock('@tanstack/react-query', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/react-query')>()),
  useQuery: () => ({ data: [] }),
}));
vi.mock('@/hooks/use-profiles', () => ({ useProfiles: () => ({ data: [] }) }));
vi.mock('@/hooks/use-engines', () => ({ useEngines: () => ({ activeTts: { display_name: 'OmniVoice (local)' } }) }));
vi.mock('@/components/app-shell/workspace-header', () => ({
  WorkspaceHeader: ({ children }: { children: ReactNode }) => <header>{children}</header>,
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
import { HomePage } from './home-page';
import en from '@/i18n/locales/en.json';
import { cloneSettingsStore } from '@/lib/store/clone-settings';

afterEach(cleanup);

it('leads with the shared script box and opens it in the voice studio', () => {
  navigate.mockClear();
  render(<HomePage />);
  expect(screen.getByText(/clone\.auto/)).toHaveTextContent('clone.auto · OmniVoice');
  const script = screen.getByLabelText('homeUi.scriptLabel');
  fireEvent.change(script, { target: { value: 'Assalomu alaykum' } });
  expect(cloneSettingsStore.state.text).toBe('Assalomu alaykum');
  fireEvent.click(screen.getByRole('button', { name: /homeUi.continue/ }));
  expect(navigate).toHaveBeenCalledWith({ to: '/clone' });
});

it('leaves destinations and voices to the sidebar and offers a way in when there is no work yet', () => {
  render(<HomePage />);
  expect(screen.queryByRole('navigation')).toBeNull();
  expect(screen.getByText(/homeUi.noProjects/)).toBeVisible();
  expect(screen.getByRole('link', { name: 'dubWorkspace.title' })).toHaveAttribute('href', '/dub');
  expect(screen.getByRole('link', { name: 'audiobook.title' })).toHaveAttribute(
    'href',
    '/audiobook',
  );
  expect(document.querySelector('img')).toBeNull();
});

it('keeps the Dubbing name consistent across catalogs', () => {
  expect(en.dubWorkspace.title).toBe('Dubbing');
  expect(en.nav.dub).toBe('Dubbing');
  expect(en.keyboard.dub).toBe('Dubbing');
});
