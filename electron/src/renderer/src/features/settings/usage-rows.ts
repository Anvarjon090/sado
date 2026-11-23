export interface UsageCount {
  name: string;
  count: number;
}

const CODE = /^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$/i;

function displayName(code: string, locale: string): string | undefined {
  try {
    return new Intl.DisplayNames([locale], { type: 'language' }).of(code) ?? undefined;
  } catch {
    return undefined;
  }
}

/* History stores a take's language either as a code ("uz") or as an English
   name ("Uzbek"), so one language could appear twice. Merge them under one
   row, labelled in the interface language, biggest first. */
export function mergeLanguageRows(rows: UsageCount[], locale: string): UsageCount[] {
  const merged = new Map<string, UsageCount>();
  for (const row of rows) {
    const raw = row.name.trim();
    if (!raw) continue;
    const isCode = CODE.test(raw) && raw.toLowerCase() !== 'auto';
    const english = isCode ? displayName(raw, 'en') : raw;
    const key = (english ?? raw).toLocaleLowerCase('en');
    const label = isCode ? (displayName(raw, locale) ?? raw) : raw;
    const current = merged.get(key);
    if (current) {
      current.count += row.count;
      if (isCode) current.name = label;
    } else {
      merged.set(key, { name: label, count: row.count });
    }
  }
  return [...merged.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

const MODE_KEYS: Record<string, string> = {
  clone: 'nav.clone',
  design: 'nav.design',
  dub: 'nav.dub',
};

/** The i18n key for a stored generation mode, when the app has a name for it. */
export function modeLabelKey(mode: string): string | undefined {
  return MODE_KEYS[mode.trim().toLowerCase()];
}
