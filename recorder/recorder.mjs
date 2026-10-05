// CampaignScribe Discord recorder.
// Speaks a one-JSON-object-per-line protocol on stdout (see README.md); stdin takes commands.
// The bot token is read ONLY from the DISCORD_TOKEN environment variable and is never
// printed, logged or written anywhere.
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { Client, GatewayIntentBits, ChannelType } from 'discord.js';
import { joinVoiceChannel, entersState, VoiceConnectionStatus, EndBehaviorType } from '@discordjs/voice';
import prism from 'prism-media';
import { RATE, downmixStereoS16, silenceToInsert, eventLine, parseArgs } from './lib.mjs';

const TOKEN = process.env.DISCORD_TOKEN || '';
const STOP_MESSAGE = '⏹️ Recording stopped.';

let logStream = null;
let stopping = false;
let exiting = false;
let clientRef = null;

// Defence in depth: scrub the token out of anything we might print or log.
const redact = (s) => {
  const str = String(s ?? '');
  return TOKEN ? str.split(TOKEN).join('***') : str;
};
const log = (m) => {
  const line = `${new Date().toISOString()} ${redact(m)}\n`;
  process.stderr.write(line);
  if (logStream) logStream.write(line);
};
const out = (event, fields) => process.stdout.write(eventLine(event, fields));

function exitNow(code) {
  if (exiting) return;
  exiting = true;
  // Tear the gateway down first: exiting mid-close trips a libuv assertion on Windows.
  const finish = async () => {
    try { if (clientRef) await clientRef.destroy(); } catch { /* ignore */ }
    setTimeout(() => process.stdout.write('', () => process.exit(code)), 50);
  };
  if (logStream) logStream.end(finish); else finish();
}
function fail(code, message, exitCode = 1) {
  out('error', { code, message: redact(message) });
  exitNow(exitCode);
}

process.on('uncaughtException', (e) => log(`uncaught ${e && e.stack}`));
process.on('unhandledRejection', (e) => log(`unhandled rejection ${e && e.stack ? e.stack : e}`));

let args;
try {
  args = parseArgs(process.argv.slice(2));
} catch (e) {
  fail('bad_args', e.message);
}
if (args && !TOKEN) fail('no_token', 'DISCORD_TOKEN is not set.');
if (args && TOKEN) main(args);

function main(args) {
  const OUT = args.mode === 'record' ? path.resolve(args.out) : null;
  if (OUT) {
    fs.mkdirSync(OUT, { recursive: true });
    logStream = fs.createWriteStream(path.join(OUT, 'recorder.log'), { flags: 'a' });
  }

  const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildVoiceStates] });
  clientRef = client;
  client.on('error', (e) => log(`client error ${e.message}`));

  const tracks = new Map();   // userId -> { ws, written, packets, opus, dec }
  const names = {};
  const lastSpeaking = new Map();
  let decodeErrors = 0;
  let recordStart = 0;
  let connection = null;
  let channel = null;
  let telemetryTimer = null;

  const writeTracksJson = () => {
    if (!OUT) return;
    try { fs.writeFileSync(path.join(OUT, 'tracks.json'), JSON.stringify(names, null, 2)); }
    catch (e) { log(`tracks.json write failed: ${e.message}`); }
  };

  function writeZeros(t, n) {
    while (n > 0) {
      const c = Math.min(n, RATE);
      t.ws.write(Buffer.alloc(c * 2));
      t.written += c;
      n -= c;
    }
  }

  // (Re)attach the opus receive stream + decoder to an existing track. The write stream and
  // `written` counter are kept so a rejoin only replaces opus and dec.
  function attach(receiver, userId, t) {
    const opus = receiver.subscribe(userId, { end: { behavior: EndBehaviorType.Manual } });
    const dec = new prism.opus.Decoder({ rate: RATE, channels: 2, frameSize: 960 });
    t.opus = opus;
    t.dec = dec;
    opus.on('data', () => { t.packets++; });
    opus.on('error', (e) => log(`receive stream error ${userId}: ${e.message}`));
    dec.on('error', (e) => { decodeErrors++; if (decodeErrors < 20) log(`decode error ${userId}: ${e.message}`); });
    dec.on('data', (chunk) => {
      if (stopping) return;
      const mono = downmixStereoS16(chunk);
      const frames = mono.length >> 1;
      const pad = silenceToInsert({ elapsedMs: Date.now() - recordStart, written: t.written, frames });
      if (pad > 0) writeZeros(t, pad);
      t.ws.write(mono);
      t.written += frames;
    });
    opus.pipe(dec);
  }

  function startTrack(receiver, guild, userId) {
    const ws = fs.createWriteStream(path.join(OUT, `${userId}.pcm`));
    const t = { ws, written: 0, packets: 0, opus: null, dec: null };
    tracks.set(userId, t);
    names[userId] = userId;
    writeTracksJson();
    out('user', { id: userId, name: userId });
    guild.members.fetch(userId).then((m) => {
      names[userId] = m.displayName || m.user.username;
      writeTracksJson();
      out('user', { id: userId, name: names[userId] });
    }).catch((e) => { log(`member fetch failed ${userId}: ${e.message}`); });
    log(`subscribe ${userId}`);
    attach(receiver, userId, t);
  }

  async function stop(reason) {
    if (stopping) return;
    stopping = true;
    log(`stopping: ${reason}`);
    if (telemetryTimer) clearInterval(telemetryTimer);
    const seconds = recordStart ? Math.round((Date.now() - recordStart) / 1000) : 0;
    const total = recordStart ? Math.round(((Date.now() - recordStart) / 1000) * RATE) : 0;
    for (const [id, t] of tracks) {
      try { t.opus.unpipe(t.dec); t.opus.destroy(); } catch { /* already gone */ }
      if (total > t.written) writeZeros(t, total - t.written);
      await new Promise((r) => t.ws.end(r));
      log(`closed ${id} samples=${t.written} (${(t.written / RATE).toFixed(2)}s)`);
    }
    writeTracksJson();
    if (channel) {
      try { await channel.send(STOP_MESSAGE); } catch (e) { log(`stop msg failed: ${e.message}`); }
    }
    try { if (connection) connection.destroy(); } catch { /* ignore */ }
    try { await client.destroy(); } catch { /* ignore */ }
    log('exit 0');
    out('stopped', { seconds });
    exitNow(0);
  }

  // stdin: {"cmd":"stop"} or EOF stops the recording (EOF = parent died / closed the pipe).
  // Full stop-on-EOF behaviour needs a live Discord login, so it is covered by Task 3's
  // fake-recorder test and the manual acceptance run, not by protocol.test.mjs.
  function watchStdin() {
    const rl = readline.createInterface({ input: process.stdin });
    rl.on('line', (line) => {
      let msg;
      try { msg = JSON.parse(line); } catch { log('stdin: ignoring non-JSON line'); return; }
      if (msg && msg.cmd === 'stop') stop('stop command');
      else log('stdin: ignoring unknown command');
    });
    rl.on('close', () => stop('stdin EOF'));
    process.stdin.on('end', () => stop('stdin end'));
  }

  async function fetchInventory() {
    const app = await client.application.fetch();
    const owner = app.owner && app.owner.username ? { id: app.owner.id, name: app.owner.username } : null;
    let ownerVoice = null;
    if (owner) {
      for (const g of client.guilds.cache.values()) {
        const cid = g.voiceStates.cache.get(owner.id)?.channelId;
        if (cid) { ownerVoice = { guild_id: g.id, channel_id: cid }; break; }
      }
    }
    return { app, owner, ownerVoice };
  }

  function wireReconnect(conn) {
    conn.on('stateChange', (o, n) => log(`conn state ${o.status} -> ${n.status}`));
    conn.on('error', (e) => log(`conn error: ${e.message}`));
    conn.on(VoiceConnectionStatus.Disconnected, async () => {
      try {
        await Promise.race([
          entersState(conn, VoiceConnectionStatus.Signalling, 5000),
          entersState(conn, VoiceConnectionStatus.Connecting, 5000),
        ]);
      } catch {
        for (let attempt = 1; attempt <= 3 && !stopping; attempt++) {
          out('reconnecting', { attempt });
          try {
            conn.rejoin();
            await entersState(conn, VoiceConnectionStatus.Ready, 5000);
            out('rejoined');
            return;
          } catch { await new Promise((r) => setTimeout(r, 5000)); }
        }
        if (stopping) return;
        out('error', { code: 'voice_lost', message: 'Lost the voice connection and could not rejoin.' });
        stop('voice_lost');
      }
    });
  }

  async function onReady() {
    log('logged in');
    out('ready', { bot: { id: client.user.id, name: client.user.username } });
    let inv;
    try {
      inv = await fetchInventory();
    } catch (e) {
      return fail('login_failed', `Could not read bot information: ${e.message}`);
    }

    if (args.mode === 'list') {
      const guilds = [...client.guilds.cache.values()].map((g) => ({
        id: g.id,
        name: g.name,
        voice_channels: [...g.channels.cache
          .filter((c) => c.isVoiceBased() && c.type !== ChannelType.GuildStageVoice)
          .values()].map((c) => ({ id: c.id, name: c.name })),
      }));
      out('inventory', { guilds, owner: inv.owner, owner_voice: inv.ownerVoice, application_id: client.application.id });
      try { await client.destroy(); } catch { /* ignore */ }
      return exitNow(0);
    }

    // --record
    const channelId = args.channel ?? inv.ownerVoice?.channel_id ?? null;
    if (!channelId) {
      return fail('owner_not_in_voice', 'No channel given and the bot owner is not in a voice channel.', 2);
    }
    try {
      channel = await client.channels.fetch(channelId);
      if (!channel || !channel.guild || !channel.isVoiceBased()) throw new Error('not a voice channel');
    } catch (e) {
      channel = null;
      return fail('channel_not_found', `Could not open voice channel ${channelId}: ${e.message}`);
    }
    const guild = channel.guild;
    connection = joinVoiceChannel({
      channelId, guildId: guild.id, adapterCreator: guild.voiceAdapterCreator, selfDeaf: false, selfMute: true,
    });
    wireReconnect(connection);
    try {
      await entersState(connection, VoiceConnectionStatus.Ready, 30000);
    } catch {
      try { connection.destroy(); } catch { /* ignore */ }
      return fail('join_timeout', 'Timed out joining the voice channel.');
    }
    log('connection Ready');
    out('joined', { guild_id: guild.id, guild_name: guild.name, channel_id: channel.id, channel_name: channel.name });
    recordStart = Date.now();
    if (args.notice) {
      try { await channel.send(args.notice); out('notice_posted'); }
      catch (e) { log(`notice post failed: ${e.message}`); }
    }

    const receiver = connection.receiver;
    receiver.speaking.on('start', (userId) => {
      if (stopping) return;
      const now = Date.now();
      if (now - (lastSpeaking.get(userId) ?? 0) >= 1000) {
        lastSpeaking.set(userId, now);
        out('speaking', { id: userId });
      }
      const t = tracks.get(userId);
      if (!t) startTrack(receiver, guild, userId);
      else if (!receiver.subscriptions.has(userId)) {
        log(`resubscribe ${userId}`);
        attach(receiver, userId, t);
      }
    });

    telemetryTimer = setInterval(() => {
      const users = {};
      for (const [id, t] of tracks) users[id] = { seconds: Math.round((t.written / RATE) * 10) / 10, packets: t.packets };
      out('telemetry', {
        elapsed_s: Math.round((Date.now() - recordStart) / 1000),
        rss_mb: Math.round((process.memoryUsage().rss / 1048576) * 10) / 10,
        users,
        decode_errors: decodeErrors,
      });
    }, 10000);
  }

  process.on('SIGINT', () => stop('SIGINT'));
  process.on('SIGTERM', () => stop('SIGTERM'));
  if (args.mode === 'record') watchStdin();

  client.once('clientReady', () => {
    onReady().catch((e) => { log(`FATAL ${e.stack || e}`); fail('login_failed', e.message); });
  });
  client.login(TOKEN).catch((e) => {
    log(`login failed: ${e.message}`);
    fail('login_failed', 'Discord rejected the bot token or could not be reached.');
  });
}
