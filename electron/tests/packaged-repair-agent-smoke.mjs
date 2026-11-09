import { _electron as electron } from 'playwright';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import assert from 'node:assert/strict';

const executablePath =
  process.env.SADO_PACKAGED_EXE ||
  resolve(
    process.platform === 'win32'
      ? 'electron/release/win-unpacked/Sado.exe'
      : process.platform === 'darwin'
        ? 'electron/release/mac/Sado.app/Contents/MacOS/Sado'
        : 'electron/release/linux-unpacked/sado-electron',
  );
const profile = mkdtempSync(join(tmpdir(), 'sado-packaged-repair-'));
const app = await electron.launch({
  executablePath,
  args: ['--user-data-dir=' + profile],
  env: {
    ...process.env,
    SADO_ALLOW_MULTIPLE_INSTANCES: '1',
    SADO_SKIP_BACKEND: '1',
  },
});

try {
  const page = await app.firstWindow();
  await page.waitForFunction(() => Boolean(window.sado?.repair));
  const state = await page.evaluate(() => window.sado.repair.getState());
  assert.equal(state.workspaceAvailable, false);
  assert.equal(state.workspacePath, undefined);

  const agents = await page.evaluate(() => window.sado.repair.list());
  assert.ok(
    agents.some((agent) => agent.available),
    'At least one local agent is required',
  );
  await page.evaluate(() => {
    window.location.hash = '/settings/updates';
  });
  const launcher = page.getByRole('button', { name: 'Ask Sado Agent' });
  await launcher.waitFor();
  await page.evaluate(() => {
    window.dispatchEvent(
      new CustomEvent('sado:repair-agent-open', {
        detail: { report: 'ACTION_REQUEST: inspect the current app setup', autoFix: false },
      }),
    );
  });
  const dock = page.getByRole('region', { name: 'Ask Sado Agent' });
  await dock.waitFor();
  assert.equal(await dock.getByRole('button', { name: 'Send', exact: true }).isEnabled(), true);
  assert.equal(await dock.getByRole('button', { name: 'Plan', exact: true }).isEnabled(), true);
  assert.equal(await dock.getByRole('button', { name: 'Choose folder…' }).count(), 0);

  const ordinaryError = await page.evaluate(async () => {
    const available = (await window.sado.repair.list()).find((agent) => agent.available);
    try {
      await window.sado.repair.start({
        agent: available.id,
        mode: 'diagnose',
        report: 'Diagnose this renderer failure',
        context: '{}',
      });
      return '';
    } catch (error) {
      return String(error);
    }
  });
  assert.match(ordinaryError, /source checkout is required/i);

  const unavailable = agents.find((agent) => !agent.available);
  if (unavailable) {
    const actionError = await page.evaluate(async (agent) => {
      try {
        await window.sado.repair.start({
          agent,
          mode: 'fix',
          report: 'ACTION_REQUEST: inspect the current app setup',
          context: '{}',
        });
        return '';
      } catch (error) {
        return String(error);
      }
    }, unavailable.id);
    assert.match(actionError, /agent is not installed/i);
    assert.doesNotMatch(actionError, /source checkout is required/i);
  }
  console.log(
    'PASS: packaged app actions run without source while code repair remains source-gated',
  );
} finally {
  await app.close();
  rmSync(profile, { recursive: true, force: true });
}
