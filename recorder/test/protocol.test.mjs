// Protocol tests that need no Discord connection: missing token, bad arguments, and (opt-in,
// network) a rejected token that must never leak.
// Stop-on-stdin-EOF and the live capture path need a real Discord login, so they are covered
// by Task 3's fake-recorder test (Python side) and the manual acceptance run.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RECORDER = path.join(HERE, '..', 'recorder.mjs');

function run(args, env, cwd, keepStdin = false) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [RECORDER, ...args], {
      env: { ...process.env, DISCORD_TOKEN: '', ...env },
      cwd,
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d; });
    child.stderr.on('data', (d) => { stderr += d; });
    child.on('error', reject);
    child.on('close', (code) => resolve({ code, stdout, stderr }));
    if (!keepStdin) child.stdin.end();
  });
}

const lines = (s) => s.split('\n').filter(Boolean);

test('--list with no token prints one no_token error and exits 1', async () => {
  const r = await run(['--list'], { DISCORD_TOKEN: '' });
  assert.equal(r.code, 1);
  const l = lines(r.stdout);
  assert.equal(l.length, 1);
  const msg = JSON.parse(l[0]);
  assert.equal(msg.event, 'error');
  assert.equal(msg.code, 'no_token');
  assert.equal(typeof msg.message, 'string');
});

test('--record with no token prints no_token and exits 1', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cs-rec-'));
  const r = await run(['--record', '--out', dir, '--notice', 'hi'], { DISCORD_TOKEN: '' });
  assert.equal(r.code, 1);
  assert.equal(JSON.parse(lines(r.stdout)[0]).code, 'no_token');
  fs.rmSync(dir, { recursive: true, force: true });
});

test('no arguments prints bad_args and exits 1', async () => {
  const r = await run([], { DISCORD_TOKEN: '' });
  assert.equal(r.code, 1);
  const l = lines(r.stdout);
  assert.equal(l.length, 1);
  const msg = JSON.parse(l[0]);
  assert.equal(msg.event, 'error');
  assert.equal(msg.code, 'bad_args');
});

test('--record without --out prints bad_args even with a token set', async () => {
  const r = await run(['--record', '--notice', 'N'], { DISCORD_TOKEN: 'FAKE.TOKEN.VALUE' });
  assert.equal(r.code, 1);
  assert.equal(JSON.parse(lines(r.stdout)[0]).code, 'bad_args');
  assert.equal(r.stdout.includes('FAKE.TOKEN.VALUE'), false);
  assert.equal(r.stderr.includes('FAKE.TOKEN.VALUE'), false);
});

test('a rejected token yields login_failed and never leaks', { skip: !process.env.CS_NET_TESTS }, async () => {
  const FAKE = 'FAKE.TOKEN.VALUE';
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cs-rec-'));
  try {
    const r = await run(['--list'], { DISCORD_TOKEN: FAKE }, dir);
    assert.equal(r.code, 1);
    assert.equal(JSON.parse(lines(r.stdout).at(-1)).code, 'login_failed');
    assert.equal(r.stdout.includes(FAKE), false);
    assert.equal(r.stderr.includes(FAKE), false);

    const rec = path.join(dir, 'rec');
    const r2 = await run(['--record', '--out', rec, '--notice', 'n', '--channel', '1'], { DISCORD_TOKEN: FAKE }, dir, true);
    assert.equal(r2.code, 1);
    assert.equal(r2.stdout.includes(FAKE), false);
    assert.equal(r2.stderr.includes(FAKE), false);

    const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) =>
      e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]);
    for (const f of walk(dir)) {
      assert.equal(fs.readFileSync(f, 'utf8').includes(FAKE), false, `${f} leaked the token`);
    }
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
