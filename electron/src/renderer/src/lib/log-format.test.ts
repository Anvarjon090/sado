import { describe, expect, it } from 'vitest';
import { logSeverity, stripLogAnsi } from './log-format';

describe('log formatting', () => {
  it.each([
    ['2026-09-12 ERROR backend crashed', 'error'],
    ['Traceback (most recent call last):', 'error'],
    ['WARNING model is retrying', 'warning'],
    ['INFO Application startup complete.', 'success'],
    ['DEBUG request headers', 'debug'],
    ['INFO GET /health 200', 'info'],
  ])('classifies %s as %s', (line, severity) => {
    expect(logSeverity(line)).toBe(severity);
  });

  // A count or negation that reports the absence of a problem is not a problem.
  it.each([
    "INFO batch done {'processed': 12, 'failures': 0}",
    'INFO dubbing summary {"failed": 0, "errors": []}',
    'INFO 12 passed, 0 failed in 3.1s',
    'INFO preflight finished with no errors',
    'INFO error_count=0 warning_count=0',
    'INFO zero failures, without exceptions',
    'INFO checks complete: failures: 0, errors: none, crashes: null',
    'INFO lint: 0 warnings',
  ])('does not flag a clean summary: %s', (line) => {
    expect(logSeverity(line)).not.toMatch(/^(?:error|warning)$/);
  });

  it.each([
    ["INFO batch done {'processed': 12, 'failures': 3}", 'error'],
    ['INFO 10 failed, 2 passed', 'error'],
    ['INFO Download failed: connection reset', 'error'],
    ['INFO job_failed id=42', 'error'],
    ['ERROR worker died (failures: 0 before this one)', 'error'],
    ['INFO no errors expected, but backend crashed', 'error'],
    ['WARNING low disk, errors: 0', 'warning'],
    ['INFO 2 warnings: retrying', 'warning'],
  ])('still flags a real problem: %s -> %s', (line, severity) => {
    expect(logSeverity(line)).toBe(severity);
  });

  it('removes terminal color escapes before display', () => {
    expect(stripLogAnsi('\u001B[31mERROR\u001B[0m failed')).toBe('ERROR failed');
  });
});
