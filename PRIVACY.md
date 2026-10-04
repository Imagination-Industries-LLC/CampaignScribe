# CampaignScribe — Privacy & Data Flow

CampaignScribe is built to collect as little as possible and to be honest and explicit about where your data goes. This is a plain-English description of what stays on your computer and what is sent to outside services (and why).

## Stays on your computer (never sent anywhere)
- **Your audio recordings** — converted and transcribed locally; audio never leaves your machine.
- **The local database** (session metadata) and your saved **transcripts, summaries, and `speakers.json`**.
- **Your AI-provider API keys** — stored in Windows Credential Manager; each is sent only to its own service to authenticate.
- **Voice fingerprints (optional, local only).** To recognize returning players across sessions, CampaignScribe can derive a compact numeric "voice fingerprint" for each tracked speaker from your audio and store it **on your device only**, alongside that campaign's speaker profiles. Fingerprints are never uploaded or shared, are used only to pre-fill speaker assignments for you to confirm, and can be disabled in Settings.

## Sent to your chosen AI provider (and why)
CampaignScribe uses one AI provider at a time — chosen in **Settings → AI model** (Claude by default). For every provider the same three things are sent, and nothing else:
- **Transcript excerpts** (speaker samples) — to identify who is speaking (Discover, Transcribe, Refine).
- **Full transcript text** — to write session summaries (Summarize).
- **Your campaign/speaker context** from `speakers.json` — as context for the above.

Where that data goes depends on the provider you pick:
- **Claude (Anthropic Claude API, default)** — Anthropic states that API inputs are not used to train their models (commercial terms); API logs are retained briefly (~7–30 days) for abuse monitoring. https://www.anthropic.com/legal/privacy
- **Google Gemini** — sent to Google's Gemini API under the Gemini API terms (on the **paid** tier Google states prompts are not used to improve its products; on the **free** tier they may be — check which tier your key is on). https://ai.google.dev/gemini-api/terms
- **OpenRouter** — sent to OpenRouter, which **forwards it to the model vendor you selected** (an extra routing hop; that vendor's own policy then applies). https://openrouter.ai/privacy
- **Custom endpoint** — sent to whatever OpenAI-compatible server you configured. If that is a local server (for example Ollama on your own PC), your transcripts stay on your machine.
- **Ollama / LM Studio (local)** — nothing is sent anywhere. The model runs on your own computer and your transcripts never leave it. CampaignScribe only talks to the runtime on `localhost`.

The in-app notes on the Transcribe, Summarize and Refine screens always name the provider currently in use.

## Model downloads (first use only)
- The speech-recognition models (Whisper) are downloaded from Hugging Face's public servers, and a word-alignment model from pytorch.org, the first time they are needed. No account, token, audio, or transcripts are sent.
- The speaker-diarization model ships with CampaignScribe and never downloads.

## Sent to GitHub
- **Update checks** contact GitHub to see whether a newer version exists (and to download it). No personal content.

*Note: automatic update checks are planned and not active in the current release.*

## Feedback & diagnostics (user-initiated only)
The **Help → Feedback & Support** menu can help you share information with us — but only when you choose to, and only after showing you exactly what will be shared:
- **Copy diagnostics / Report a problem** build a small bundle of *non-sensitive* build info: app version, OS, GPU/driver details, and the tail of the local error log. File paths are scrubbed (your home folder shown as `~`) and email addresses are removed. The bundle **never** contains transcripts, audio, API keys/tokens, or `speakers.json`. Copy Diagnostics shows it to you first; Report a Problem opens a pre-filled GitHub issue (public) that you review before submitting.
- **Email feedback** opens a draft to our public address with a short build-info header (version/OS/GPU only — no error log) and space for your message. Nothing is sent until you send it.

## Optional crash reports (off by default)
- **Off unless you turn it on** in Settings → Privacy. When enabled, only *crash* reports (unhandled errors) are sent, via Sentry, to help fix bugs — no usage tracking or session pings.
- Every report is **scrubbed before sending**: no transcripts, audio, API keys/tokens, or speaker profiles; file paths have your home folder replaced with `~`, email addresses are removed, and your computer/account name is dropped. Stack-frame local variables are never collected.
- Turning the setting back off **stops all transmission** immediately.

## What CampaignScribe does NOT do
- No analytics, no tracking, no telemetry by default, and no servers of our own. We collect nothing about you.

---

Questions or concerns? Open an issue or discussion at https://github.com/Imagination-Industries-LLC/CampaignScribe
