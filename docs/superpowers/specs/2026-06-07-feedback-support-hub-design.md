# Feedback & Support Hub — Design (consolidated)

- **Status:** Designed (brainstorm 2026-06-07). Builds the unified hub from three original specs.
- **Repo:** `Imagination-Industries-LLC/CampaignScribe` (`H:\git\CampaignScribe`). Branch: `feature/feedback-support-hub`.
- **Consolidates:** Feature Specs #2 (Crash Diagnostics & Telemetry), #10 (Feedback & Support Hub), #8 (Support / Pay-What-You-Want). This is the single source of truth; the three originals are superseded by this consolidation.
- **Planning issue:** private board #6.

## Goal
Give users one **opt-in, user-initiated** place to report problems, send feedback, find discussions, and support development — consolidating today's scattered Help actions into a single `Help → Feedback & Support` dialog. Respect the project's minimal-data stance (privacy spec #3): nothing is transmitted automatically except the explicitly opt-in (default-off) crash reporter.

## Structure (decided)
**One `Help → Feedback & Support` dialog** with five sections. The existing Help menu (Getting Started · Privacy & Data · About CampaignScribe, in `app_window.py`) gains a **Feedback & Support** entry. Sections:
1. **🐞 Report a problem** — opens a pre-filled GitHub issue (diagnostics bundle + reproduce/expected/actual template).
2. **📋 Copy diagnostics** — shows a preview of the local bundle, then → clipboard + "Save as .txt".
3. **✉️ Email feedback** — shows the public address (copyable) + "Email us" → a `mailto:` draft with a short build-info header.
4. **💡 Feature ideas** — "Open Discussions" → the repo's GitHub Discussions board.
5. **❤️ Support development** — Ko-fi / GitHub Sponsors / Patreon links + the "does not cover AI costs" disclaimer.

## Build sequence (three slices; external setup walked through just-in-time)
We build all of it; each externally-gated piece has a one-time **USER SETUP** step done right before its task.
- **Slice A — Diagnostics + Hub + Email + Discussions (needs: feedback email address; enable Discussions).** The unblocked core.
- **Slice B — Support / PWYW (needs: Ko-fi / GitHub Sponsors / Patreon accounts).**
- **Slice C — Sentry opt-in crash reporting (needs: Sentry write-only DSN).**

Each slice is its own implementation plan + PR. This spec captures all three.

---

## Slice A — Diagnostics, Hub dialog, Email, Discussions

### `app/core/diagnostics.py` (new, Tk-free, unit-tested)
- `build_diagnostics_bundle(include_log_tail: bool = True) -> str` — a single plain-text block:
  - App version (`app.__version__` = "1.0.0"), OS build (`platform.platform()`), Python version.
  - GPU/torch/CUDA state from `transcriber.check_gpu()` (already returns a dict).
  - If `include_log_tail`: the **tail** of `errors.log` (`config.get_error_log_path()`), last ~200 lines.
- `scrub(text: str) -> str` — replaces the user home dir with `~` (and any `C:\Users\<name>` style paths), drops obvious usernames/emails. Applied to the whole bundle.
- **Deliberately excludes** transcripts, audio, API keys/tokens, and `speakers.json` content. (The bundle only ever reads version/OS/GPU + `errors.log`; the scrubber is defense-in-depth on the log tail.)
- Two callers: Copy Diagnostics (`include_log_tail=True`) and the Email header (a compact variant — version/OS/GPU only, **no** log tail, to respect `mailto:` length limits).

### Copy diagnostics (dialog)
- A small preview Toplevel shows exactly the bundle text that will be shared (full transparency), with **Copy to clipboard** and **Save as .txt** buttons. Read-only text widget (reuse `app.ui.common.make_readonly`).

### Report a problem
- Builds a GitHub new-issue URL for `Imagination-Industries-LLC/CampaignScribe` with a title + a body template (steps to reproduce / expected / actual) and the diagnostics bundle in a fenced block, URL-encoded, opened via `webbrowser`.
- **Overflow fallback:** if the URL exceeds a safe length (~7000 chars), copy the bundle to the clipboard and open a blank new-issue with the template + a "paste your diagnostics here" placeholder. GitHub issues are public; the bundle is non-sensitive by design.

### Email feedback
- Shows the public address (copyable) and an "Email us" button building a `mailto:` URL:
  - subject: `CampaignScribe Feedback (v1.0.0)` (interpolate `app.__version__`).
  - body: the compact build-info header (version/OS/GPU, no log tail) + a `\n\n— your feedback below —\n` placeholder. URL-encoded; keep it short.
  - Opened via `webbrowser`. If no mail client handles it, the address is still shown for manual copy.
- **OPEN ITEM (collect before this task):** the public feedback email address (a dedicated `feedback@…`-style address recommended). Stored as `FEEDBACK_EMAIL` in a new `app/core/support.py` — the single home for external-contact constants: `FEEDBACK_EMAIL` (Slice A), the `REPO_SLUG`/Discussions + new-issue URLs (Slice A, reused by Report-a-problem and Feature-ideas), and the funding URLs (added in Slice B). Tk-free.

### Feature ideas → Discussions
- "Open Discussions" button → `https://github.com/Imagination-Industries-LLC/CampaignScribe/discussions` via `webbrowser`.
- **USER SETUP (Slice A):** enable GitHub Discussions on the repo + add a "Feedback / Ideas" category (a one-time repo setting; walked through during the build).

### The hub dialog
- New `Help → Feedback & Support` opening a `FeedbackSupportDialog` Toplevel (follow the existing `AboutDialog`/Privacy dialog patterns in `app_window.py`). Houses sections 1–4 in Slice A; section 5 (Support) is added in Slice B.

---

## Slice B — Support / Pay-What-You-Want (needs funding accounts)

- **USER SETUP:** create Ko-fi (primary, one-time PWYW), GitHub Sponsors (repo Sponsor button), and Patreon (recurring) — walked through; collect the URLs/usernames.
- **`FUNDING.yml`** at repo root (`ko_fi:`, `github:`, `patreon:`) → lights up the repo "Sponsor" button.
- **Support section** (section 5 of the hub) + an **About-box Support link** (`AboutDialog`):
  - "CampaignScribe is free and open" statement.
  - **Prominent disclaimer:** "Donations support ongoing development only — they do NOT cover AI model or API costs. You pay your chosen AI provider directly, or avoid those costs entirely by running a local model (see Settings)."
  - Buttons: Ko-fi (suggested $5 / $10), GitHub Sponsors, Patreon → `webbrowser`.
- **One-time gentle nudge:** after the user completes their **3rd** consolidated summary, show one dismissible dialog ("Enjoying CampaignScribe? … a one-time $5/$10 helps development. (This doesn't cover AI costs.)") with **Support / Maybe later / Don't show again**.
  - Config: `summaries_completed` (int, default 0), `support_nudge_shown` (bool, default false). Increment in the `_consolidate` success path (`summarize_tab.py`); when the counter hits 3 and the flag is false, show once and set the flag. "Don't show again" also sets the flag. Never repeats.
- Store the funding URLs as constants in `app/core/support.py`.

---

## Slice C — Opt-in crash reporting (needs Sentry DSN)

- **USER SETUP:** create a Sentry account + a project, get a **write-only DSN** (safe to embed); walked through.
- **Settings checkbox** (`settings_dialog.py`): "Send anonymous crash reports to help fix bugs (opt-in)" — default **OFF** — with a one-line link to the privacy note. Config: `crash_reporting_enabled` (bool, default false).
- **`sentry-sdk`** added as an optional dependency; initialized **only when opted in** (at startup if the flag is set, and when toggled on), with the embedded write-only DSN.
- **`before_send` scrubber** strips PII before transmit: no transcript text, no audio, no keys/tokens, no `speakers.json`; replace user home in paths with `~`; drop usernames/emails. Reuse `diagnostics.scrub` where possible.
- **Coverage:** a global handler for unhandled exceptions on the main thread AND worker threads (the app runs transcription/summarization on `threading.Thread`; Sentry must capture those — verify the worker-thread exception path, alongside the existing `config.log_exception`).
- Consent is explicit + revocable: disabling the checkbox stops all transmission (re-init / close the client).
- **Privacy:** `PRIVACY.md` + the in-app Privacy dialog gain a line describing the opt-in crash reporter and exactly what it sends (scrubbed) — text must match the consent checkbox.
- Cost: free Sentry Developer tier (5,000 errors/mo).

---

## Privacy & data (cross-cutting, #3)
- Slice A: the diagnostics bundle + email header carry **non-sensitive build info only**, are **user-initiated**, and are **shown before sending** (the Copy Diagnostics preview; the email draft the user reviews). Add a line to `PRIVACY.md` / Privacy dialog noting the user-initiated diagnostics/feedback path.
- Slice C: the opt-in crash reporter is the only automatic transmission; documented as above, default off.

## Config keys (new)
- Slice B: `summaries_completed` (int, 0), `support_nudge_shown` (bool, false).
- Slice C: `crash_reporting_enabled` (bool, false).

## Out of scope
- Any in-app form posting to a backend; any always-on telemetry/usage analytics (everything is user-initiated except the opt-in reporter).
- In-app payments, license keys, paid feature gating (app stays fully free); donor tracking.
- Native/out-of-process crash capture (Crashpad) — unnecessary for Python/Tkinter.

## Test plan
- **Slice A (unit, Tk-free):** `build_diagnostics_bundle` includes version/OS/GPU (+ log tail when asked); `scrub` replaces home→`~` and drops user/email; bundle excludes anything sensitive given a sample `errors.log`. `mailto:`/issue-URL builders produce correctly URL-encoded strings with the build-info header; issue-URL overflow path switches to the clipboard fallback (test the length-branch logic purely).
- **Slice A (GUI):** Help → Feedback & Support opens with sections 1–4; Copy Diagnostics preview shows the bundle and copies it; Report a Problem / Email / Discussions invoke the right URLs (inject a fake `webbrowser.open`/clipboard to capture).
- **Slice B:** nudge fires once after the 3rd summary, is dismissible, never reappears (flag persisted); "Don't show again" honored; Support section + About link open the right URLs; `FUNDING.yml` present.
- **Slice C:** crash reporting OFF by default; enabling + forcing an exception sends a **scrubbed** event (verify no PII/transcript/key/path in the payload via a captured `before_send`); disabling stops events; worker-thread exception is captured.
