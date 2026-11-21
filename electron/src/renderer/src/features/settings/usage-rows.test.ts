import { describe, expect, it } from 'vitest';
import { mergeLanguageRows, modeLabelKey } from './usage-rows';

describe('mergeLanguageRows', () => {
  it('counts a language once whether history stored its code or its name', () => {
    const rows = mergeLanguageRows(
      [
        { name: 'uz', count: 40 },
        { name: 'Uzbek', count: 2 },
        { name: 'en', count: 5 },
        { name: 'English', count: 3 },
        { name: 'auto', count: 1 },
      ],
      'en',
    );
    expect(rows).toEqual([
      { name: 'Uzbek', count: 42 },
      { name: 'English', count: 8 },
      { name: 'auto', count: 1 },
    ]);
  });

  it('labels codes in the interface language', () => {
    expect(mergeLanguageRows([{ name: 'ru', count: 1 }], 'de')).toEqual([
      { name: 'Russisch', count: 1 },
    ]);
  });

  it('keeps names it cannot resolve and drops empty ones', () => {
    expect(
      mergeLanguageRows(
        [
          { name: 'Klingon', count: 2 },
          { name: '  ', count: 9 },
        ],
        'en',
      ),
    ).toEqual([{ name: 'Klingon', count: 2 }]);
  });
});

describe('modeLabelKey', () => {
  it('names the stored modes and leaves unknown ones alone', () => {
    expect(modeLabelKey('clone')).toBe('nav.clone');
    expect(modeLabelKey('Design')).toBe('nav.design');
    expect(modeLabelKey('karaoke')).toBeUndefined();
  });
});
