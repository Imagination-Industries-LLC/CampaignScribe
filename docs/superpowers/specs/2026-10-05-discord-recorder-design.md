# Discord Live Recorder (Phase 4b) — Design

- **Feature:** Phase 4, part b, of #4 Discord Voice Recording (planning issue CampaignScribe-planning#13)
- **Date:** 2026-10-05
- **Builds on:**
  - Phase 4a, multi-track import (PR #59): one audio file per speaker, merged into one transcript.
  - The 4b feasibility spike of 2026-10-05.
- **Supersedes:** the recording parts of the May 2026 spec. Its py-cord approach cannot receive audio under Discord's DAVE voice encryption, which bots must support since 2026-03.

## Spike evidence (2026-10-05, MDMT server)

- **Stack:** a Node.js recorder using discord.js 14.27.0, @discordjs/voice 0.19.2, @snazzah/davey 0.1.12, libsodium-wrappers 0.8.4, opusscript 0.0.8 and prism-media 1.3.5.
- **Method:** it streams each user's decoded audio straight to disk as mono 48 kHz PCM, with silence filled in from the wall clock.
- **60-minute soak, 2 users:** connected in 0.3 s, then no reconnects and no decode errors. Memory stayed flat at 52–81 MB, both tracks were exactly 3600.81 s long, and the speech was intelligible all the way through.
- **Permissions:** intents Guilds and GuildVoiceStates only; the bot has View Channels, Connect and Send Messages.
- **Not yet proven:** a user leaving and rejoining (a DAVE re-key), 3 or more users, and the recorder running from the packaged exe.

## Goals

1. Record a live Discord voice session from inside CampaignScribe as **one track per person**, written to disk as it happens.
2. One-time bot setup in Settings: a token, an invite link, a connection test, and in-app instructions.
3. Start recording from a session. The bot **joins the channel its owner is in**, with a server and channel picker as the fallback, and posts a configurable recording notice.
4. On Stop, attach the tracks to the session and open Transcribe in "One file per speaker" mode with Discord display names.
5. Recover from crashes and dropouts without losing audio.
6. A user-defined **maximum recording length**, 6 hours by default, shown prominently on the recorder. Clicking it opens the setting, and it can be changed while recording.

## Non-goals (v1)

- Cloud hosting. The recorder runs on the user's PC during the session.
- Video, text-channel logging, and removing speech that leaks between mics.
- Using one bot token on several PCs at once.
- Recording Stage channels.
- Detecting participants' consent. The notice and a confirmation dialog put that responsibility on the user.

## Architecture

```
CampaignScribe (Python/Tk)                         Recorder (Node.js, bundled)
 app/core/discord_recorder.py  --spawn (hidden)-->  recorder/recorder.mjs
   RecorderProcess                env: DISCORD_TOKEN   discord.js + @discordjs/voice + davey
     events <- stdout JSON lines  ------------------   per-user PCM -> <out>/<userId>.pcm
     commands -> stdin JSON lines ------------------   tracks.json, recorder.log
   finalize(out_dir) -> <Name>_<userId>.wav (16 kHz mono) via ffmpeg
```

### 1. The recorder — `recorder/` (new top-level folder, committed)

The folder holds `package.json`, `package-lock.json` (exact pinned versions from the spike) and `recorder.mjs`. `node_modules/` is not committed; it is installed at build time.

**Modes,** chosen by argument:
- `--list` logs in and prints one JSON line, then exits 0. The line contains:
  - `{"event":"inventory","guilds":[{"id","name","voice_channels":[{"id","name"}]}],`
  - `"owner":{"id","name"}|null,"owner_voice":{"guild_id","channel_id"}|null}`
- `--record --out <dir> [--channel <id>] --notice <text>` records. With no `--channel`, it joins the channel in `owner_voice`. If there is none, it prints `{"event":"error","code":"owner_not_in_voice"}` and exits 2.

**Owner lookup.** The recorder reads the owner from `client.application.fetch()`. When the application belongs to a Team, `owner` is `null` and the picker is required.

**Events** are printed to stdout, one JSON object per line:
- `ready` (logged in)
- `joined` with `{guild, channel, channel_name}`
- `notice_posted`
- `user` with `{id, name}` the first time each person is heard
- `speaking` with `{id}`, rate-limited to 1 per user per second
- `telemetry` every 10 s with `{elapsed_s, rss_mb, users:{id:{seconds, packets}}, decode_errors}`
- `reconnecting`
- `rejoined`
- `error` with `{code, message}`
- `stopped` with `{seconds}`

Diagnostic text goes to stderr and to `<out>/recorder.log`. **The token is never printed or logged.**

**Commands** arrive on stdin, one JSON object per line: `{"cmd":"stop"}`. If stdin closes (EOF), the recorder treats it as stop, so a crashed parent never leaves it recording.

**Capture** works as in the spike:
- Each user's audio is subscribed on their first `speaking` event, decoded with opusscript, downmixed to mono and streamed to `<out>/<userId>.pcm`.
- Wall-clock silence is filled in whenever a gap exceeds 40 ms, and late joiners get leading silence.
- On stop, every track is padded to the same length, the recorder posts "⏹️ Recording stopped." and leaves.
- `tracks.json` (`{userId: displayName}`) is rewritten each time a user is first seen.

**Reconnect.** On a voice disconnect, the recorder waits up to 5 s for Signalling or Connecting, as in the @discordjs/voice reconnect pattern. Otherwise it rejoins the same channel up to 3 times, 5 s apart, emitting `reconnecting` and `rejoined`. Silence fills the gap, so alignment holds. If rejoining fails, it emits `error` `{code:"voice_lost"}` and stops cleanly.

**Leave and rejoin.** A user who leaves and comes back keeps the same per-user stream, with silence filling the time they were away.

### 2. Bundling the Node runtime

- **New script `scripts/fetch_node_runtime.py`,** the same pattern as `fetch_diarization_weights.py`.
  - It downloads the official Node.js **v24 LTS win-x64 zip** at a pinned version with a pinned SHA-256.
  - It verifies the zip, then extracts `node.exe` and `npm` to `vendor/node/` (git-ignored).
  - It does nothing if those files are already present and valid.
- **`build.bat`** runs the fetch, then `vendor\node\npm ci --omit=dev` in `recorder\`. Any failure exits 1.
- **PyInstaller** bundles `vendor\node\node.exe` as `node\node.exe`, and `recorder\` (with its `node_modules`) as `recorder\`. The added size is about 85 MB.
- **`setup_venv.bat`** runs the same two steps, but only warns on failure, as it does for the weights.
- **Runtime resolution,** in `discord_recorder.node_exe()` and `recorder_dir()`:
  - Frozen app: `_MEIPASS/node/node.exe` and `_MEIPASS/recorder`.
  - Dev checkout: `vendor/node/node.exe`, falling back to `node` on PATH, and `<repo>/recorder`.
  - If either is missing, `RecorderUnavailable` is raised with a reinstall or "run the fetch script" message.
- **Notices.** `THIRD-PARTY-NOTICES.md` gains entries for Node.js (MIT plus bundled licenses), discord.js and @discordjs/voice (Apache-2.0), @snazzah/davey, opusscript, prism-media and libsodium-wrappers, with their licenses as published.

### 3. Python side — `app/core/discord_recorder.py` (Tk-free)

```python
class RecorderUnavailable(RuntimeError): ...

def node_exe() -> str
def recorder_dir() -> str
def get_token() -> str            # keyring ("CampaignScribe", "discord_bot_token")
def save_token(token: str) -> None
def invite_url(token: str) -> str # client_id = base64url-decode(first token segment)
INVITE_PERMISSIONS = 1051648      # View Channels + Send Messages + Connect

def list_inventory(timeout_s: float = 20.0) -> dict   # runs --list, returns the inventory event

class RecorderProcess:
    def __init__(self, out_dir: str, *, channel_id: str | None, notice: str,
                 on_event: Callable[[dict], None]) -> None
    def start(self) -> None       # Popen(node, recorder.mjs, --record ...), CREATE_NO_WINDOW,
                                  # env DISCORD_TOKEN, stdin/stdout pipes; reader thread -> on_event
    def stop(self, timeout_s: float = 15.0) -> None   # write {"cmd":"stop"}; wait; kill on timeout
    @property
    def running(self) -> bool

def finalize(out_dir: str) -> list[str]
    """Convert every <userId>.pcm (s16le 48 kHz mono) to <DisplayName>_<userId>.wav (16 kHz mono)
    using tracks.json names; delete the .pcm after a successful conversion; return WAV paths."""

def unfinished_recordings(root: str) -> list[str]
    """Recording folders under root that still contain .pcm files (crash recovery)."""
```

- **Subprocesses.** Every one uses `creationflags=subprocess.CREATE_NO_WINDOW`. The token is passed only in the child's environment.
- **Unreadable output.** Lines that aren't JSON are logged and ignored.
- **Failed conversion.** If a track fails to convert, its `.pcm` file is kept and the error is reported. Other tracks still convert.
- **Display names in file names.** Characters that are invalid in Windows file names are replaced with `_`. The WAV name then works with `multitrack.name_from_filename`, which strips the trailing Discord id.

### 4. Settings → Discord — `app/ui/settings_dialog.py`

A new section, "— Discord recording —", with these controls:
- **Bot token:** a masked entry, saved on Save via `save_token`.
- **Invite bot:** opens `invite_url(token)` in the browser. It is disabled while the token is blank.
- **Test connection:** runs `list_inventory` on a worker thread. It then shows "✓ Connected as <bot> — N servers, M voice channels" or the error.
- **How to set up a bot…:** opens a dialog with the developer-portal steps:
  - create an application;
  - Bot page: Public Bot off, privileged intents off, Reset Token and copy it;
  - paste the token here, then click Invite bot.
- **Recording notice:** a text field, saved to config `discord_notice`. Default: `🔴 This voice channel is being recorded by CampaignScribe for session notes.`

- **Max recording length:**
  - two spinboxes, hours from 0 up and minutes from 0 to 59, with the label "Max recording length (auto-stop)";
  - saved to config `discord_max_minutes` (integer, default `360`);
  - the minimum is 1 minute, with no maximum. A value of 0:00 is rejected on Save with "Max recording length must be at least 1 minute."
  - `SettingsDialog(master, initial_provider=None, focus=None)` gains `focus`. With `focus="discord_max_length"` the dialog scrolls to and focuses the hours spinbox, and `AppWindow.open_settings` passes `focus` through.

New config keys:
- `discord_notice`
- `discord_max_minutes` (default `360`)
- `discord_last_guild` and `discord_last_channel`, for the picker
- `recordings_folder`: the parent folder for recordings. If blank, it is `<default output folder or app data>/recordings`.

### 5. Recording from a session — `app/ui/session_view.py` + new `app/ui/discord_record_dialog.py`

**The session view's audio section** gets a **🔴 Record from Discord** button next to "Add audio".

**Pre-flights:**
- If no token is set, the app says "Set up the Discord bot in Settings (⚙) first." and offers to open Settings.
- If the recorder is unavailable, the app shows the `RecorderUnavailable` message.

**The record dialog** is non-modal, one per app, and is a `tk.Toplevel` that is not grab-set, so the app stays usable.

1. **Consent.** A confirmation first says: "Everyone in the voice channel will be recorded. You are responsible for telling participants and getting their consent where the law requires it. The bot will post this notice in the channel: <notice>". The buttons are **Start recording** and **Cancel**.
2. **Channel choice.**
   - The app tries an owner auto-join first.
   - If the recorder exits with `owner_not_in_voice`, or the owner is `null`, the dialog shows a server and voice-channel picker. The picker is filled from `list_inventory` and pre-selects `discord_last_*`. The user starts again from there.
3. **While recording,** the dialog shows:
   - the channel name;
   - an elapsed timer;
   - a row per person, with their name, a speaking dot that is lit for 1.5 s after each `speaking` event, and their recorded minutes;
   - free disk space on the recordings drive, with a warning below 2 GB;
   - status lines for reconnecting and rejoined events;
   - **the auto-stop line,** a large clickable label directly under the timer, described below;
   - a **Stop recording** button.

   **The auto-stop line:**
   - **Text:** `⏱ Auto-stop at H:MM — in H:MM:SS`. It is styled as a link with a hand cursor and the tooltip "Change the maximum recording length".
   - **Clicking it** calls `app.open_settings(focus="discord_max_length")`. Settings is modal, but the recording and this dialog's timers keep running, because `after` callbacks still fire under a grab.
   - **When Settings closes,** and on every 1-second tick, the dialog re-reads `discord_max_minutes`, so a change takes effect immediately while recording.
   - **Last 5 minutes:** the line switches to the warning style and reads `⏱ Auto-stop in M:SS`.
   - **Limit reached:** the dialog runs exactly the same stop path as the Stop button: stop, finalize, attach, navigate. Its status line notes "Stopped automatically at the maximum recording length."
   - **New limit below the time already recorded:** if a change leaves the limit at or below the elapsed time, the dialog asks once, with an askyesno titled "Maximum length already reached": "The new maximum (H:MM) is shorter than this recording (H:MM:SS). Stop recording now?"
     - **Yes** stops through the normal path.
     - **No** keeps recording with auto-stop suspended. The line shows, in the error style, `⏱ Past the maximum length — auto-stop is off until you set a longer limit`. A later change to a limit above the elapsed time re-arms auto-stop.
   - **Who enforces it:** the Python dialog, not the recorder. If CampaignScribe dies, the recorder already stops on stdin EOF.
4. **Stop.** The dialog sends stop, waits for `stopped`, and runs `finalize` on a worker thread. Then it:
   - adds the WAVs to the session's `source_audio_files`, like `_add_track`;
   - closes, and calls `app.open_session_stage(session_id, "transcribe", run_params={"mode": "tracks"})`.
5. **Recorder errors.** If the recorder exits on its own with an error, the dialog shows the error, finalizes whatever was recorded, attaches it, and doesn't navigate.

**Output folder:** `<recordings_folder>/session_<id>_<YYYYmmdd_HHMMSS>/`.

**Transcribe tab, small change.** `load_for_session(session, run_params)` with `run_params["mode"] == "tracks"` switches to "One file per speaker" mode. It uses Task 4's `_apply_mode`. Names are pre-filled from the file names, which are the Discord display names.

### 6. Safety and recovery

- **Closing the app while recording.** `AppWindow._on_close` asks "A Discord recording is running. Stop it and quit?". Yes stops cleanly, finalizes and exits. No keeps recording.
- **Parent crash.** The recorder sees stdin EOF and stops cleanly, so the files stay complete. **Recorder crash:** the `.pcm` files written so far stay on disk.
- **Startup recovery.** A new startup prompt, run after the existing ones in `_run_startup_prompts`, calls `unfinished_recordings(recordings root)`. If any are found, it asks "Finish converting N interrupted recording(s)?". Yes runs `finalize` on each. Each recovered set is attached to its session, read from the `session_<id>_` folder name, when that session still exists. Otherwise it is left in its folder, and the folder is reported.
- **Privacy.** PRIVACY.md gains a "Discord recording" section:
  - Audio travels through Discord's servers, as in any Discord call.
  - CampaignScribe receives it on this PC and stores it only in the recordings folder.
  - The bot token stays in Windows Credential Manager.
  - Nothing is uploaded by CampaignScribe.

## Testing

- **Python unit tests** fake the recorder with a tiny Python script that speaks the JSON protocol, so no Node and no network are needed. They check:
  - event parsing;
  - stop over stdin, and kill on timeout;
  - EOF behavior;
  - `invite_url` decoding;
  - `finalize` with synthetic `.pcm` files: names, sanitising, 16 kHz output length, keeping the `.pcm` on failure;
  - `unfinished_recordings`;
  - `node_exe` and `recorder_dir` resolution, both frozen and dev;
  - token storage on the in-memory keyring.
- **Recorder unit tests,** with Node's built-in test runner (`node --test`) in `recorder/test/`. They cover the pure helpers: silence-gap math, mono downmix, JSON event formatting and display-name sanitising. They run in build and dev checks, not in the Python CI jobs.
- **GUI tests** check:
  - the Settings Discord section;
  - Invite disabled while the token is blank;
  - Test connection with a patched `list_inventory`;
  - the record dialog flow with a fake `RecorderProcess`: consent, then events, then stop, then finalize, then attach and navigate;
  - the picker fallback on `owner_not_in_voice`;
  - the quit-while-recording prompt;
  - the recovery prompt;
  - **max length:**
    - the default of 360 minutes;
    - Save rejecting 0:00;
    - `open_settings(focus="discord_max_length")` focusing the hours spinbox;
    - the auto-stop line text for a fake elapsed time;
    - the warning style in the last 5 minutes;
    - auto-stop calling the same stop path when the fake elapsed time reaches the limit;
    - a mid-recording config change being picked up on the next tick;
    - a new limit below the elapsed time prompting, where Yes stops, No suspends with the error line, and a later longer limit re-arms.

    The dialog's clock is injectable (`now=` callable), so tests never sleep.

  The existing autouse guard fails any unpatched modal dialog.
- **CI constraints:** no Node, network, real ML packages or fetched weights in the Python tests.
- **Manual acceptance,** on the MDMT server:
  1. Owner auto-join, then a session of at least 20 minutes, with 3 or more people if available and otherwise 2. It includes a leave-and-rejoin and a mute and unmute.
  2. Stop. The tracks are attached, Transcribe opens in tracks mode, and the merged transcript has correct names.
  3. Kill CampaignScribe mid-recording. On relaunch, recovery finalizes the audio.
  4. Repeat steps 1 and 2 from the packaged exe built by `build.bat`.
