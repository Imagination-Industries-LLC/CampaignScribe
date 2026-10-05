"""Settings dialog: AI model/provider, default model, output folder, # speakers."""

from __future__ import annotations

import math
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app import config
from app.core import discord_recorder, llm
from app.core.llm import cost, local_detect
from app.ui.common import ScrollableFrame, open_url

# Room for Gemini thinking tokens / reasoning models; the probe reply is still one word.
_TEST_PROBE_MAX_TOKENS = 64
_TEST_PROBE_TIMEOUT_S = 30.0


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, initial_provider: str | None = None, focus: str | None = None):
        super().__init__(master)
        self._initial_provider = initial_provider
        self.title("CampaignScribe — Settings")
        self.transient(master)
        self.resizable(False, False)
        self.grab_set()

        cfg = config.load_config()

        # Save/Cancel stay pinned at the bottom; everything else scrolls so the dialog always
        # fits the screen (the Discord section made it taller than a 900 px display).
        self._btn_frame = ttk.Frame(self)
        self._btn_frame.pack(side="bottom", pady=12)
        self._scroll = ScrollableFrame(self)
        self._scroll.pack(side="top", fill="both", expand=True)
        self._body = self._scroll.inner

        pad = {"padx": 10, "pady": 6}
        row = 0

        row = self._build_llm_section(row, pad)

        ttk.Label(self._body, text="Default output folder:").grid(
            row=row, column=0, sticky="w", **pad
        )
        self.out_var = tk.StringVar(value=cfg.get("default_output_folder", ""))
        ttk.Entry(self._body, textvariable=self.out_var, width=55).grid(row=row, column=1, **pad)
        ttk.Button(self._body, text="Browse…", command=self._browse_out).grid(
            row=row, column=2, **pad
        )
        row += 1

        ttk.Label(self._body, text="Default Whisper model:").grid(
            row=row, column=0, sticky="w", **pad
        )
        self.model_var = tk.StringVar(value=cfg.get("default_whisper_model", "large-v3"))
        ttk.Combobox(
            self._body,
            textvariable=self.model_var,
            state="readonly",
            width=20,
            values=["tiny", "base", "small", "medium", "large-v3"],
        ).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(self._body, text="Default # speakers:").grid(row=row, column=0, sticky="w", **pad)
        self.spk_var = tk.IntVar(value=int(cfg.get("default_num_speakers", 5)))
        ttk.Spinbox(
            self._body,
            from_=1,
            to=20,
            textvariable=self.spk_var,
            width=8,
        ).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(self._body, text="Theme:").grid(row=row, column=0, sticky="w", **pad)
        self.theme_var = tk.StringVar(value=cfg.get("theme_mode", "dark").capitalize())
        ttk.Combobox(
            self._body,
            textvariable=self.theme_var,
            state="readonly",
            width=20,
            values=["Dark", "Light", "System"],
        ).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        # ---- Discovery section ----
        ttk.Separator(self._body, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", padx=10, pady=(6, 2)
        )
        row += 1
        ttk.Label(self._body, text="— Discovery —").grid(
            row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 4)
        )
        row += 1
        ttk.Label(
            self._body,
            text=(
                "Discovery uses a lighter model on a sample to build the initial roster"
                " — you review it before transcribing."
            ),
            wraplength=420,
            justify="left",
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 4))
        row += 1

        ttk.Label(self._body, text="Discovery model:").grid(row=row, column=0, sticky="w", **pad)
        self.discover_model_var = tk.StringVar(value=cfg.get("discover_whisper_model", "small"))
        ttk.Combobox(
            self._body,
            textvariable=self.discover_model_var,
            state="readonly",
            width=20,
            values=["tiny", "base", "small", "medium", "large-v3"],
        ).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(self._body, text="Discovery sample (min, 0 = full first file):").grid(
            row=row, column=0, sticky="w", **pad
        )
        self.discover_sample_var = tk.IntVar(value=int(cfg.get("discover_sample_minutes", 0)))
        ttk.Spinbox(
            self._body,
            from_=0,
            to=120,
            textvariable=self.discover_sample_var,
            width=8,
        ).grid(row=row, column=1, sticky="w", **pad)
        row += 1

        # ---- Privacy / crash reporting ----
        ttk.Separator(self._body, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", padx=10, pady=(6, 2)
        )
        row += 1
        ttk.Label(self._body, text="— Privacy —").grid(
            row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 4)
        )
        row += 1
        self.crash_var = tk.BooleanVar(value=bool(cfg.get("crash_reporting_enabled", False)))
        ttk.Checkbutton(
            self._body,
            text="Send anonymous crash reports to help fix bugs (opt-in)",
            variable=self.crash_var,
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 2))
        row += 1
        ttk.Label(
            self._body,
            text=(
                "Off by default. Reports are scrubbed of transcripts, audio, keys, speaker "
                "profiles, and personal paths before sending. See Help → Privacy & Data."
            ),
            wraplength=420,
            justify="left",
        ).grid(row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 6))
        row += 1

        row = self._build_discord_section(row, pad, cfg)

        self.save_btn = ttk.Button(self._btn_frame, text="Save", command=self._save)
        self.save_btn.pack(side="left", padx=6)
        ttk.Button(self._btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=6)

        self._fit_to_screen(master)
        self.llm_provider_combo.focus_set()
        if focus == "discord_max_length":
            self.after_idle(self._focus_discord_max)

    def _fit_to_screen(self, master) -> None:
        """Size the dialog to its content, capped to the screen, and keep it fully on screen."""
        self.update_idletasks()
        canvas = self._scroll.canvas
        body_w = self._body.winfo_reqwidth()
        body_h = self._body.winfo_reqheight()
        btn_h = self._btn_frame.winfo_reqheight() + 24
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        max_h = max(sh - 96, 200)
        vsb_w = self._scroll.vsb.winfo_reqwidth()
        width = min(body_w + vsb_w, sw)
        height = min(body_h + btn_h, max_h)
        canvas.configure(width=body_w, height=max(height - btn_h, 50))
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + 60
        x = max(0, min(x, sw - width))
        y = max(0, min(y, sh - height - 48))  # leave room for the taskbar
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.update_idletasks()

    def _scroll_into_view(self, widget) -> None:
        canvas = self._scroll.canvas
        total = max(self._body.winfo_reqheight(), 1)
        offset = widget.winfo_rooty() - self._body.winfo_rooty()
        canvas.yview_moveto(max(0.0, min(1.0, (offset - 20) / total)))

    def _focus_discord_max(self):
        try:
            self.lift()
            self.update_idletasks()
            self._scroll_into_view(self.discord_max_hours_spin)
            self.discord_max_hours_spin.focus_force()
        except tk.TclError:
            pass

    # ---- Discord recording section ----
    def _build_discord_section(self, row: int, pad: dict, cfg: dict) -> int:
        ttk.Separator(self._body, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", padx=10, pady=(6, 2)
        )
        row += 1
        ttk.Label(self._body, text="— Discord recording —").grid(
            row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 4)
        )
        row += 1

        self._discord_loaded_token = discord_recorder.get_token()
        ttk.Label(self._body, text="Bot token:").grid(row=row, column=0, sticky="w", **pad)
        self.discord_token_var = tk.StringVar(value=self._discord_loaded_token)
        self.discord_token_entry = ttk.Entry(
            self._body, textvariable=self.discord_token_var, width=55, show="•"
        )
        self.discord_token_entry.grid(row=row, column=1, **pad)
        self.discord_invite_btn = ttk.Button(
            self._body, text="Invite bot", command=self._invite_discord_bot
        )
        self.discord_invite_btn.grid(row=row, column=2, **pad)
        self.discord_token_var.trace_add("write", lambda *_: self._sync_discord_invite())
        self._sync_discord_invite()
        row += 1

        test_frame = ttk.Frame(self._body)
        test_frame.grid(row=row, column=1, columnspan=2, sticky="w", **pad)
        self.discord_test_btn = ttk.Button(
            test_frame, text="Test connection", command=self._test_discord
        )
        self.discord_test_btn.pack(side="left")
        self.discord_test_label = ttk.Label(test_frame, text="", wraplength=300, justify="left")
        self.discord_test_label.pack(side="left", padx=8)
        ttk.Button(test_frame, text="How to set up a bot…", command=self._show_discord_guide).pack(
            side="right"
        )
        row += 1

        ttk.Label(self._body, text="Recording notice:").grid(row=row, column=0, sticky="w", **pad)
        self.discord_notice_var = tk.StringVar(
            value=cfg.get("discord_notice") or config.DEFAULT_CONFIG["discord_notice"]
        )
        ttk.Entry(self._body, textvariable=self.discord_notice_var, width=55).grid(
            row=row, column=1, columnspan=2, sticky="w", **pad
        )
        row += 1

        ttk.Label(self._body, text="Max recording length (auto-stop):").grid(
            row=row, column=0, sticky="w", **pad
        )
        total = int(cfg.get("discord_max_minutes", 360) or 360)
        self.discord_max_hours_var = tk.IntVar(value=total // 60)
        self.discord_max_minutes_var = tk.IntVar(value=total % 60)
        len_frame = ttk.Frame(self._body)
        len_frame.grid(row=row, column=1, sticky="w", **pad)
        self.discord_max_hours_spin = ttk.Spinbox(
            len_frame, from_=0, to=999, textvariable=self.discord_max_hours_var, width=5
        )
        self.discord_max_hours_spin.pack(side="left")
        ttk.Label(len_frame, text="h").pack(side="left", padx=(2, 10))
        ttk.Spinbox(
            len_frame, from_=0, to=59, textvariable=self.discord_max_minutes_var, width=4
        ).pack(side="left")
        ttk.Label(len_frame, text="min").pack(side="left", padx=(2, 0))
        row += 1
        return row

    def _sync_discord_invite(self):
        tok = self.discord_token_var.get().strip()
        ok = bool(tok) and discord_recorder.invite_url(tok) is not None
        self.discord_invite_btn.config(state="normal" if ok else "disabled")

    def _invite_discord_bot(self):
        url = discord_recorder.invite_url(self.discord_token_var.get().strip())
        if url:
            open_url(url)

    def _test_discord(self, _sync: bool = False):
        """Check the (possibly unsaved) typed token against Discord.

        The typed value is passed as list_inventory(token=...), so testing never saves it.
        """
        token = self.discord_token_var.get().strip()
        if not token:
            self.discord_test_label.config(text="✗ Enter a bot token first.")
            return
        self.discord_test_btn.config(state="disabled")
        self.discord_test_label.config(text="Testing…")

        def work():
            try:
                text = self._format_discord_inventory(discord_recorder.list_inventory(token=token))
            except discord_recorder.RecorderError as e:
                text = f"✗ {e.message}"
            except discord_recorder.RecorderUnavailable as e:
                text = f"✗ {e}"
            except Exception as e:
                text = f"✗ {type(e).__name__}"
            if _sync:
                self._finish_discord_test(text)
                return
            try:
                self.after(0, lambda: self._finish_discord_test(text))
            except (RuntimeError, tk.TclError):
                pass

        if _sync:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _format_discord_inventory(inv: dict) -> str:
        guilds = inv.get("guilds") or []
        n = len(guilds)
        chans = sum(len(g.get("voice_channels") or []) for g in guilds)
        return (
            f"✓ Connected — {n} server{'' if n == 1 else 's'}, "
            f"{chans} voice channel{'' if chans == 1 else 's'}"
        )

    def _finish_discord_test(self, text: str):
        try:
            if not self.winfo_exists():
                return
            self.discord_test_label.config(text=text)
            self.discord_test_btn.config(state="normal")
        except tk.TclError:
            pass

    def _show_discord_guide(self):
        win = tk.Toplevel(self)
        win.title("Set up a Discord bot")
        win.transient(self)
        txt = tk.Text(win, width=70, height=14, wrap="word", padx=10, pady=8)
        txt.insert(
            "1.0",
            "1. Go to https://discord.com/developers/applications and click New Application.\n"
            "2. Open the Bot tab and turn OFF Public Bot, so only you can add it.\n"
            "3. Click Reset Token, copy the token, and paste it into Bot token here. "
            "Treat it like a password: anyone with it controls the bot.\n"
            "4. Click Invite bot and add the bot to your server.\n"
            "5. Click Test connection to confirm the bot can see your server.\n"
            "Leave all Privileged Gateway Intents OFF (Presence, Server Members, Message Content): "
            "the recorder does not need them.\n",
        )
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(0, 8))

    # ---- AI model section ----
    def _build_llm_section(self, row: int, pad: dict) -> int:
        cfg = config.load_config()
        self._llm_state: dict[str, dict] = {}
        self._llm_loaded_keys: dict[str, str] = {}
        for pid, preset in llm.PRESETS.items():
            key = config.get_provider_key(pid)
            self._llm_loaded_keys[pid] = key
            self._llm_state[pid] = {
                "model": cfg.get(f"llm_model_{pid}", "") or preset.default_model,
                "key": key,
                "base_url": cfg.get("llm_base_url_custom", "") if preset.needs_base_url else "",
                "detected": [],
                "detected_once": False,
                "detecting": False,
                "caveat": "",
                "rate_in": "",
                "rate_out": "",
            }
        for pid, preset in llm.PRESETS.items():
            r = cost.rates_for(preset, cfg)
            self._llm_state[pid]["rate_in"] = cost.fmt_rate(r.input_per_mtok)
            self._llm_state[pid]["rate_out"] = cost.fmt_rate(r.output_per_mtok)
        self._detect_queue: queue.Queue = queue.Queue()
        self._llm_current = cfg.get("llm_provider", "anthropic")
        if self._llm_current not in llm.PRESETS:
            self._llm_current = "anthropic"
        # First-run welcome can open Settings on a chosen provider. Nothing is
        # persisted until Save, so Cancel keeps the configured provider.
        if self._initial_provider in llm.PRESETS:
            self._llm_current = self._initial_provider
        self._display_to_id = {p.display_name: pid for pid, p in llm.PRESETS.items()}

        ttk.Label(self._body, text="— AI model —").grid(
            row=row, column=0, columnspan=3, sticky="w", padx=10, pady=(6, 0)
        )
        row += 1

        ttk.Label(self._body, text="Provider:").grid(row=row, column=0, sticky="w", **pad)
        self.llm_provider_var = tk.StringVar(value=llm.PRESETS[self._llm_current].display_name)
        self.llm_provider_combo = ttk.Combobox(
            self._body,
            textvariable=self.llm_provider_var,
            state="readonly",
            width=28,
            values=[p.display_name for p in llm.PRESETS.values()],
        )
        self.llm_provider_combo.grid(row=row, column=1, sticky="w", **pad)
        self.llm_provider_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_provider_change())
        row += 1

        self.llm_badge_label = ttk.Label(self._body, text="", wraplength=520, justify="left")
        self.llm_badge_label.grid(row=row, column=1, columnspan=2, sticky="w", padx=10, pady=(0, 2))
        row += 1

        self.llm_rates_row = ttk.Frame(self._body)
        self.llm_rates_row.grid(row=row, column=0, columnspan=3, sticky="ew")
        ttk.Label(self.llm_rates_row, text="Rates ($ per M tokens):").grid(
            row=0, column=0, sticky="w", **pad
        )
        rates_inner = ttk.Frame(self.llm_rates_row)
        rates_inner.grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(rates_inner, text="in").pack(side="left")
        self.llm_rate_in_var = tk.StringVar()
        ttk.Entry(rates_inner, textvariable=self.llm_rate_in_var, width=8).pack(
            side="left", padx=(4, 12)
        )
        ttk.Label(rates_inner, text="out").pack(side="left")
        self.llm_rate_out_var = tk.StringVar()
        ttk.Entry(rates_inner, textvariable=self.llm_rate_out_var, width=8).pack(
            side="left", padx=(4, 12)
        )
        ttk.Button(rates_inner, text="Default", command=self._reset_rates).pack(side="left")
        row += 1

        ttk.Label(self._body, text="Model:").grid(row=row, column=0, sticky="w", **pad)
        self.llm_model_var = tk.StringVar()
        self.llm_model_combo = ttk.Combobox(
            self._body, textvariable=self.llm_model_var, width=52, state="normal", values=[]
        )
        self.llm_model_combo.grid(row=row, column=1, **pad)
        self.llm_model_var.trace_add("write", lambda *_: self._refresh_badges())
        model_btns = ttk.Frame(self._body)
        model_btns.grid(row=row, column=2, sticky="w", **pad)
        ttk.Button(model_btns, text="Default", command=self._reset_model).pack(side="left")
        self.llm_detect_btn = ttk.Button(model_btns, text="Detect", command=self._run_detect)
        # packed/unpacked by _load_llm_fields
        row += 1

        self.llm_local_label = ttk.Label(self._body, text="", wraplength=520, justify="left")
        self.llm_local_label.grid(row=row, column=1, columnspan=2, sticky="w", padx=10, pady=(0, 4))
        row += 1

        self.llm_key_row = ttk.Frame(self._body)
        self.llm_key_row.grid(row=row, column=0, columnspan=3, sticky="ew")
        ttk.Label(self.llm_key_row, text="API key:").grid(row=0, column=0, sticky="w", **pad)
        self.api_var = tk.StringVar()
        self.api_entry = ttk.Entry(self.llm_key_row, textvariable=self.api_var, width=55, show="•")
        self.api_entry.grid(row=0, column=1, **pad)
        self.api_show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.llm_key_row,
            text="Show",
            variable=self.api_show_var,
            command=self._toggle_api_visibility,
        ).grid(row=0, column=2, sticky="w", **pad)
        self.llm_key_row.columnconfigure(1, weight=1)
        row += 1

        self.llm_base_url_row = ttk.Frame(self._body)
        self.llm_base_url_row.grid(row=row, column=0, columnspan=3, sticky="ew")
        ttk.Label(self.llm_base_url_row, text="Base URL:").grid(row=0, column=0, sticky="w", **pad)
        self.llm_base_url_var = tk.StringVar()
        ttk.Entry(self.llm_base_url_row, textvariable=self.llm_base_url_var, width=55).grid(
            row=0, column=1, **pad
        )
        self.llm_base_url_row.columnconfigure(1, weight=1)
        row += 1

        self.llm_test_btn = ttk.Button(
            self._body, text="Test connection", command=self._test_connection
        )
        self.llm_test_btn.grid(row=row, column=0, sticky="w", **pad)
        self.llm_test_label = ttk.Label(self._body, text="", wraplength=420, justify="left")
        self.llm_test_label.grid(row=row, column=1, columnspan=2, sticky="w", **pad)
        row += 1

        ttk.Separator(self._body, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", padx=10, pady=(2, 6)
        )
        row += 1

        self._load_llm_fields()
        return row

    def _stash_llm_fields(self) -> None:
        st = self._llm_state[self._llm_current]
        st["model"] = self.llm_model_var.get()
        st["key"] = self.api_var.get()
        if llm.PRESETS[self._llm_current].needs_base_url:
            st["base_url"] = self.llm_base_url_var.get()
        st["rate_in"] = self.llm_rate_in_var.get()
        st["rate_out"] = self.llm_rate_out_var.get()

    def _load_llm_fields(self) -> None:
        preset = llm.PRESETS[self._llm_current]
        st = self._llm_state[self._llm_current]
        self.llm_model_var.set(st["model"])
        self.llm_model_combo.config(values=[m.model_id for m in st["detected"]])
        self.api_var.set(st["key"])
        self.llm_base_url_var.set(st["base_url"])
        self.llm_rate_in_var.set(st["rate_in"])
        self.llm_rate_out_var.set(st["rate_out"])
        if preset.local_runtime:
            self.llm_rates_row.grid_remove()
        else:
            self.llm_rates_row.grid()
        if preset.needs_base_url:
            self.llm_base_url_row.grid()
        else:
            self.llm_base_url_row.grid_remove()
        if preset.needs_key or preset.provider_id == "custom":
            self.llm_key_row.grid()
        else:
            self.llm_key_row.grid_remove()
        if preset.local_runtime:
            self.llm_detect_btn.pack(side="left", padx=(6, 0))
            self.llm_local_label.config(text=st["caveat"])
            self.llm_detect_btn.config(state="disabled" if st["detecting"] else "normal")
        else:
            self.llm_detect_btn.pack_forget()
            self.llm_local_label.config(text="")
        self.llm_test_label.config(text="")
        self._refresh_badges()
        if preset.local_runtime and not st["detected_once"]:
            self._run_detect()

    def _on_provider_change(self) -> None:
        new_id = self._display_to_id.get(self.llm_provider_var.get(), "anthropic")
        if new_id == self._llm_current:
            return
        self._stash_llm_fields()
        self._llm_current = new_id
        self._load_llm_fields()

    def _refresh_badges(self) -> None:
        preset = llm.PRESETS[self._llm_current]
        model = self.llm_model_var.get().strip()
        size = ""
        for m in self._llm_state[self._llm_current]["detected"]:
            if m.model_id == model:
                size = m.parameter_size
                break
        self.llm_badge_label.config(text=" · ".join(llm.badges_for(preset, model, size)))

    # ---- local runtime detection ----
    def _run_detect(self, _sync: bool = False) -> None:
        pid = self._llm_current
        preset = llm.PRESETS[pid]
        if not preset.local_runtime:
            return
        st = self._llm_state[pid]
        st["detected_once"] = True
        st["detecting"] = True
        st["caveat"] = f"Looking for {preset.display_name}…"
        self.llm_local_label.config(text=st["caveat"])
        self.llm_detect_btn.config(state="disabled")
        if _sync:
            self._apply_detect_result(local_detect.detect(preset.local_runtime))
            return

        # Capture only plain values: if the worker held `self`, the Tk variables could be
        # garbage-collected on the worker thread and raise "main thread is not in main loop".
        q = self._detect_queue
        runtime = preset.local_runtime

        def worker() -> None:
            try:
                result = local_detect.detect(runtime)
            except Exception as e:  # noqa: BLE001 - the poll loop must always terminate
                result = local_detect.DetectResult(
                    runtime, False, [], f"detect failed: {type(e).__name__}: {e}"
                )
            q.put(result)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll_detect)

    def _poll_detect(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            result = self._detect_queue.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_detect)
            return
        self._apply_detect_result(result)

    def _apply_detect_result(self, result) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        pid = result.runtime_id  # preset ids equal runtime ids for the two local presets
        preset = llm.PRESETS[pid]
        st = self._llm_state[pid]
        st["detected"] = list(result.models)
        if result.running and result.models and not st["model"].strip():
            st["model"] = result.models[0].model_id
        if not result.running:
            text = (
                f"{preset.display_name} not running — start it, then press Detect. ({result.error})"
            )
        elif not result.models:
            text = (
                "0 models found — run `ollama pull <model>` (e.g. qwen2.5:14b), then press Detect."
                if pid == "ollama"
                else "0 models found — load a model in LM Studio, then press Detect."
            )
        else:
            text = (
                f"{len(result.models)} models found. Small models (< 12B) may struggle with "
                "the strict speaker-ID JSON; summaries are fine."
            )
        st["detecting"] = False
        st["caveat"] = text
        if pid == self._llm_current:
            self.llm_model_combo.config(values=[m.model_id for m in st["detected"]])
            if not self.llm_model_var.get().strip():
                self.llm_model_var.set(st["model"])
            self.llm_local_label.config(text=st["caveat"])
            self.llm_detect_btn.config(state="normal")
            self._refresh_badges()

    def _reset_model(self) -> None:
        default = llm.PRESETS[self._llm_current].default_model
        if default:  # blank for local presets: keep the user's chosen model
            self.llm_model_var.set(default)

    def _reset_rates(self) -> None:
        preset = llm.PRESETS[self._llm_current]
        self.llm_rate_in_var.set(cost.fmt_rate(preset.input_per_mtok))
        self.llm_rate_out_var.set(cost.fmt_rate(preset.output_per_mtok))

    @staticmethod
    def _parse_rates(text_in: str, text_out: str) -> tuple[float, float] | None:
        try:
            i, o = float(text_in.strip()), float(text_out.strip())
        except ValueError:
            return None
        if not (math.isfinite(i) and math.isfinite(o)) or i < 0 or o < 0:
            return None
        return i, o

    def _test_connection(self, _sync: bool = False) -> None:
        self._stash_llm_fields()
        pid = self._llm_current
        st = self._llm_state[pid]
        self.llm_test_label.config(text="Testing…")
        self.llm_test_btn.config(state="disabled")

        def run() -> str:
            try:
                provider = llm.make_provider(
                    pid,
                    model=st["model"],
                    api_key=st["key"].strip(),
                    base_url=st["base_url"],
                    timeout_s=_TEST_PROBE_TIMEOUT_S,
                )
                provider.complete(
                    "Reply with the single word OK.", max_tokens=_TEST_PROBE_MAX_TOKENS
                )
                return f"✓ Connected ({provider.display_name} · {provider.model})"
            except llm.LLMError as e:
                return f"✗ {e}"
            except Exception as e:  # noqa: BLE001 - surfaced inline, never crashes the dialog
                return f"✗ {type(e).__name__}: {e}"

        if _sync:
            self._report_test_result(run())
            return

        def worker() -> None:
            result = run()
            try:
                self.after(0, lambda: self._report_test_result(result))
            except tk.TclError:
                pass  # dialog already destroyed

        threading.Thread(target=worker, daemon=True).start()

    def _report_test_result(self, text: str) -> None:
        try:
            if not self.winfo_exists():
                return
            self.llm_test_label.config(text=text)
            self.llm_test_btn.config(state="normal")
        except tk.TclError:
            pass

    def _toggle_api_visibility(self):
        self.api_entry.config(show="" if self.api_show_var.get() else "•")

    def _browse_out(self):
        path = filedialog.askdirectory(
            title="Choose default output folder",
            initialdir=config.load_config().get("last_output_folder", "") or None,
        )
        if path:
            self.out_var.set(path)

    def _save(self):
        try:
            max_minutes = int(self.discord_max_hours_var.get()) * 60 + int(
                self.discord_max_minutes_var.get()
            )
        except (tk.TclError, ValueError):
            max_minutes = 0
        if max_minutes < 1:
            messagebox.showerror(
                "Settings", "Max recording length must be at least 1 minute.", parent=self
            )
            return
        try:
            self._stash_llm_fields()
            for pid, st in self._llm_state.items():
                key = st["key"].strip()
                if key != self._llm_loaded_keys.get(pid, ""):
                    config.save_provider_key(pid, key)
            cfg = config.load_config()
            cfg["llm_provider"] = self._llm_current
            for pid, st in self._llm_state.items():
                model = st["model"].strip()
                cfg[f"llm_model_{pid}"] = "" if model == llm.PRESETS[pid].default_model else model
            rates = (
                dict(cfg.get("llm_rates") or {}) if isinstance(cfg.get("llm_rates"), dict) else {}
            )
            for pid, st in self._llm_state.items():
                preset = llm.PRESETS[pid]
                if preset.local_runtime:
                    rates.pop(pid, None)
                    continue
                pair = self._parse_rates(st["rate_in"], st["rate_out"])
                if pair is None or pair == (preset.input_per_mtok, preset.output_per_mtok):
                    rates.pop(pid, None)
                else:
                    rates[pid] = [pair[0], pair[1]]
            cfg["llm_rates"] = rates
            cfg["llm_base_url_custom"] = self._llm_state["custom"]["base_url"].strip().rstrip("/")
            cfg["default_output_folder"] = self.out_var.get().strip()
            cfg["default_whisper_model"] = self.model_var.get()
            cfg["default_num_speakers"] = int(self.spk_var.get() or 5)
            cfg["theme_mode"] = self.theme_var.get().lower()
            cfg["discover_whisper_model"] = self.discover_model_var.get()
            cfg["discover_sample_minutes"] = int(self.discover_sample_var.get() or 0)
            cfg["crash_reporting_enabled"] = bool(self.crash_var.get())
            token = self.discord_token_var.get().strip()
            if token != self._discord_loaded_token:
                discord_recorder.save_token(token)
            cfg["discord_notice"] = self.discord_notice_var.get().strip() or str(
                config.DEFAULT_CONFIG["discord_notice"]
            )
            cfg["discord_max_minutes"] = max_minutes
            config.save_config(cfg)
            from app.core import crash_reporting

            crash_reporting.set_enabled(cfg["crash_reporting_enabled"])
        except Exception as e:
            messagebox.showerror("Settings", f"Could not save settings:\n{e}", parent=self)
            return
        self.destroy()
