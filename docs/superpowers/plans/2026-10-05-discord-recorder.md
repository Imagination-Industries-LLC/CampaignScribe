# Discord Live Recorder (Phase 4b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record a live Discord voice session from inside CampaignScribe as one track per person, through a bundled Node.js recorder helper, then hand the tracks to Phase 4a's "One file per speaker" transcription.

**Architecture:**
- A committed Node.js project, `recorder/`, holds the spike recorder, hardened with a stdin/stdout JSON protocol, `--list` and `--record` modes, reconnect, and owner auto-join.
- A Tk-free `app/core/discord_recorder.py` launches and talks to it, and converts the per-user PCM to WAV.
- The UI parts are:
  - a Settings "Discord recording" section, including the maximum recording length;
  - a non-modal record dialog opened from the session window;
  - app-level quit and crash-recovery prompts.
- The Node runtime is fetched at build time with a pinned SHA-256 and bundled by PyInstaller.

**Tech Stack:** Python 3.11, Tkinter/ttk, pytest, Node.js 24 (`node --test`), discord.js 14, @discordjs/voice 0.19, @snazzah/davey, opusscript, prism-media, libsodium-wrappers, ffmpeg (bundled).

**Spec:** `docs/superpowers/specs/2026-10-05-discord-recorder-design.md`

## Global Constraints

**Commands and commits:**
- Run Python through `.venv\Scripts\python`. The shell is PowerShell 5.1: no `&&`; use `; if ($?) { ... }`.
- Commit messages are single-line, with no `Co-Authored-By` trailer and no AI attribution of any kind.
- Never commit `CampaignScribe.spec` changes made by a build. If it shows as modified after a build, run `git checkout -- CampaignScribe.spec`. Task 2 is the exception: it edits that file on purpose and commits it.

**Code rules:**
- Every Python subprocess uses `creationflags=subprocess.CREATE_NO_WINDOW`, including tests that launch processes. In tests, pass the flag only when `sys.platform == "win32"`.
- **The Discord bot token must never be printed, logged, written to a file, or passed on a command line.** It travels only in the child's environment (`DISCORD_TOKEN`) and is stored only in keyring, as service `CampaignScribe` and username `discord_bot_token`.
- Never touch the keyring entry ("CampaignScribe", "huggingface_token").
- The word "MeetingScribe" must not appear anywhere.

**Full gate before each task's commit:**
- `.venv\Scripts\python -m pytest -q`
- `.venv\Scripts\python -m ruff check app tests scripts`
- `.venv\Scripts\python -m ruff format app tests scripts`
- `.venv\Scripts\python -m bandit -q -r app -ll`
- For tasks touching `recorder/`, also `vendor\node\node.exe --test recorder\test`, or `node --test recorder\test` when `vendor\node` is not fetched yet.

**CI facts:**
- The ubuntu job runs `pytest -m "not gui"` with only `requirements-dev.txt` installed. It has no numpy, torch, whisperx, pyannote, Node or network. Every non-gui test must pass on Linux, with platform-neutral paths, and must not need those packages.
- GUI tests (marked `gui`) run on windows-latest only.
- `tests/gui/conftest.py` and `tests/smoke/conftest.py` contain an autouse guard that **fails any unpatched** `messagebox` / `simpledialog` / `filedialog` call. Patch every dialog a test reaches.
- Unattended Tk dialogs auto-dismiss after about 2 s on the dev PC, so a test can pass locally and still hang CI. Trust the guard.

**Spec values (verbatim):**
- `INVITE_PERMISSIONS = 1051648`.
- Config defaults:
  - `discord_notice` = `🔴 This voice channel is being recorded by CampaignScribe for session notes.`
  - `discord_max_minutes` = `360`
  - `discord_last_guild` = `""`, `discord_last_channel` = `""`, `recordings_folder` = `""`
- Recording folder: `<recordings root>/session_<id>_<YYYYmmdd_HHMMSS>/`.
- Recordings root: `recordings_folder` if set, else `<default_output_folder>/recordings` when that is set, else `<app data dir>/recordings`.
- Track WAV name: `<DisplayName>_<userId>.wav`, 16 kHz mono. Characters invalid on Windows (`<>:"/\|?*` and control characters) become `_`, and the result is stripped. If that leaves it empty, use `user`.
- Stop message: `⏹️ Recording stopped.`
- UI strings:
  - Settings section header: `— Discord recording —`
  - Settings controls: `Bot token:`, `Invite bot`, `Test connection`, `How to set up a bot…`, `Recording notice:`, `Max recording length (auto-stop):`
  - Max-length validation: `Max recording length must be at least 1 minute.`
  - Session window button: `🔴 Record from Discord`
  - Missing-token message: `Set up the Discord bot in Settings (⚙) first.`
  - Consent text: `Everyone in the voice channel will be recorded. You are responsible for telling participants and getting their consent where the law requires it. The bot will post this notice in the channel:`, followed by a blank line and the notice.
  - Consent buttons: `Start recording` / `Cancel`
  - Recorder Stop button: `Stop recording`
- Auto-stop line formats:
  - normal: `⏱ Auto-stop at H:MM — in H:MM:SS`
  - last 5 minutes: `⏱ Auto-stop in M:SS`
  - suspended: `⏱ Past the maximum length — auto-stop is off until you set a longer limit`
  - tooltip: `Change the maximum recording length`
  - after an auto-stop: `Stopped automatically at the maximum recording length.`
- Limit-passed prompt:
  - title: `Maximum length already reached`
  - body: `The new maximum (H:MM) is shorter than this recording (H:MM:SS). Stop recording now?`
- Quit prompt: `A Discord recording is running. Stop it and quit?`
- Recovery prompt: `Finish converting N interrupted recording(s)?`, with N being the number.
- Low disk: warn below 2 GB free on the recordings drive.

**Controller rulings:**
- **Pinned Node runtime:** `node-v24.21.0-win-x64.zip`, SHA-256 `158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541`, taken from https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt on 2026-10-05. The spike's v24.15.0 did the same job, and v24.21.0 is the same major line.
- **Focus, not scroll:** `SettingsDialog` is a plain gridded `Toplevel`, not a scrollable one. "Scroll to and focus" is implemented as raising the dialog and focusing the max-length hours spinbox.
- **Exact npm pins:** `recorder/package.json` pins exact versions, with no `^`. They are discord.js 14.27.0, @discordjs/voice 0.19.2, @snazzah/davey 0.1.12, libsodium-wrappers 0.8.4, opusscript 0.0.8 and prism-media 1.3.5. A committed `package-lock.json` pins the transitive dependencies.

## Review Focus

1. **The recorder outliving its parent.** If CampaignScribe is killed, the recorder must notice stdin EOF and stop cleanly, leaving finished `.pcm` files. Task 1 pins this with a node test; Task 3 pins EOF handling with the fake recorder.
2. **The token leaking.** The token must never appear in command lines, logs, `recorder.log`, `tracks.json`, error messages or exception text. Tasks 1 and 3 pin this. Grep the outputs in tests for the fake token string.
3. **Auto-stop arithmetic and edge cases.** The limit can change mid-recording, can drop below the elapsed time, can suspend and then re-arm, and the warning window applies. The dialog clock is injected. Task 5 pins all of these.
4. **A display name that is empty, duplicated, or full of `\/:*?"<>|`.** WAV names must stay unique, which the user id guarantees, and valid on Windows. Tasks 1 and 3 pin this.
5. **Stopping while finalize is still converting.** A second Stop click, a closed window, or quitting the app must not start a second finalize or lose tracks. Task 5 pins the double-stop case; Task 6 pins quitting mid-finalize.

---

### Task 1: Node recorder project (`recorder/`)

**Files:**
- Create: `recorder/package.json`, `recorder/package-lock.json`, `recorder/lib.mjs`, `recorder/recorder.mjs`, `recorder/test/lib.test.mjs`, `recorder/test/protocol.test.mjs`, `recorder/README.md`
- Modify: `.gitignore`, adding `/recorder/node_modules/` and `/vendor/`.
- Reference only, not committed: the spike recorder at `C:\Users\admin\AppData\Local\Temp\claude\h--ProtonDrive-mrompel-My-files-Audio-Transcription-CampaignScribe-CampaignScribe-Build-folder\d0ed75ce-3229-455e-be7b-9bd6c3cc6f68\scratchpad\spike4b\recorder\recorder.mjs`. It is proven in a 60-minute soak. Keep its capture logic.

**Interfaces:**
- Produces the CLI protocol that Task 3 relies on.
  - `node recorder.mjs --list` prints one inventory JSON line and exits 0. On a failure it prints one `error` line and exits 1.
  - `node recorder.mjs --record --out <dir> --notice <text> [--channel <id>]` streams events. Exit codes:
    - 0 after `stopped`;
    - 2 on `owner_not_in_voice`;
    - 1 on fatal errors.
- **Every stdout line is one JSON object** with an `event` key:
  - `ready` with `{bot:{id,name}}`
  - `inventory` with `{guilds:[{id,name,voice_channels:[{id,name}]}], owner:{id,name}|null, owner_voice:{guild_id,channel_id}|null, application_id}`
  - `joined` with `{guild_id, guild_name, channel_id, channel_name}`
  - `notice_posted`
  - `user` with `{id, name}`
  - `speaking` with `{id}`, at most once per user per second
  - `telemetry` with `{elapsed_s, rss_mb, users:{<id>:{seconds, packets}}, decode_errors}`, every 10 s
  - `reconnecting` with `{attempt}`
  - `rejoined`
  - `error` with `{code, message}`
  - `stopped` with `{seconds}`
- **Error codes:** `login_failed`, `no_token`, `channel_not_found`, `owner_not_in_voice`, `join_timeout`, `voice_lost`, `bad_args`.
- **stdin** takes one JSON object per line. `{"cmd":"stop"}` stops the recording, and EOF on stdin also stops it.
- **Files written to `--out`:**
  - `<userId>.pcm`: s16le, 48 kHz, mono;
  - `tracks.json`: `{userId: displayName}`, rewritten when a user is first seen and again when their name resolves;
  - `recorder.log`.

- [ ] **Step 1: Pure helpers with tests first**

`recorder/test/lib.test.mjs`, run with `node --test recorder/test`:

```js
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
  assert.equal(silenceToInsert({ elapsedMs: 1000, written: RATE - 960 - 1000, frames: 960 }), 0);
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
```

`recorder/lib.mjs`:

```js
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
```

Install the dependencies first: `cd recorder; npm install --save-exact discord.js@14.27.0 @discordjs/voice@0.19.2 @snazzah/davey@0.1.12 libsodium-wrappers@0.8.4 opusscript@0.0.8 prism-media@1.3.5`. This creates `package.json` and `package-lock.json`; also set `"type": "module"` and `"private": true`. Run `node --test test`, where `lib.test.mjs` must pass.

- [ ] **Step 2: `recorder.mjs`, the protocol and lifecycle**

Port the spike's capture logic (`startTrack` and `stop`) unchanged in behaviour, but use the helpers from `lib.mjs`.

**Paths and output:**
- Write everything into `args.out`; create it if it doesn't exist.
- Write events to stdout with `process.stdout.write(eventLine(...))`. **Never `console.log` anything else to stdout.**
- Diagnostics go to `recorder.log` in `args.out` and to stderr.
- Never write `process.env.DISCORD_TOKEN` anywhere.
- If the token is missing, emit `error` `{code:'no_token'}` and exit 1.

**Startup:**
- Create the client with intents `Guilds` and `GuildVoiceStates` only.
- On `clientReady`, emit `ready`, then call `client.application.fetch()`.
  - `owner` is `app.owner` when it is a User (has `username`), else `null`, which covers Team owners.
  - `owner_voice` is the first guild where `guild.voiceStates.cache.get(owner.id)?.channelId` is set.

**`--list` mode:**
- Emit `inventory` with:
  - the guilds;
  - their voice channels: `guild.channels.cache.filter(c => c.isVoiceBased() && c.type !== ChannelType.GuildStageVoice)`;
  - `owner`, `owner_voice`, and `application_id: client.application.id`.
- Then destroy the client and exit 0.

**`--record` mode:**
- **Choose the target channel.** The channel is `args.channel ?? owner_voice?.channel_id`. If there is none, emit `error` `{code:'owner_not_in_voice'}` and exit 2.
- **Join and announce.**
  - Fetch the channel. On failure, emit `error` `channel_not_found` and exit 1.
  - Join with `selfDeaf: false, selfMute: true`, then wait for Ready with `entersState` for 30 s. On timeout, emit `join_timeout` and exit 1.
  - Emit `joined`.
  - `recordStart = Date.now()`.
  - Send `args.notice` to `channel` if it is non-empty, then emit `notice_posted`. On a send failure, log it and carry on.
- **Capture each user.**
  - `receiver.speaking.on('start', id => ...)`: start the track on first sight and emit `user` with `{id, name: <resolved display name or id>}`. Re-emit `user` once the member fetch resolves the name.
  - Emit `speaking` `{id}`, rate-limited per user to 1 per 1000 ms.
- **Telemetry** every 10 s.
- **Reconnect**, the @discordjs/voice pattern:

```js
connection.on(VoiceConnectionStatus.Disconnected, async () => {
  try {
    await Promise.race([
      entersState(connection, VoiceConnectionStatus.Signalling, 5000),
      entersState(connection, VoiceConnectionStatus.Connecting, 5000),
    ]);
  } catch {
    for (let attempt = 1; attempt <= 3 && !stopping; attempt++) {
      out('reconnecting', { attempt });
      try {
        connection.rejoin();
        await entersState(connection, VoiceConnectionStatus.Ready, 5000);
        out('rejoined'); return;
      } catch { await new Promise((r) => setTimeout(r, 5000)); }
    }
    out('error', { code: 'voice_lost', message: 'Lost the voice connection and could not rejoin.' });
    stop('voice_lost');
  }
});
```

  The receiver keeps per-user streams across a rejoin. Subscriptions are keyed by user id, and wall-clock padding fills the gap. If `receiver.subscriptions` was cleared by the rejoin, re-subscribe on the next `speaking` start for users already in `tracks`. Keep their write stream and `written` counter, and replace only `opus` and `dec`.
- **Stop:**
  - **Triggers:** `{"cmd":"stop"}` on stdin, stdin `end` or `close` (EOF), `SIGINT`, `SIGTERM`, or `voice_lost`.
  - **Sequence:** pad every track to the same final length, `end()` every write stream, rewrite `tracks.json`, and send `⏹️ Recording stopped.`, ignoring a failure. Then destroy the connection and client, emit `stopped` `{seconds}`, and exit 0 after the log stream finishes.
  - **Idempotent:** a second trigger does nothing.
- **stdin parsing:** use `readline` on `process.stdin`. Ignore lines that aren't valid JSON or carry an unknown command; log them.

- [ ] **Step 3: Protocol tests without Discord**

`recorder/test/protocol.test.mjs` spawns `node recorder.mjs` with an **empty** `DISCORD_TOKEN` and with bad arguments, capturing stdout. It asserts:
- `--list` with no token prints exactly one line, `{"event":"error","code":"no_token",...}`, and exits 1;
- no arguments prints an `error` `bad_args` line and exits 1;
- with `DISCORD_TOKEN=FAKE.TOKEN.VALUE` and `--list`, after `login_failed` (exit 1; this needs network, so skip it with `{ skip: !process.env.CS_NET_TESTS }`), the string `FAKE.TOKEN.VALUE` appears in neither stdout, stderr nor any file.

Full stop-on-EOF behaviour needs a live login, so it is covered by Task 3's fake-recorder test and the manual acceptance. Add a comment saying so.

- [ ] **Step 4: Live check, which needs the stored bot token and network**

Write a throwaway `scratch_list.py`; do not commit it. It reads the token from keyring and runs `node recorder.mjs --list` with `DISCORD_TOKEN` set in the child environment only, using `CREATE_NO_WINDOW`. Confirm the inventory lists the MDMT server and its voice channels, and that `owner` is the account that created the bot. Paste only the event names and counts into the report, never the token.

- [ ] **Step 5: README and commit**

`recorder/README.md` gives the purpose, the protocol summary (copy it from Interfaces above), the dev commands (`npm ci`, `node --test test`) and the note that the token is only ever passed through the environment.

```
git add .gitignore recorder/package.json recorder/package-lock.json recorder/lib.mjs recorder/recorder.mjs recorder/test recorder/README.md
git commit -m "feat: Node Discord recorder helper (DAVE receive, JSON stdio protocol, owner auto-join, reconnect)"
```

---

### Task 2: Fetch and bundle the Node runtime

**Files:**
- Create: `scripts/fetch_node_runtime.py`, `tests/unit/test_fetch_node_runtime.py`
- Modify:
  - `build.bat`: after the weights fetch and before PyInstaller.
  - `setup_venv.bat`: after the weights fetch.
  - `CampaignScribe.spec` (`datas` entries).
  - `THIRD-PARTY-NOTICES.md`.
  - `tests/unit/test_packaging_lists.py`.

**Interfaces:**
- Produces `vendor/node/node.exe` and `vendor/node/npm.cmd`, with `node_modules/npm`. At runtime, Task 3 looks for `<_MEIPASS>/node/node.exe` and `<_MEIPASS>/recorder/recorder.mjs` in the frozen app.

- [ ] **Step 1: Tests first**

Mirror `tests/unit/test_fetch_weights.py`. The fetch script exposes:
- `NODE_VERSION = "24.21.0"`
- `ZIP_NAME = "node-v24.21.0-win-x64.zip"`
- `ZIP_SHA256 = "158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541"`
- `URL = f"https://nodejs.org/dist/v{NODE_VERSION}/{ZIP_NAME}"`
- `DEFAULT_DEST = <repo>/vendor/node`
- `sha256(path)`, `is_installed(dest) -> bool` (true when `node.exe` and `npm.cmd` exist and `node.exe --version` prints `v24.21.0`; that probe uses `CREATE_NO_WINDOW`), `download(url, path)`, `extract(zip_path, dest)` (flattens the zip's top folder `node-v24.21.0-win-x64/` into `dest`), and `main() -> int`.

The tests use `tmp_path`, a monkeypatched `download` that copies a small locally built zip, and a monkeypatched `ZIP_SHA256`. They check:
- the hash-mismatch path deletes the bad zip and returns 1;
- a good zip extracts with the top folder flattened;
- `main()` returns 0 without downloading when `is_installed` is true;
- a network error returns 1 with the message `Download failed:` printed.

Keep the tests Linux-safe: build the fake zip with `zipfile`, and use no `.exe` execution. Monkeypatch `is_installed` where needed.

- [ ] **Step 2: Implement `scripts/fetch_node_runtime.py`**

Follow `scripts/fetch_diarization_weights.py`'s structure and messages.
- Download with `urllib.request.urlopen`. Guard the scheme to `https` and mark the call `# nosec B310`, as the existing code does.
- Download to a `.part` file, verify the SHA-256, then extract. On a mismatch, delete the file and return 1. Print `[fetch_node_runtime] ...` messages.

- [ ] **Step 3: Wire up the builds**

**`build.bat`,** after the weights block:

```bat
echo Fetching bundled Node.js runtime...
"%PY%" scripts\fetch_node_runtime.py
if errorlevel 1 (
    echo ERROR: Node.js runtime missing or invalid; see message above.
    exit /b 1
)
echo Installing recorder dependencies...
pushd recorder
call "%ROOT%vendor\node\npm.cmd" ci --omit=dev --no-audit --no-fund
if errorlevel 1 (
    popd
    echo ERROR: npm ci for the recorder failed.
    exit /b 1
)
popd
```

Add to the PyInstaller arguments:
- `--add-data "vendor\node\node.exe;node"`
- `--add-data "recorder;recorder"`

**`setup_venv.bat`:** the same two steps, but on failure only print `[setup_venv] WARNING: ...` and continue.

**`CampaignScribe.spec`:** add the matching `datas` entries, and commit this file.

- [ ] **Step 4: Packaging tests and notices**

**`tests/unit/test_packaging_lists.py`** gains three checks:
- `build.bat` runs `fetch_node_runtime.py`, then `npm.cmd" ci --omit=dev` in recorder, both **before** the PyInstaller line, and has `errorlevel` checks for both;
- the two `--add-data` entries are present;
- `setup_venv.bat` runs the fetch.

**`THIRD-PARTY-NOTICES.md`** gains a "Discord recording" section listing each component with its license and home page:
- Node.js (MIT, with a note that the distribution includes third-party components under their own licenses, listed in Node's LICENSE);
- discord.js and @discordjs/voice (Apache-2.0);
- @snazzah/davey;
- opusscript (MIT);
- prism-media (Apache-2.0);
- libsodium-wrappers (ISC).

Before writing each license, read it from the installed `recorder/node_modules/<pkg>/package.json` `license` field. Don't guess. Extend `tests/unit/test_notices.py`'s needles with `Node.js` and `@discordjs/voice`.

- [ ] **Step 5: Run the fetch for real, then gate and commit**

Run `.venv\Scripts\python scripts\fetch_node_runtime.py`. Expect it to download about 30 MB, verify, and extract. Then:
- confirm `vendor\node\node.exe --version` prints `v24.21.0`;
- run `vendor\node\npm.cmd ci --omit=dev` in `recorder`;
- run `vendor\node\node.exe --test recorder\test`;
- run the full gate.

Do **not** run `build.bat` in this task; the controller does a packaged build at the end.

```
git add scripts/fetch_node_runtime.py tests/unit/test_fetch_node_runtime.py build.bat setup_venv.bat CampaignScribe.spec THIRD-PARTY-NOTICES.md tests/unit/test_packaging_lists.py tests/unit/test_notices.py
git commit -m "build: fetch pinned Node.js runtime and bundle the recorder"
```

---

### Task 3: `app/core/discord_recorder.py`

**Files:**
- Create: `app/core/discord_recorder.py`, `tests/unit/test_discord_recorder.py`, `tests/unit/fake_recorder.py` (a helper script, not a test)
- Modify: `app/config.py`. Add the five `DEFAULT_CONFIG` keys from Global Constraints after `"setup_welcome_shown"`. Add `get_discord_token()` and `save_discord_token(token)` next to the provider-key helpers.

**Interfaces:**
- Consumes the Task 1 protocol.
- Produces, exactly:

```python
class RecorderUnavailable(RuntimeError): ...
INVITE_PERMISSIONS = 1051648

def node_exe() -> str
def recorder_script() -> str          # path to recorder.mjs
def recordings_root(cfg: dict | None = None) -> str
def new_recording_dir(session_id: int, now: datetime | None = None, cfg: dict | None = None) -> str
def get_token() -> str                # = config.get_discord_token()
def save_token(token: str) -> None    # = config.save_discord_token()
def application_id_from_token(token: str) -> str | None
def invite_url(token: str) -> str | None
def list_inventory(timeout_s: float = 20.0) -> dict      # raises RecorderError(code, message)
class RecorderError(RuntimeError):
    def __init__(self, code: str, message: str): ...
class RecorderProcess:
    def __init__(self, out_dir: str, *, notice: str, channel_id: str | None,
                 on_event: Callable[[dict], None], cmd: list[str] | None = None) -> None
    def start(self) -> None
    def stop(self, timeout_s: float = 15.0) -> int | None   # returns exit code
    @property
    def running(self) -> bool
    @property
    def exit_code(self) -> int | None
def sanitize_name(name: str) -> str
def finalize(out_dir: str, *, ffmpeg: str | None = None) -> tuple[list[str], dict[str, str]]
    # -> (wav_paths, failures {pcm_path: error})
def unfinished_recordings(root: str) -> list[str]
def session_id_from_dir(path: str) -> int | None
```

- [ ] **Step 1: Write the fake recorder and the tests**

`tests/unit/fake_recorder.py` is a stand-alone script that speaks the protocol. Its behaviour is chosen with `FAKE_MODE` in the environment:
- `record_ok`: print `ready`, `joined`, `user` (`{"id":"1","name":"Mi/ke"}`) and `speaking`. Write `1.pcm` with 1 s of s16 silence and `tracks.json`. Wait for the stdin `stop` command or EOF, then print `stopped` and exit 0.
- `owner_absent`: print `error` `owner_not_in_voice` and exit 2.
- `hang`: ignore stdin forever. This tests kill-on-timeout.
- `list_ok`: print the `inventory` line and exit 0.
- `garbage`: print `not json`, then `ready`.

It must never print the value of `DISCORD_TOKEN`. In the record modes it writes the token to no file.

Tests in `tests/unit/test_discord_recorder.py` build `cmd=[sys.executable, <fake>]` and pass `FAKE_MODE` through a monkeypatched environment. They are Linux-safe and need no Node:
- **Events and stop:** with `RecorderProcess`, events arrive in order; `stop()` returns 0 and leaves `running` False.
- **EOF:** with `record_ok`, closing the parent's stdin pipe (the `_close_stdin()` helper) makes the fake exit 0 by itself.
- **Kill on timeout:** in `hang` mode, `stop(timeout_s=1)` kills the process and returns a non-zero or None exit code within 3 s.
- **Unreadable lines:** `garbage` delivers only `ready` to `on_event`.
- **Token never leaks:** set `DISCORD_TOKEN=SECRET123` through `config.save_discord_token`, which uses the in-memory keyring. Assert that `SECRET123` appears in no `cmd` argument (inspect `proc.args`), no event, and no file in `out_dir`.
- **Application id:** `application_id_from_token` decodes the first segment, base64url without padding, into its digits. Malformed input returns None. `invite_url` contains `client_id=<id>`, `scope=bot` and `permissions=1051648`, and returns None for a bad token.
- **Inventory:** `list_inventory` with the fake in `list_ok` mode returns the dict. A fake returning `error` raises `RecorderError` with the code.
- **Name sanitising:** `sanitize_name` matches the Task 1 table.
- **`finalize`:**
  - It writes 2 s of a 48 kHz s16 mono `.pcm` for user `1` with `tracks.json {"1":"Mi/ke"}`, runs ffmpeg, and produces `Mi_ke_1.wav`, 16 kHz mono and 2.0 s long (read it with `wave`), and deletes the `.pcm`.
  - A `.pcm` with no name falls back to the id.
  - A conversion failure keeps the `.pcm` and records the failure.
  - **ffmpeg:** use `audio.get_ffmpeg_path()`. The bundled `ffmpeg\ffmpeg.exe` exists on Windows dev and CI-Windows, but not on ubuntu, where the test must `pytest.skip` when `shutil.which("ffmpeg")` is None and no bundled binary exists.
- **Recovery:** `unfinished_recordings` finds only folders containing `.pcm` files. `session_id_from_dir("…/session_12_20261005_101010")` returns 12, and any other name returns None.
- **Paths:** `recordings_root` follows the precedence in Global Constraints. `new_recording_dir` returns `<root>/session_<id>_<ts>` and creates it.
- **`node_exe` and `recorder_script` resolution:**
  - frozen, with `sys._MEIPASS` set to tmp: returns `<tmp>/node/node.exe`;
  - dev, with `vendor/node/node.exe` present (create it in a tmp repo root via a monkeypatched `_repo_root()`): returns that path;
  - dev fallback: `shutil.which("node")`;
  - nothing found: `RecorderUnavailable` with "Reinstall CampaignScribe, or in a development checkout run: python scripts/fetch_node_runtime.py".

- [ ] **Step 2: Implement**

**`RecorderProcess.start`:**
- **Command:** `cmd or [node_exe(), recorder_script(), "--record", "--out", out_dir, "--notice", notice] (+ ["--channel", channel_id])`.
- **Environment:** `dict(os.environ, DISCORD_TOKEN=get_token())`. Raise `RecorderError("no_token", ...)` when the token is empty, unless a test `cmd` is supplied.
- **Process:** `Popen` with `stdin=PIPE`, `stdout=PIPE`, `stderr=PIPE`, `text=True`, `encoding="utf-8"`, `bufsize=1`, and `creationflags=CREATE_NO_WINDOW` on Windows.
- **Reader threads:** a daemon reader thread parses each stdout line with `json.loads` and calls `on_event(dict)` for dicts that have `"event"`. Other lines are ignored and logged through `config.log_exception` only when they are actual exceptions. A second daemon thread drains stderr into a list capped at 200 lines, for the report.

**`stop()`:**
- Write `{"cmd":"stop"}\n`, flush, close stdin, then `wait(timeout)`.
- On a timeout, call `kill()`, then wait. Join the reader thread.
- Calling `stop()` again is a no-op that returns the cached exit code.

**`list_inventory`:** runs `--list` with the same environment and `CREATE_NO_WINDOW`, capturing output with a timeout. It returns the `inventory` event, or raises `RecorderError(code, message)` from the `error` event. On a timeout or no output it raises `RecorderError("timeout", ...)`.

**`finalize`:** for each `*.pcm`, run ffmpeg with `-f s16le -ar 48000 -ac 1 -i <pcm> -ar 16000 -ac 1 <name>_<id>.wav -y` through `subprocess.run(..., creationflags=CREATE_NO_WINDOW, capture_output=True, check=False)`. Delete the `.pcm` on success only. Read the names from `tracks.json`, falling back to the id.

- [ ] **Step 3: Run tests, gate, commit**

```
git add app/core/discord_recorder.py app/config.py tests/unit/test_discord_recorder.py tests/unit/fake_recorder.py
git commit -m "feat: discord_recorder core (process protocol, token, invite, finalize, recovery helpers)"
```

---

### Task 4: Settings → Discord recording (including max length)

**Files:**
- Modify: `app/ui/settings_dialog.py`
  - Build the new section between Privacy and the Save/Cancel `btn_frame`, around lines 120-150.
  - Extend `__init__`'s signature and `_save` (around line 511).
- Modify: `app/ui/app_window.py`, `open_settings` (around line 390).
- Test: `tests/gui/test_settings_discord.py`

**Interfaces:**
- Consumes from Task 3: `discord_recorder.get_token`, `save_token`, `invite_url` and `list_inventory`, plus the config keys.
- Produces:
  - `SettingsDialog(master, initial_provider=None, focus=None)`.
  - `AppWindow.open_settings(initial_provider=None, focus=None)`.
  - Widgets: `dlg.discord_token_var`, `dlg.discord_invite_btn`, `dlg.discord_test_btn`, `dlg.discord_test_label`, `dlg.discord_notice_var`, `dlg.discord_max_hours_var` and `dlg.discord_max_minutes_var` (both `tk.IntVar`), and `dlg.discord_max_hours_spin`.

- [ ] **Step 1: Tests first**

Use the `root` fixture pattern from `tests/gui/test_settings_initial_provider.py`.

```python
def test_discord_defaults(root):
    dlg = SettingsDialog(root); dlg.update_idletasks()
    try:
        assert dlg.discord_token_var.get() == ""
        assert str(dlg.discord_invite_btn["state"]) == "disabled"
        assert dlg.discord_max_hours_var.get() == 6 and dlg.discord_max_minutes_var.get() == 0
        assert dlg.discord_notice_var.get().startswith("🔴 This voice channel is being recorded")
    finally:
        dlg.destroy()


def test_invite_enables_with_token_and_opens_url(root, monkeypatch):
    opened = []
    monkeypatch.setattr("app.ui.settings_dialog.open_url", lambda u: opened.append(u))
    dlg = SettingsDialog(root)
    try:
        dlg.discord_token_var.set("MTIzNDU2Nzg5MDEyMzQ1Njc4.x.y")  # base64url("123456789012345678")
        dlg.update_idletasks()
        assert str(dlg.discord_invite_btn["state"]) == "normal"
        dlg.discord_invite_btn.invoke()
        assert "client_id=123456789012345678" in opened[0] and "permissions=1051648" in opened[0]
    finally:
        dlg.destroy()


def test_save_persists_token_notice_and_max(root):
    dlg = SettingsDialog(root)
    dlg.discord_token_var.set("tok"); dlg.discord_notice_var.set("Recording!")
    dlg.discord_max_hours_var.set(2); dlg.discord_max_minutes_var.set(30)
    dlg._save()
    assert config.get_discord_token() == "tok"
    cfg = config.load_config()
    assert cfg["discord_notice"] == "Recording!" and cfg["discord_max_minutes"] == 150


def test_save_rejects_zero_max(root, monkeypatch):
    errors = []
    monkeypatch.setattr("app.ui.settings_dialog.messagebox.showerror", lambda t, m, **k: errors.append(m))
    dlg = SettingsDialog(root)
    try:
        dlg.discord_max_hours_var.set(0); dlg.discord_max_minutes_var.set(0)
        dlg._save()
        assert errors == ["Max recording length must be at least 1 minute."]
        assert config.load_config()["discord_max_minutes"] == 360
    finally:
        if dlg.winfo_exists():
            dlg.destroy()


def test_focus_max_length(root):
    dlg = SettingsDialog(root, focus="discord_max_length"); dlg.update()
    try:
        assert dlg.focus_get() is dlg.discord_max_hours_spin
    finally:
        dlg.destroy()


def test_connection_test_reports_inventory(root, monkeypatch):
    monkeypatch.setattr("app.core.discord_recorder.list_inventory", lambda timeout_s=20.0: {
        "event": "inventory", "guilds": [{"id": "1", "name": "MDMT", "voice_channels": [{"id": "2", "name": "Table"}]}],
        "owner": {"id": "9", "name": "Mike"}, "owner_voice": None, "application_id": "5"})
    dlg = SettingsDialog(root)
    try:
        dlg.discord_token_var.set("tok")
        dlg._test_discord(_sync=True)
        assert dlg.discord_test_label.cget("text").startswith("✓ Connected — 1 server")
    finally:
        dlg.destroy()
```

Also add:
- a test that a `RecorderError` from `list_inventory` shows `✗ <message>`;
- a test that `How to set up a bot…` opens a Toplevel whose text contains "Public Bot" and "Reset Token". Destroy it in the test, and never call `wait_window`.
- a test that `AppWindow.open_settings(focus="discord_max_length")` passes `focus` through to a fake `SettingsDialog`, using the `_FakeSettings` pattern from `tests/gui/test_banner_settings_button.py`.

Unsaved token handling: when the token entry differs from the saved token, Test connection temporarily uses the typed value. Monkeypatch `discord_recorder.get_token` inside `_test_discord`, or pass the token through a `token=` parameter on `list_inventory`. Choose one, document it in the report, and give `list_inventory(timeout_s=20.0, token: str | None = None)` a `token` override if you choose the parameter. Update Task 3's interface note in your report.

- [ ] **Step 2: Implement**

**The section** has, in order:
- the header `— Discord recording —`;
- `Bot token:`, an Entry with `show="•"`, then `Invite bot`, which is enabled only when the trimmed token is non-empty and `invite_url` returns non-None, through a `trace_add` on `discord_token_var`;
- `Test connection` with `discord_test_label`. It runs a worker thread and posts the result via `after`; the `_sync=True` path runs inline for tests;
- `How to set up a bot…`;
- `Recording notice:`, an Entry;
- `Max recording length (auto-stop):`, two `ttk.Spinbox` widgets for hours (0–999) and minutes (0–59), with `h` and `min` labels.

**Saving.** `_save` validates the max length **before** writing anything. When `hours*60+minutes < 1`, it shows the exact error and returns, so nothing is saved and the dialog stays open. On success it:
- calls `save_token` only when the value changed;
- writes `cfg["discord_notice"]` and `cfg["discord_max_minutes"]`.

**`focus="discord_max_length"`:** after the build, call `self.after_idle(lambda: (self.lift(), self.discord_max_hours_spin.focus_set()))`.

**`AppWindow.open_settings(initial_provider=None, focus=None)`** passes both through to the dialog.

- [ ] **Step 3: Tests, gate, commit**

```
git add app/ui/settings_dialog.py app/ui/app_window.py tests/gui/test_settings_discord.py
git commit -m "feat: Settings Discord recording section (token, invite, test, notice, max length)"
```

---

### Task 5: Record dialog + session window button + Transcribe hand-off

**Files:**
- Create: `app/core/autostop.py` (Tk-free), `tests/unit/test_autostop.py`, `app/ui/discord_record_dialog.py`, `tests/gui/test_discord_record_dialog.py`
- Modify:
  - `app/ui/session_view.py`: add the button next to `＋ add track` (around line 59), plus a helper `attach_audio(paths)` that reuses `_add_track`'s update logic.
  - `app/ui/transcribe_tab.py`: `load_for_session` honours `run_params.get("mode") == "tracks"`.
  - `app/ui/app_window.py`: a single-instance registry `self.discord_recorder_dialog`.

**Interfaces:**
- Consumes:
  - Task 3: `RecorderProcess`, `RecorderError`, `list_inventory`, `finalize`, `new_recording_dir` and `get_token`.
  - Task 4: `app.open_settings(focus="discord_max_length")`.
  - Phase 4a: `TranscribeTab._apply_mode()` and `mode_var`.
- Produces:
  - `DiscordRecordDialog(master, app, session_id, *, now=time.monotonic, recorder_factory=RecorderProcess)`.
  - `DiscordRecordDialog.stop(reason="user")`, which is idempotent.
  - `dlg.state`, one of `"consent" | "picker" | "starting" | "recording" | "stopping" | "done" | "error"`.
  - Pure helper `autostop_text(elapsed_s: float, limit_min: int) -> tuple[str, str]`, returning `(text, style)` where style is one of `"normal" | "warn" | "error"`.
  - `AppWindow.discord_recorder_dialog`, which is the dialog or None.

- [ ] **Step 1: Write the pure-helper tests**

These go in `tests/unit/test_autostop.py`, which is not gui-marked, so they run on Linux CI. `autostop_text` lives in the Tk-free `app/core/autostop.py`, and the dialog imports it from there.

```python
@pytest.mark.parametrize("elapsed, limit, text, style", [
    (0, 360, "⏱ Auto-stop at 6:00 — in 6:00:00", "normal"),
    (3600 + 59, 90, "⏱ Auto-stop at 1:30 — in 0:29:01", "normal"),
    (360 * 60 - 299, 360, "⏱ Auto-stop in 4:59", "warn"),
    (360 * 60, 360, "⏱ Past the maximum length — auto-stop is off until you set a longer limit", "error"),
])
def test_autostop_text(elapsed, limit, text, style):
    assert autostop.autostop_text(elapsed, limit) == (text, style)
```

The boundary: `remaining <= 300` seconds gives `warn`, and `remaining <= 0` gives `error`. The dialog only shows the `error` text while suspended. When the limit is reached it auto-stops instead.

- [ ] **Step 2: Write the GUI tests**

Use a **fake recorder factory** that records its constructor arguments and exposes `emit(event)` to drive `on_event`. `start()` and `stop()` record their calls, and `stop()` emits `stopped`. A **fake clock** is a list cell returned by `now`. Patch `discord_recorder.finalize` to return `(["…/Mike_1.wav"], {})`, `messagebox.askyesno`, `get_token` (returning "tok"), and `app.open_settings` and `app.open_session_stage` with recorders. Call `dlg._tick()` directly instead of waiting for `after`. Tests:
- **Consent:** construction shows consent containing the notice. `Cancel` destroys the dialog, and the factory is never called.
- **Owner auto-join:** `Start recording` constructs the recorder with `channel_id=None` and the notice from config. `state` becomes `starting`, then `recording` after `emit({"event":"joined",...})`.
- **Picker fallback:** the recorder's `error` `owner_not_in_voice` (exit 2) moves `state` to `picker`. The combobox is filled from a patched `list_inventory`, and `discord_last_guild` and `discord_last_channel` are preselected. Start then constructs the recorder with `channel_id="2"` and saves the `discord_last_*` keys.
- **Per-person rows:** `user` and `speaking` events add a person row with its name, and the dot is lit. After the fake clock advances 2 s and a tick, the dot is unlit.
- **Auto-stop line:** with config `discord_max_minutes=1` and the clock at 30 s, a tick shows `⏱ Auto-stop in 0:30` in the warn style.
  - At 60 s, a tick calls `stop(reason="max_length")`. The status reads `Stopped automatically at the maximum recording length.`; finalize is called once; the WAVs are attached to the session (assert `db.get_session(sid)["source_audio_files"]`); and `open_session_stage(sid, "transcribe", run_params={"mode": "tracks"})` is called.
- **Mid-recording changes:** set `discord_max_minutes` from 1 to 120 while recording, and the next tick shows `Auto-stop at 2:00`.
- **Limit already passed:** with the clock at 30 min, set the limit to 10 and tick.
  - The `askyesno` titled `Maximum length already reached` is called once.
  - Answering **No** keeps recording and shows the suspended text in the error style. Later ticks don't ask again.
  - Raising the limit to 60 re-arms it, so the normal text returns. At 60 min it auto-stops.
  - A separate test answers **Yes**, which stops.
- **The link:** clicking the auto-stop label, with `event_generate("<Button-1>")` or a direct call to its handler, calls `app.open_settings(focus="discord_max_length")`.
- **Double stop:** calling `stop()` twice, or clicking `Stop recording` after an auto-stop, runs finalize exactly once (Review Focus 5).
- **Recorder error:** `error` `voice_lost` plus exit shows the message, finalizes, and attaches, but does **not** call `open_session_stage`.
- **Session window button:** with no token, clicking it shows `Set up the Discord bot in Settings (⚙) first.` through a patched `askyesno` offering to open Settings. With a token, it opens the dialog. When `app.discord_recorder_dialog` already exists and is alive, it is lifted instead of a second one opening.
- **Transcribe hand-off:** `TranscribeTab.load_for_session(session, run_params={"mode": "tracks"})` sets `mode_var` to `"tracks"` and the track table shows names from the WAV file names.

- [ ] **Step 3: Implement**

**The dialog:**
- It is a `tk.Toplevel`, transient to the app, and **not grab-set**. It sets `protocol("WM_DELETE_WINDOW", ...)`: while recording, that asks to stop through the same `stop()`; otherwise it closes.
- **Event marshalling:** `on_event` runs on the reader thread, so it calls `self.after(0, self._handle, ev)`, and all UI changes happen in `_handle`.
- **The tick** is `self.after(1000, self._tick)` while recording. It:
  - updates elapsed, which is `now() - started_at`, where `started_at` is set on `joined`;
  - updates the dots and the per-person minutes from telemetry;
  - shows free disk space, via `shutil.disk_usage(out_dir).free`, with a warning label below 2 GB;
  - shows the auto-stop line;
  - checks the limit.
- **Limit checks:** keep `self._suspended_for_limit: int | None`, the limit value that was declined. Re-read `config.load_config()["discord_max_minutes"]` each tick.
  - If the limit is greater than elapsed, clear the suspension.
  - If the limit is at or below elapsed and the limit changed since the last tick to a value that is not the declined one, ask the question.
  - If the limit is at or below elapsed and unchanged since recording passed it naturally, auto-stop.

  Track `self._last_limit` to tell "the limit was lowered" apart from "time ran out".
- **`stop(reason)`:** idempotent, guarded by `self._stopping`. It:
  - sets `state="stopping"`;
  - calls `recorder.stop()` in a worker thread, then `finalize(out_dir)`;
  - then on the UI thread, attaches the WAVs to the session through `db` (append to `source_audio_files` JSON) and refreshes any open `SessionView`'s `audio_box` through `app`, if it is reachable;
  - for `reason in {"user","max_length"}`, destroys the dialog and calls `app.open_session_stage(session_id, "transcribe", run_params={"mode": "tracks"})`;
  - for errors, stays open in `state="error"` and shows the message and the folder path.
- **Output folder:** `new_recording_dir(session_id)`.
- **On start:** `app.discord_recorder_dialog = self`. On destroy, set it back to None.

**`load_for_session`:** after the existing logic, if `run_params and run_params.get("mode") == "tracks"`, set `mode_var` to `"tracks"` and call `_apply_mode()`. The track table is rebuilt from `audio_files` by Phase 4a's `_set_audio_files`, so names come from `name_from_filename`.

- [ ] **Step 4: Tests, gate, commit**

```
git add app/core/autostop.py tests/unit/test_autostop.py app/ui/discord_record_dialog.py app/ui/session_view.py app/ui/transcribe_tab.py app/ui/app_window.py tests/gui/test_discord_record_dialog.py
git commit -m "feat: Discord record dialog (consent, owner auto-join, picker, live panel, max-length auto-stop) and session hand-off"
```

---

### Task 6: App-level safety, recovery, privacy

**Files:**
- Modify:
  - `app/ui/app_window.py`: `_on_close` (around line 641); `_run_startup_prompts` (around line 346) gains a third step, `_maybe_recover_recordings`.
  - `PRIVACY.md`.
  - `tests/unit/test_packaging_lists.py` or `tests/unit/test_privacy*.py`, whichever holds the privacy text checks.
- Test: `tests/gui/test_discord_safety.py`

**Interfaces:**
- Consumes: `AppWindow.discord_recorder_dialog` and `DiscordRecordDialog.stop()` from Task 5; `discord_recorder.unfinished_recordings`, `finalize`, `session_id_from_dir` and `recordings_root` from Task 3.

- [ ] **Step 1: Tests first**

**Quitting while recording:**
- With a fake live dialog (`state == "recording"`), `_on_close` asks `A Discord recording is running. Stop it and quit?`.
- **No** keeps the app open, and `stop` is not called.
- **Yes** calls `stop(reason="quit")`, then closes once the dialog reports done. Use a fake dialog whose `stop` sets `state="done"` synchronously; the real dialog finalizes in a worker thread, so `_on_close` polls the state with `after(200)`, at most 120 s, before destroying.
- With no dialog, or `state == "done"`, there is no prompt (Review Focus 5).

**Recovery:**
- With two `session_<id>_<ts>` folders holding `.pcm` files under a temp recordings root (`recordings_folder` set in config), `_maybe_recover_recordings` asks `Finish converting 2 interrupted recording(s)?`.
- **Yes** calls a patched `finalize` for each. WAVs whose session exists in the DB are attached; the folder for a session that no longer exists is reported in a `showinfo`.
- **No** does nothing.
- With no folders, there is no prompt.
- An exception inside it is logged and does not block startup. The existing `_run_startup_prompts` already guarantees this; assert that the step is in the tuple.

**Privacy:** PRIVACY.md contains a `## Discord recording` heading and the phrases `Discord's servers`, `Windows Credential Manager` and `recordings folder`.

- [ ] **Step 2: Implement**

**`_on_close`:** check `getattr(self, "discord_recorder_dialog", None)`. If it is alive and its `state` is `starting`, `recording` or `stopping`, ask. On Yes, call `stop(reason="quit")` and poll as described. On No, return without closing.

**`_maybe_recover_recordings`:** for each unfinished folder, run `finalize`, then attach the WAVs to `session_id_from_dir(folder)` when that session exists. Collect the folders that couldn't be attached and show them in one `showinfo` at the end.

**PRIVACY.md section:**
- Audio travels through Discord's servers, as in any Discord call.
- CampaignScribe's own bot receives it on this PC and stores it only in the recordings folder.
- The bot token is stored in Windows Credential Manager and is sent only to Discord.
- Nothing is uploaded by CampaignScribe.
- The bot posts a notice in the channel.
- The user is responsible for consent.

- [ ] **Step 3: CI-condition run, gate, commit**

Run the full suite as CI sees it, with the weights folder moved aside and the ML packages and **numpy** hidden. Restore the folder afterwards, even on failure:

```powershell
Rename-Item models models.ci-hidden
try { .venv\Scripts\python -c "import sys, pytest; [sys.modules.__setitem__(m, None) for m in ('whisperx','pyannote','torch','torchaudio','huggingface_hub','numpy')]; sys.exit(pytest.main(['-q','-p','no:cacheprovider','tests']))" } finally { Rename-Item models.ci-hidden models }
```

Expected: everything passes, with skips only for tests that genuinely need numpy, pyannote or ffmpeg. Nothing hangs.

```
git add app/ui/app_window.py PRIVACY.md tests/gui/test_discord_safety.py tests/unit/<privacy test file>
git commit -m "feat: stop-and-quit prompt, interrupted-recording recovery, privacy statement for Discord recording"
```

---

## Manual acceptance (controller with Mike, after Task 6)

On the MDMT server, from source:

1. **Setup:** Settings → Discord recording. The token is already stored, and Test connection lists MDMT.
2. **Recording:** from a session, Record from Discord, then consent; the bot auto-joins Mike's channel and posts the notice. Record for at least 20 minutes with 2 people, or 3 if available. Include a leave-and-rejoin and a mute and unmute.
3. **Max length:** change it to 1 hour mid-recording through the link, and confirm the line updates. Set it below the elapsed time, choose No and confirm the suspension, then set it longer and confirm it re-arms.
4. **Stop:** Stop, then confirm the tracks are attached, Transcribe opens in tracks mode with names, and a Transcribe run produces a merged transcript.
5. **Recovery:** start a second recording and kill CampaignScribe with Task Manager. Confirm the bot leaves within a few seconds, relaunch, and confirm the recovery prompt converts and attaches the audio.
6. **Packaged build:** run `build.bat`, then repeat steps 2 and 4 briefly from `dist\CampaignScribe\CampaignScribe.exe`.
