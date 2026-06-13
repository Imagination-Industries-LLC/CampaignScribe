# CampaignScribe — Privacy & Data Flow

CampaignScribe is built to collect as little as possible and to be honest and explicit about where your data goes. This is a plain-English description of what stays on your computer and what is sent to outside services (and why).

## Stays on your computer (never sent anywhere)
- **Your audio recordings** — converted and transcribed locally; audio never leaves your machine.
- **The local database** (session metadata) and your saved **transcripts, summaries, and `speakers.json`**.
- **Your Anthropic API key and HuggingFace token** — stored in Windows Credential Manager; sent only to the respective service to authenticate.
- **Voice fingerprints (optional, local only).** To recognize returning players across sessions, CampaignScribe can derive a compact numeric "voice fingerprint" for each tracked speaker from your audio and store it **on your device only**, alongside that campaign's speaker profiles. Fingerprints are never uploaded or shared, are used only to pre-fill speaker assignments for you to confirm, and can be disabled in Settings.

## Sent to the Anthropic Claude API (and why)
- **Transcript excerpts** (speaker samples) — to identify who is speaking (Discover, Transcribe, Refine).
- **Full transcript text** — to write session summaries (Summarize).
- **Your campaign/speaker context** from `speakers.json` — as context for the above.

Anthropic states that API inputs are not used to train their models (commercial terms); API logs are retained briefly (~7–30 days) for abuse monitoring. See Anthropic's privacy policy: https://www.anthropic.com/legal/privacy

## Sent to HuggingFace
- **Only your HuggingFace token**, to authenticate and download the speaker-diarization model. No audio or transcripts are sent — diarization runs locally on your machine.

## Sent to GitHub
- **Update checks** contact GitHub to see whether a newer version exists (and to download it). No personal content.

*Note: automatic update checks are planned and not active in the current release.*

## Feedback & diagnostics (user-initiated only)
The **Help → Feedback & Support** menu can help you share information with us — but only when you choose to, and only after showing you exactly what will be shared:
- **Copy diagnostics / Report a problem** build a small bundle of *non-sensitive* build info: app version, OS, GPU/driver details, and the tail of the local error log. File paths are scrubbed (your home folder shown as `~`) and email addresses are removed. The bundle **never** contains transcripts, audio, API keys/tokens, or `speakers.json`. Copy Diagnostics shows it to you first; Report a Problem opens a pre-filled GitHub issue (public) that you review before submitting.
- **Email feedback** opens a draft to our public address with a short build-info header (version/OS/GPU only — no error log) and space for your message. Nothing is sent until you send it.

## Optional crash reports (off by default)
- Only if you opt in. Crash reports are scrubbed of transcripts, keys, and audio before sending.

*Note: opt-in crash reporting is planned and not active in the current release.*

## What CampaignScribe does NOT do
- No analytics, no tracking, no telemetry by default, and no servers of our own. We collect nothing about you.

---

Questions or concerns? Open an issue or discussion at https://github.com/Imagination-Industries-LLC/CampaignScribe
