// Pure helpers for the CampaignScribe Discord recorder (no I/O, no discord.js).
export const RATE = 48000;          // decoder output rate
export const GAP_SAMPLES = 1920;    // > 40 ms behind wall clock -> insert silence

export function downmixStereoS16(chunk) {
  const frames = chunk.length >> 2;
  const mono = Buffer.alloc(frames * 2);
  for (let i = 0; i < frames; i++) {
    const l = chunk.readInt16LE(i * 4);
    const r = chunk.readInt16LE(i * 4 + 2);
    mono.writeInt16LE((l + r) >> 1, i * 2);
  }
  return mono;
}

// Samples of silence to write before a chunk of `frames` samples so the track stays
// aligned to wall-clock time since recording start.
export function silenceToInsert({ elapsedMs, written, frames }) {
  const expected = Math.round((elapsedMs / 1000) * RATE);
  const gap = expected - written;
  if (gap <= GAP_SAMPLES) return 0;
  return Math.max(0, expected - frames - written);
}

export function eventLine(event, fields = {}) {
  return JSON.stringify({ event, ...fields }) + '\n';
}

export function sanitizeName(name) {
  // eslint-disable-next-line no-control-regex
  const s = String(name ?? '').replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').trim();
  return s || 'user';
}

export function parseArgs(argv) {
  const has = (f) => argv.includes(f);
  const val = (f) => { const i = argv.indexOf(f); return i >= 0 && i + 1 < argv.length ? argv[i + 1] : null; };
  if (has('--list')) return { mode: 'list' };
  if (has('--record')) {
    const out = val('--out');
    if (!out) throw new Error('--record needs --out <dir>');
    return { mode: 'record', out, notice: val('--notice') ?? '', channel: val('--channel') };
  }
  throw new Error('mode required: --list or --record');
}

// Resolve once a writable stream has finished, errored or closed, so a stop never hangs on a
// stream that already failed (e.g. disk full).
export function endStream(ws) {
  return new Promise((resolve) => {
    if (ws.destroyed || ws.writableFinished) return resolve();
    const done = () => resolve();
    ws.once('finish', done);
    ws.once('error', done);
    ws.once('close', done);
    try { ws.end(); } catch { resolve(); }
  });
}
