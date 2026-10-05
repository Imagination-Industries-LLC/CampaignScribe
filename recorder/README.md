# CampaignScribe Discord recorder

A small Node.js helper that CampaignScribe launches to record a Discord voice channel, one
raw track per speaker. It joins with the bot, receives audio (including Discord's DAVE
end-to-end encryption), and speaks a line-based JSON protocol over stdio so the Python app
can drive it.

## Protocol

`node recorder.mjs --list` prints one `inventory` JSON line and exits 0. On a failure it
prints one `error` line and exits 1.

`node recorder.mjs --record --out <dir> --notice <text> [--channel <id>]` streams events.
The channel defaults to the voice channel the bot owner is currently in. Exit codes:

- 0 after `stopped`
- 2 on `owner_not_in_voice`
- 1 on fatal errors

**Every stdout line is one JSON object** with an `event` key:

- `ready` with `{bot:{id,name}}`
- `inventory` with `{guilds:[{id,name,voice_channels:[{id,name}]}], owner:{id,name}|null, owner_voice:{guild_id,channel_id}|null, application_id}`
- `joined` with `{guild_id, guild_name, channel_id, channel_name}`
- `notice_posted`
- `user` with `{id, name}` (re-sent when the display name resolves)
- `speaking` with `{id}`, at most once per user per second
- `telemetry` with `{elapsed_s, rss_mb, users:{<id>:{seconds, packets}}, decode_errors}`, every 10 s
- `reconnecting` with `{attempt}`
- `rejoined`
- `error` with `{code, message}`
- `stopped` with `{seconds}`

Error codes: `login_failed`, `no_token`, `channel_not_found`, `owner_not_in_voice`,
`join_timeout`, `voice_lost`, `bad_args`.

**stdin** takes one JSON object per line. `{"cmd":"stop"}` stops the recording, and EOF on
stdin also stops it (so a recorder never outlives its parent).

**Files written to `--out`:**

- `<userId>.pcm`: s16le, 48 kHz, mono, padded to wall-clock so all tracks are the same length
- `tracks.json`: `{userId: displayName}`, rewritten when a user is first seen and again when their name resolves
- `recorder.log`

## Token

The bot token is read only from the `DISCORD_TOKEN` environment variable. It is never passed on
a command line, printed, logged, or written to a file.

## Development

```
cd recorder
npm ci
node --test
```

Plain `node --test` (or `npm test`) run from this folder is the form that works on Node 24; the
`node --test <dir>` form is not accepted there. The test that submits a rejected token to
Discord needs network and is skipped unless `CS_NET_TESTS=1` is set.
