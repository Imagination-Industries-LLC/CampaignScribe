# First-Run Setup Guidance — Design

- **Feature:** #13 First-Run Setup Guidance (Phase 3; planning issue CampaignScribe-planning#12)
- **Date:** 2026-10-04
- **Supersedes:** the May 2026 spec `Feature Spec - First-Run Setup Guidance.md` (ProtonDrive). That spec assumed an Anthropic key plus a Hugging Face token. The token was removed in #56, and Phase 2 shipped the multi-provider seam.

## Problem

A new user who launches CampaignScribe gets no guidance. A warning banner appears, but they must find the ⚙ button and work out the provider choices alone. The Home tab with no campaigns says "Select a campaign" with nothing to select.

## Already shipped (not in scope)

- **Provider-aware banner.** `AppWindow._refresh_banner` shows `llm.not_ready_message()` for the active provider, local runtimes included.
- **Key testing.** Settings has **Test connection** for every provider and **Detect** for local runtimes.
- **Getting Started text** describes the one-AI-provider requirement.
- **No Hugging Face token.** Diarization weights are bundled.

## Goals

1. On first launch, an unconfigured user is guided to choose and set up an AI provider in one or two clicks.
2. A user who has just set up a provider is invited to create their first campaign.
3. Home explains the empty state and offers the next action.
4. The setup banner is clickable.

## Design

### 1. Trigger rule — new `app/core/first_run.py` (Tk-free)

```python
SETUP_OFFERED_KEY = "setup_welcome_shown"

def should_offer_setup(cfg: dict) -> bool:
    """True when the welcome has never been shown and the active provider is not ready."""
    return not cfg.get(SETUP_OFFERED_KEY, False) and not llm.provider_ready(cfg)

def mark_setup_offered() -> None:
    """Persist the flag (reload-then-save so a concurrent write is not clobbered)."""
```

- The flag is set **when the welcome is shown**, whatever the user picks. The welcome appears at most once per install.
- Users who are already set up never see it. Upgraders who never configured a provider see it once.
- The theme-change window rebuild in `main.py` constructs a new `AppWindow`. The flag prevents a second showing.
- "Config file missing" is **not** used as the signal. `crash_reporting.init_from_config()` and other startup code call `load_config()`, which creates the file before the window exists.
- `DEFAULT_CONFIG` gains `"setup_welcome_shown": False`.

### 2. Startup sequencing — `app/ui/app_window.py`

- The existing `self.after(300, self._maybe_offer_library_import)` becomes `self.after(300, self._run_startup_prompts)`. It keeps the same `_migration_after_id` and the same cancellation paths.
- `_run_startup_prompts()` calls `_maybe_offer_library_import()` first, then `_maybe_first_run_setup()`. Prompts appear one at a time, never stacked.
- Each step is wrapped so an exception in one is logged via `config.log_exception` and does not block the other.
- `_maybe_first_run_setup()`: if `first_run.should_offer_setup(config.load_config())`, call `mark_setup_offered()`, then show the Welcome dialog.

### 3. Welcome dialog — new `app/ui/welcome_dialog.py`

A small modal `tk.Toplevel` that is transient to the main window, grab-set, non-resizable, and themed like the other dialogs.

- **Title:** "Welcome to CampaignScribe"
- **Body:** "CampaignScribe transcribes your sessions on this PC. To name speakers and write summaries it needs an AI model — pick one to set up now. You can change it any time in Settings (⚙)."
- **Buttons, top to bottom:**
  - **Use a cloud AI**, with dim caption "Claude, Google Gemini or OpenRouter — needs an API key". Opens Settings with provider `anthropic` preselected.
  - **Use a free local model**, with dim caption "Ollama or LM Studio, runs on your PC". Opens Settings with provider `ollama` preselected. The existing local-runtime path runs Detect automatically on first view.
  - **Later.** Closes the dialog. The banner stays.
- Closing the window with ✕ or Escape behaves like **Later**.
- The dialog returns the choice: `"cloud"`, `"local"` or `None`. The main window opens Settings after the welcome is destroyed, so two modal grabs are never held at once.

### 4. Settings preselection — `app/ui/settings_dialog.py`

- `SettingsDialog(master, initial_provider: str | None = None)`.
- When `initial_provider` is a key of `llm.PRESETS`, `_build_llm_section` starts on that provider instead of `cfg["llm_provider"]`. The combobox shows its display name, and `_load_llm_fields` runs as usual, auto-running Detect for local runtimes.
- Nothing is saved until the user presses **Save**. Cancel leaves the config's `llm_provider` unchanged.
- An unknown `initial_provider` is ignored.
- `AppWindow.open_settings(initial_provider: str | None = None)` passes it through. Existing call sites are unchanged.

### 5. First-campaign offer — `app/ui/app_window.py`

After Settings closes **from the welcome flow** (cloud or local choice), and only then:
- If `library.list_campaigns()` is empty, ask: **"Create your first campaign?"** with body "A campaign holds your speaker profiles and session history. You can also create one later from Home." (Yes/No).
- Yes switches to the Home tab and calls `home_tab.new_campaign()`, the existing prompt.
- The offer is made whether or not the provider ended up ready. Creating a campaign needs no provider.

### 6. Home empty state — `app/ui/home_tab.py`

- `_new_campaign` is renamed to the public `new_campaign`, and all internal callers are updated. After creating a campaign it selects it, as today.
- When the library has **no campaigns and no uncategorized sessions**, the detail pane shows:
  - Title: **"No campaigns yet"**
  - Summary: "Create a campaign to hold your speaker profiles and sessions, or import an existing speakers .json."
  - A primary-style **"＋ Create your first campaign"** button in the detail pane that calls `new_campaign()`.
- As soon as a campaign exists, the normal "Select a campaign" behavior returns. The empty-state widgets are hidden, not destroyed.
- Evaluated wherever `_refresh_campaigns` or `_clear_detail` runs today.

### 7. Clickable banner — `app/ui/app_window.py`

- An **Open Settings** button (`BTN_GHOST`) packs at the right of `banner_inner` and calls `self.open_settings()`.
- The banner text and show/hide logic are unchanged.

## Error handling

- A failure while building the welcome or the empty state is logged via `config.log_exception`. It must not stop the app from starting.
- `mark_setup_offered` runs before the dialog is shown. A crash inside the dialog therefore cannot cause a repeat on every launch.

## Testing

- **Unit, `tests/unit/test_first_run.py`:**
  - `should_offer_setup` is True when the flag is unset and the provider is not ready.
  - It is False when the flag is set, or when the provider is ready (a stored key, or a local runtime with a model).
  - `mark_setup_offered` persists the flag and keeps unrelated config keys.
- **GUI, `tests/gui/test_welcome_flow.py`:** `messagebox` and `SettingsDialog` are patched to record calls, with no real modal waits.
  - Startup on a fresh config shows the welcome once. A second `AppWindow` on the same config does not.
  - **Cloud** opens Settings with `initial_provider="anthropic"`. **Local** opens it with `"ollama"`. **Later** and ✕ open nothing.
  - After cloud or local, with an empty library, the first-campaign offer appears. Yes calls `home_tab.new_campaign`. With an existing campaign there is no offer.
  - A ready provider shows no welcome.
- **GUI, `tests/gui/test_settings_initial_provider.py`:**
  - The dialog opens on the requested provider.
  - Cancel does not change `llm_provider`.
  - An unknown id falls back to the configured provider.
- **GUI, `tests/gui/test_home_empty_state.py`:**
  - An empty library shows "No campaigns yet" and the create button.
  - After `library.create_campaign`, the empty state is hidden.
- **GUI, banner:** the banner's Open Settings button calls `open_settings`.
- **CI:** the GUI tests must not rely on fetched model weights or a real provider. The `tests/gui/conftest.py` weights fixture already covers the weights.

## Out of scope

- A multi-step setup wizard.
- New key-testing or model-detection logic, which already exists.
- A startup check for bundled model files. Transcribe, Refine and Discover already pre-flight this.
- Re-showing the welcome from a menu. Help → Getting Started remains the manual entry point.
