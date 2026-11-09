import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ProfileAvatar, profileInitials } from './profile-avatar';

describe('profile portraits', () => {
  it('uses first and last initials and handles empty and Unicode names', () => {
    expect(profileInitials('  Scarlet Rose  ')).toBe('SR');
    expect(profileInitials('Scarlet')).toBe('S');
    expect(profileInitials('')).toBe('♪');
    expect(profileInitials('Émilie Rose')).toBe('ÉR');
    expect(profileInitials("Aisha (o'zbekcha)")).toBe('AO');
    expect(profileInitials('Sinov — 1-so‘zlovchi')).toBe('SS');
  });
  it('falls back to initials when the saved image cannot load', () => {
    const view = render(<ProfileAvatar name="Scarlet Rose" imageUrl="/profiles/one/image" />);
    fireEvent.error(view.container.querySelector('img')!);
    expect(screen.getByText('SR')).toBeInTheDocument();
  });
});
