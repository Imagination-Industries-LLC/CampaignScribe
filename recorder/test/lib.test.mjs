import { test } from 'node:test';
import assert from 'node:assert/strict';
import { downmixStereoS16, silenceToInsert, eventLine, sanitizeName, parseArgs, RATE } from '../lib.mjs';

test('downmix averages L/R', () => {
  const st = Buffer.alloc(8);
  st.writeInt16LE(1000, 0); st.writeInt16LE(3000, 2); st.writeInt16LE(-2, 4); st.writeInt16LE(-4, 6);
  const m = downmixStereoS16(st);
  assert.equal(m.length, 4);
  assert.equal(m.readInt16LE(0), 2000);
  assert.equal(m.readInt16LE(2), -3);
});

test('silenceToInsert fills gaps over 40 ms only', () => {
  // 1 s elapsed, 960-frame chunk arriving, nothing written yet -> pad up to the chunk's start
  assert.equal(silenceToInsert({ elapsedMs: 1000, written: 0, frames: 960 }), RATE - 960);
  // already caught up (gap <= 1920 samples) -> no pad
  assert.equal(silenceToInsert({ elapsedMs: 1000, written: RATE - 1000, frames: 960 }), 0);
  // never negative
  assert.equal(silenceToInsert({ elapsedMs: 10, written: 5000, frames: 960 }), 0);
});

test('eventLine is one JSON line', () => {
  const s = eventLine('user', { id: '1', name: 'Mi\nke' });
  assert.equal(s.endsWith('\n'), true);
  assert.equal(s.split('\n').length, 2);
  assert.deepEqual(JSON.parse(s), { event: 'user', id: '1', name: 'Mi\nke' });
});

test('sanitizeName', () => {
  assert.equal(sanitizeName('Mike'), 'Mike');
  assert.equal(sanitizeName('a/b\\c:d*e?f"g<h>i|j'), 'a_b_c_d_e_f_g_h_i_j');
  assert.equal(sanitizeName('   '), 'user');
  assert.equal(sanitizeName('x\u0001y'), 'x_y');
  assert.equal(sanitizeName('a'.repeat(300)), 'a'.repeat(80));
  assert.equal(sanitizeName(' '.repeat(5) + 'b'.repeat(79) + ' c'), 'b'.repeat(79));
});

test('parseArgs', () => {
  assert.deepEqual(parseArgs(['--list']), { mode: 'list' });
  assert.deepEqual(parseArgs(['--record', '--out', 'D', '--notice', 'N', '--channel', '5']),
    { mode: 'record', out: 'D', notice: 'N', channel: '5' });
  assert.deepEqual(parseArgs(['--record', '--out', 'D', '--notice', 'N']),
    { mode: 'record', out: 'D', notice: 'N', channel: null });
  assert.throws(() => parseArgs(['--record', '--notice', 'N']), /--out/);
  assert.throws(() => parseArgs([]), /mode/);
});

test('endStream resolves for a healthy, an errored and an already-closed stream', async () => {
  const fs = await import('node:fs');
  const os = await import('node:os');
  const path = await import('node:path');
  const { endStream } = await import('../lib.mjs');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cs-es-'));
  try {
    const ok = fs.createWriteStream(path.join(dir, 'ok.pcm'));
    ok.write(Buffer.alloc(10));
    await endStream(ok);
    assert.equal(fs.statSync(path.join(dir, 'ok.pcm')).size, 10);

    // Force an error state: the target path is a directory, so opening fails.
    const bad = fs.createWriteStream(dir);
    bad.on('error', () => {});
    await new Promise((r) => bad.once('error', r));
    await endStream(bad);            // must not hang

    await endStream(ok);             // already finished: must not hang
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
