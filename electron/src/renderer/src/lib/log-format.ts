export type LogSeverity = 'error' | 'warning' | 'success' | 'debug' | 'info';

export function stripLogAnsi(line: string): string {
  let clean = '';
  for (let index = 0; index < line.length; index++) {
    if (line.charCodeAt(index) !== 27 || line[index + 1] !== '[') {
      clean += line[index];
      continue;
    }
    index += 2;
    while (index < line.length) {
      const code = line.charCodeAt(index);
      if (code >= 0x40 && code <= 0x7e) break;
      index++;
    }
  }
  return clean;
}

const PROBLEM_NOUN = String.raw`(?:errors?|failures?|failed|exceptions?|crash(?:es|ed)?|warn(?:ing)?s?)`;

/**
 * Mentions that report the ABSENCE of a problem: `no errors`, `0 failed`,
 * `zero failures`, `'failures': 0`, `error_count=0`, `errors: []`. They are
 * blanked before classifying, so a clean summary is not painted as an error
 * while a real problem elsewhere on the same line still is.
 */
const BENIGN_MENTION = new RegExp(
  String.raw`(?<![a-z0-9])(?:no|zero|0|without)\s+${PROBLEM_NOUN}(?![a-z0-9])` +
    String.raw`|(?<![a-z0-9])${PROBLEM_NOUN}(?:[_ -]?count)?['"]?\s*[:=]\s*` +
    String.raw`(?:0(?:\.0+)?|none|null|false|\[\s*\]|\{\s*\})(?![a-z0-9.])`,
  'gi',
);

export function logSeverity(line: string): LogSeverity {
  const value = stripLogAnsi(line).replace(BENIGN_MENTION, ' ');
  if (
    /(?:^|[\s[.:_-])(?:critical|fatal|error|exception|traceback|panic)(?:$|[\s\].:_-])/i.test(
      value,
    ) ||
    /(?<![a-z0-9])(?:failed|failures?|crashed)(?![a-z0-9])|unexpectedly stopped|unhandled rejection/i.test(
      value,
    )
  ) {
    return 'error';
  }
  if (/(?:^|[\s[.:_-])(?:warn|warning)(?:$|[\s\].:_-])|deprecated|retrying/i.test(value)) {
    return 'warning';
  }
  if (/(?:ready|complete|completed|succeeded|healthy|loaded)\b/i.test(value)) return 'success';
  if (/(?:^|[\s[.:_-])(?:debug|trace)(?:$|[\s\].:_-])/i.test(value)) return 'debug';
  return 'info';
}
