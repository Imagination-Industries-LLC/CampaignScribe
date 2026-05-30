# CampaignScribe — Privacy & Data Flow

CampaignScribe is built to collect as little as possible and to be honest and explicit about where your data goes. This is a plain-English description of what stays on your computer and what is sent to outside services (and why).

## Stays on your computer (never sent anywhere)
- **Your audio recordings** — converted and transcribed locally; audio never leaves your machine.
- **The local database** (session metadata) and your saved **transcripts, summaries, and `speakers.json`**.
- **Your Anthropic API key and HuggingFace token** — stored in Windows Credential Manager; sent only to the respective service to authenticate.

## Sent to the Anthropic Claude API (and why)
- **Short transcript snippets** (speaker samples) — to identify who is speaking (Discover, Transcribe, Refine).
- **Full transcript text** — to write session summaries (Summarize).
- **Your campaign/speaker context** from `speakers.json` — as context for the above.

Anthropic states that API inputs are not used to train their models (commercial terms); API logs are retained briefly (~7–30 days) for abuse monitoring. See Anthropic's privacy policy: https://www.anthropic.com/legal/privacy

## Sent to HuggingFace
- **Only your HuggingFace token**, to authenticate and download the speaker-diarization model. No audio or transcripts are sent — diarization runs locally on your machine.

## Sent to GitHub
- **Update checks** contact GitHub to see whether a newer version exists (and to download it). No personal content.

## Optional crash reports (off by default)
- Only if you opt in. Crash reports are scrubbed of transcripts, keys, and audio before sending.

## What CampaignScribe does NOT do
- No analytics, no tracking, no telemetry by default, and no servers of our own. We collect nothing about you.
