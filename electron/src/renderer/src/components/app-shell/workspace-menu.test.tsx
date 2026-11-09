import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

const route = vi.hoisted(() => ({ pathname: '/gallery' }));
vi.mock('@tanstack/react-router', () => ({
  useRouterState: ({ select }: any) => select({ location: route }),
  Link: ({ to, activeProps: _activeProps, activeOptions: _activeOptions, children, ...props }: any) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/lib/store/workspace', () => ({ setWorkspace: vi.fn() }));
import { WorkspaceNavigation } from './workspace-menu';

it('lists each destination once: home, creation, then the library', () => {
  route.pathname = '/gallery';
  render(<WorkspaceNavigation />);
  const hrefs = Array.from(document.querySelectorAll('nav a'), (a) => a.getAttribute('href'));
  expect(hrefs.slice(0, 10)).toEqual([
    '/',
    '/clone',
    '/design',
    '/dub',
    '/stories',
    '/audiobook',
    '/transcriptions',
    '/personas',
    '/gallery',
    '/projects',
  ]);
  expect(new Set(hrefs).size).toBe(hrefs.length);
  expect(screen.getByText('nav.section_create')).toBeInTheDocument();
  expect(screen.getByText('nav.section_library')).toBeInTheDocument();
});

it('folds the rarer tools under More and opens it on their routes', () => {
  route.pathname = '/gallery';
  const { rerender } = render(<WorkspaceNavigation />);
  const more = screen.getByRole('button', { name: 'nav.more' });
  expect(more).toHaveAttribute('aria-expanded', 'false');
  fireEvent.click(more);
  expect(more).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByRole('link', { name: 'workflows.title' })).toHaveAttribute('href', '/calls');
  route.pathname = '/tools';
  rerender(<WorkspaceNavigation />);
  expect(screen.getByRole('button', { name: 'nav.more' })).toHaveAttribute(
    'aria-expanded',
    'true',
  );
});

it('keeps folded destinations reachable from the compact rail', async () => {
  route.pathname = '/gallery';
  render(<WorkspaceNavigation compact />);
  expect(screen.getByRole('link', { name: 'nav.clone' })).toHaveAttribute('href', '/clone');
  fireEvent.click(screen.getByRole('button', { name: 'nav.more' }));
  expect(await screen.findByRole('link', { name: 'nav.batch_dub' })).toHaveAttribute(
    'href',
    '/batch',
  );
});

it('opens a compact group for a mouse hover while ignoring touch hover', async () => {
  render(<WorkspaceNavigation compact />);
  const more = screen.getByRole('button', { name: 'nav.more' });
  fireEvent.pointerEnter(more, { pointerType: 'touch' });
  expect(screen.queryByRole('link', { name: 'tools.title' })).toBeNull();
  fireEvent.pointerEnter(more, { pointerType: 'mouse' });
  expect(await screen.findByRole('link', { name: 'tools.title' })).toBeInTheDocument();
  expect(more).toHaveAttribute('aria-expanded', 'true');
});

it('closes the compact flyout when choosing the current route again', async () => {
  route.pathname = '/tools';
  render(<WorkspaceNavigation compact />);
  fireEvent.click(screen.getByRole('button', { name: 'nav.more' }));
  fireEvent.click(await screen.findByRole('link', { name: 'tools.title' }));
  await waitFor(() => expect(screen.queryByRole('link', { name: 'tools.title' })).toBeNull());
});
