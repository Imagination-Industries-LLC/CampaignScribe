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
