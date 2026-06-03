"""Main application window: notebook tabs, status bar, settings button.

Updated to adopt Mike's DM Tools Design System via ``app.ui.theme``.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app import __version__, config
from app.core import library, privacy
from app.core.transcriber import check_gpu
from app.ui.common import make_readonly, open_path_native, open_url, reveal_in_folder
from app.ui.edit_profile_window import EditProfileWindow
from app.ui.home_tab import HomeTab
from app.ui.refine_tab import RefineTab
from app.ui.session_view import SessionView
from app.ui.settings_dialog import SettingsDialog
from app.ui.summarize_tab import SummarizeTab
from app.ui.theme import (
    BTN_GHOST,
    BTN_LINK,
    LBL_EYEBROW,
    LBL_STATUS_INFO,
    LBL_STATUS_WARN,
    LBL_TITLE,
    S_2,
    S_3,
    S_4,
    StatusLevel,
    apply_theme,
    color,
)
from app.ui.transcribe_tab import TranscribeTab


def backlink_sessions_to_campaigns() -> int:
    """Non-destructive: link null-slug sessions to a same-named library campaign
    (case-insensitive exact name match). Returns the count linked."""
    from app.core import library
    from app.data import db

    by_name = {c["display_name"].strip().lower(): c["slug"] for c in library.list_campaigns()}
    linked = 0
    for s in db.list_sessions(campaign_slug=db.UNCATEGORIZED):
        name = (s.get("campaign_name") or "").strip().lower()
        slug = by_name.get(name)
        if slug:
            db.update_session(s["id"], campaign_slug=slug)
            linked += 1
    return linked


class AppWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self._rebuild_requested = False
        self.title(f"CampaignScribe v{__version__}")

        # 🎨 MDMT theme — must run BEFORE any widget is constructed.
        # Sets ttk styles, classic-Tk widget defaults, window background,
        # and (via _set_icon below) the multi-resolution app icon.
        apply_theme(self)

        cfg = config.load_config()
        w = int(cfg.get("window_width", 1000))
        h = int(cfg.get("window_height", 760))
        x = int(cfg.get("window_x", -1))
        y = int(cfg.get("window_y", -1))
        # Restore exact position (including a second monitor); (-1, -1) = unset.
        if (x, y) != (-1, -1):
            self.geometry(f"{w}x{h}+{x}+{y}")
        else:
            self.geometry(f"{w}x{h}")
        self.minsize(900, 700)

        self._set_icon()

        # ---- Top bar -----------------------------------------------------
        topbar = ttk.Frame(self, style="Chrome.TFrame")
        topbar.pack(side="top", fill="x")

        title_block = ttk.Frame(topbar, style="Chrome.TFrame")
        title_block.pack(side="left", padx=S_4, pady=S_3)

        ttk.Label(
            title_block,
            text="CampaignScribe — D&D Transcription Suite",
            style=LBL_TITLE,
            background=color("BG_CHROME"),
        ).pack(anchor="w")

        ttk.Label(
            title_block,
            text="◈  RECORDED · RECAPPED · RECALLED  ◈",
            style=LBL_EYEBROW,
            background=color("BG_CHROME"),
        ).pack(anchor="w")

        ttk.Button(topbar, text="⚙ Settings", style=BTN_GHOST, command=self.open_settings).pack(
            side="right", padx=S_4, pady=S_3
        )

        # ---- API key banner (shown only when missing) --------------------
        # Using a plain tk.Frame because we want a one-off warm tint that
        # doesn't deserve its own named style.
        self.banner = tk.Frame(self, background=color("BG_CHROME"), borderwidth=0)
        # Inner row gives us padding without futzing with the outer frame
        banner_inner = tk.Frame(self.banner, background=color("BG_CHROME"))
        banner_inner.pack(fill="x", padx=S_4, pady=S_2)

        ttk.Label(
            banner_inner,
            text="⚠  No Anthropic API key stored. Click Settings (⚙) to add it.",
            style=LBL_STATUS_WARN,
        ).pack(side="left")

        self.banner_label = banner_inner  # backwards-compatible attribute

        # ---- Notebook ----------------------------------------------------
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=S_2, pady=S_2)

        # Show/hide the API-key banner. Must run AFTER self.notebook exists:
        # when no key is stored, _refresh_banner packs the banner with
        # before=self.notebook, so the notebook must already be created.
        self._refresh_banner()

        self.home_tab = HomeTab(self.notebook, self)
        self.transcribe_tab = TranscribeTab(self.notebook, self)
        self.summarize_tab = SummarizeTab(self.notebook, self)
        self.refine_tab = RefineTab(self.notebook, self)

        # (widget, label, icon-name) in display order
        self._tab_specs = [
            (self.home_tab, "1. Home", "campaigns"),
            (self.transcribe_tab, "2. Transcribe", "transcribe"),
            (self.summarize_tab, "3. Summarize", "summarize"),
            (self.refine_tab, "4. Refine", "refine"),
        ]
        self._tab_icons = {}  # icon-name -> {"idle": PhotoImage, "active": PhotoImage}
        for widget, label, icon in self._tab_specs:
            self._tab_icons[icon] = {
                "idle": self._load_tab_icon(icon, "idle"),
                "active": self._load_tab_icon(icon, "active"),
            }
            idle = self._tab_icons[icon]["idle"]
            if idle is not None:
                self.notebook.add(widget, text=label, image=idle, compound="left")
            else:
                self.notebook.add(widget, text=label)

        # Mark the initially-selected tab (index 0) with its active icon.
        _first_active = self._tab_icons.get(self._tab_specs[0][2], {}).get("active")
        if _first_active is not None:
            self.notebook.tab(0, image=_first_active)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # ---- Status bar --------------------------------------------------
        # Replaces the previous emoji-prefixed StringVar with a colored
        # Canvas dot + a Label whose style flips with the level.
        status_bar = tk.Frame(self, background=color("BG_CHROME"), height=28)
        status_bar.pack(side="bottom", fill="x")

        self._status_dot = tk.Canvas(
            status_bar,
            width=14,
            height=14,
            background=color("BG_CHROME"),
            highlightthickness=0,
        )
        self._status_dot.pack(side="left", padx=(S_4, S_3), pady=S_3)

        self.status_var = tk.StringVar()
        self._status_label = ttk.Label(
            status_bar,
            textvariable=self.status_var,
            style=LBL_STATUS_INFO,
        )
        self._status_label.pack(side="left", pady=S_3)

        self._update_status_bar()

        self._build_menu()
        self._bind_shortcuts()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Offer the one-time library migration after the window is shown.
        self._migration_after_id = self.after(300, self._maybe_offer_library_import)

    # ----------------------------------------------------------------------
    # Status bar
    # ----------------------------------------------------------------------

    def _set_status_dot(self, color_hex: str) -> None:
        """Redraw the status dot with the given fill."""
        self._status_dot.delete("all")
        self._status_dot.create_oval(
            2,
            2,
            12,
            12,
            fill=color_hex,
            outline=color_hex,
        )

    def _set_status(self, level: tuple, message: str) -> None:
        """Update both the dot color and the label style to match ``level``.

        ``level`` is one of :data:`StatusLevel.OK` / ``.WARN`` / ``.ERR`` / ``.INFO``.
        """
        _, style_name, color_token = level
        self.status_var.set(message)
        self._status_label.configure(style=style_name)
        self._set_status_dot(color(color_token))

    def _update_status_bar(self) -> None:
        """Compute the right level + message for the current GPU/torch state."""
        gpu = check_gpu()
        rec = gpu.get("recommendation")
        torch_v = gpu.get("torch_version") or "?"
        cuda_v = gpu.get("torch_cuda_version") or "none"

        if rec == "cuda":
            msg = (
                f"GPU: {gpu['device_name']} ({gpu['vram_gb']} GB VRAM) — "
                f"torch {torch_v} (cuda {cuda_v}) — Transcription ready"
            )
            self._set_status(StatusLevel.OK, msg)
        elif rec == "cpu_no_cuda":
            msg = (
                f"GPU detected ({gpu.get('smi_gpu_name', 'NVIDIA')}) but PyTorch "
                f"can't use it — falling back to CPU. "
                f"torch {torch_v} (built for cuda {cuda_v}). "
                f"Update NVIDIA driver/CUDA at nvidia.com/Download"
            )
            self._set_status(StatusLevel.WARN, msg)
        elif rec == "cpu_unavailable":
            msg = (
                f"PyTorch not available ({gpu.get('error', 'unknown error')}) "
                f"— transcription disabled"
            )
            self._set_status(StatusLevel.ERR, msg)
        else:
            msg = f"No NVIDIA GPU detected — CPU mode (very slow for long files). torch {torch_v}"
            self._set_status(StatusLevel.WARN, msg)

    # ----------------------------------------------------------------------
    # Icon (unchanged from original; reads new assets/icon.ico)
    # ----------------------------------------------------------------------

    def _set_icon(self):
        import os
        import sys

        try:
            if getattr(sys, "frozen", False):
                base = sys._MEIPASS  # type: ignore[attr-defined]
            else:
                base = os.path.dirname(os.path.abspath(os.path.join(__file__, "..", "..")))
            ico = os.path.join(base, "assets", "icon.ico")
            if os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:
            pass

    # ----------------------------------------------------------------------
    # Banner / settings / tab plumbing (unchanged behavior)
    # ----------------------------------------------------------------------

    def _refresh_banner(self):
        if config.get_anthropic_key():
            self.banner.pack_forget()
        else:
            # Insert above notebook, below topbar
            self.banner.pack(side="top", fill="x", before=self.notebook)

    def _maybe_offer_library_import(self):
        """One-time migration: if the library is empty and the user has a
        previously-used speakers.json on disk, offer to import it. Asked at
        most once (guarded by config 'library_import_prompted').

        Also runs the one-time back-link migration (guarded by
        'sessions_backlinked') that links existing null-slug sessions to a
        same-named library campaign.  Both hooks are independent.
        """
        import os

        # One-time back-link: link null-slug sessions to matching campaigns.
        cfg = config.load_config()
        if not cfg.get("sessions_backlinked"):
            try:
                backlink_sessions_to_campaigns()
            except Exception:
                pass
            cfg = config.load_config()
            cfg["sessions_backlinked"] = True
            config.save_config(cfg)

        cfg = config.load_config()
        if cfg.get("library_import_prompted"):
            return
        # Already using the library? Nothing to migrate; don't ask again.
        if library.list_campaigns():
            cfg["library_import_prompted"] = True
            config.save_config(cfg)
            return
        last = cfg.get("last_speakers_json", "")
        if not last or not os.path.exists(last):
            return  # nothing to offer yet — leave the flag so a future run can ask
        if messagebox.askyesno(
            "Import to Campaign Library?",
            "CampaignScribe now organizes speaker profiles into a Campaign "
            "Library.\n\nImport your most recent speakers.json to get started?"
            f"\n\n{last}",
            parent=self,
        ):
            try:
                library.import_file(last)
            except Exception as e:
                messagebox.showerror("CampaignScribe", f"Could not import:\n{e}")
            else:
                if hasattr(self, "home_tab"):
                    try:
                        self.home_tab.on_show()
                    except Exception:
                        pass  # a UI refresh failure must not block the migration
        # Re-load: the modal above ran the Tk event loop, so config may have
        # changed underneath us (e.g. Settings opened via shortcut). Reload
        # before flipping the flag so we don't clobber a concurrent write.
        cfg = config.load_config()
        cfg["library_import_prompted"] = True
        config.save_config(cfg)

    def open_settings(self):
        old_mode = config.load_config().get("theme_mode", "dark")
        dlg = SettingsDialog(self)
        self.wait_window(dlg)
        self._refresh_banner()
        for tab in (
            self.home_tab,
            self.transcribe_tab,
            self.summarize_tab,
            self.refine_tab,
        ):
            if hasattr(tab, "on_settings_changed"):
                tab.on_settings_changed()
        new_mode = config.load_config().get("theme_mode", "dark")
        if new_mode != old_mode:
            self._handle_theme_change()

    def _any_tab_busy(self) -> bool:
        return any(getattr(widget, "_busy", False) for widget, _label, _icon in self._tab_specs)

    def request_rebuild(self):
        """Persist geometry, flag a rebuild, and close the window so the
        entry-point relaunch loop constructs a fresh one (new theme applied)."""
        self._save_window_geometry()
        self._rebuild_requested = True
        if getattr(self, "_migration_after_id", None) is not None:
            try:
                self.after_cancel(self._migration_after_id)
            except Exception:
                pass
            self._migration_after_id = None
        self.destroy()

    def _handle_theme_change(self):
        """Apply a theme_mode change by rebuilding — unless a job is running,
        in which case defer to next launch (the new mode is already persisted)."""
        if self._any_tab_busy():
            messagebox.showinfo(
                "Theme",
                "A job is currently running. The new theme will be applied the "
                "next time you launch CampaignScribe.",
                parent=self,
            )
            return
        self.request_rebuild()

    def open_home(self):
        self.notebook.select(self.home_tab)
        if hasattr(self.home_tab, "on_show"):
            self.home_tab.on_show()

    def open_edit_profile(self, slug: str, discover_audio: str | None = None):
        win = EditProfileWindow(self, self, slug)
        if discover_audio:
            win.start_discover(discover_audio)
        return win

    def open_session(self, session_id: int):
        SessionView(self, self, session_id)

    def open_session_stage(self, session_id: int, stage: str):
        from app.data import db

        session = db.get_session(session_id)
        tab = {
            "transcribe": self.transcribe_tab,
            "summarize": self.summarize_tab,
            "refine": self.refine_tab,
        }.get(stage, self.transcribe_tab)
        if session is not None and hasattr(tab, "load_for_session"):
            tab.load_for_session(session)
        self.notebook.select(tab)

    def jump_to_tab(self, index: int):
        self.notebook.select(index)

    # ----------------------------------------------------------------------
    # Menu bar + keyboard shortcuts
    # ----------------------------------------------------------------------

    def _build_menu(self):
        menubar = tk.Menu(self)

        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(
            label="Open Audio…", accelerator="Ctrl+O", command=self._menu_open_audio
        )
        filemenu.add_command(label="Settings…", accelerator="Ctrl+,", command=self.open_settings)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=filemenu)

        toolsmenu = tk.Menu(menubar, tearoff=0)
        toolsmenu.add_command(label="Open Logs Folder", command=self._open_logs_folder)
        toolsmenu.add_command(label="Open Data Folder", command=self._open_data_folder)
        menubar.add_cascade(label="Tools", menu=toolsmenu)

        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="Getting Started", command=self._show_getting_started)
        helpmenu.add_command(label="Privacy & Data", command=self._show_privacy)
        helpmenu.add_separator()
        helpmenu.add_command(label="About CampaignScribe", command=self._show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)

        self.config(menu=menubar)

    def _bind_shortcuts(self):
        self.bind_all("<Control-o>", lambda _e: self._menu_open_audio())
        self.bind_all("<Control-O>", lambda _e: self._menu_open_audio())
        self.bind_all("<Control-comma>", lambda _e: self.open_settings())
        self.bind_all("<F5>", lambda _e: self._run_current_tab())
        for i in range(1, len(self._tab_specs) + 1):
            self.bind_all(f"<Control-Key-{i}>", lambda _e, n=i - 1: self.jump_to_tab(n))

    def _current_tab(self):
        try:
            idx = self.notebook.index("current")
        except Exception:
            return None
        if 0 <= idx < len(self._tab_specs):
            return self._tab_specs[idx][0]
        return None

    def _menu_open_audio(self):
        """Ctrl+O / File→Open Audio: use the current tab's audio browse if it has
        one, else jump to Transcribe and open its file picker."""
        tab = self._current_tab()
        if hasattr(tab, "_browse_audio"):
            tab._browse_audio()
        elif hasattr(tab, "_add_files"):
            tab._add_files()
        else:
            self.notebook.select(self.transcribe_tab)
            if hasattr(self.transcribe_tab, "_add_files"):
                self.transcribe_tab._add_files()

    def _run_current_tab(self):
        """F5: invoke the current tab's primary action button if enabled."""
        tab = self._current_tab()
        btn = getattr(tab, "go_btn", None)
        if btn is not None and str(btn["state"]) != "disabled":
            btn.invoke()

    def _open_logs_folder(self):
        log = config.get_error_log_path()
        if log.exists():
            reveal_in_folder(str(log))
        else:
            open_path_native(str(config.get_app_data_dir()))

    def _open_data_folder(self):
        open_path_native(str(config.get_app_data_dir()))

    def _show_getting_started(self):
        messagebox.showinfo(
            "Getting Started",
            "CampaignScribe needs two free credentials (Settings ⚙):\n\n"
            "1. Anthropic API key — for speaker identification and summaries.\n"
            "2. HuggingFace token — for speaker diarization (also accept the "
            "pyannote model license on huggingface.co).\n\n"
            "Then work left to right: Home → New session → Transcribe → "
            "Summarize. Refine improves your speaker profile from new audio.",
            parent=self,
        )

    def _show_privacy(self):
        PrivacyDialog(self)

    def _show_about(self):
        AboutDialog(self)

    def _asset_dir(self):
        import os
        import sys

        if getattr(sys, "frozen", False):
            base = sys._MEIPASS  # type: ignore[attr-defined]
        else:
            base = os.path.dirname(os.path.abspath(os.path.join(__file__, "..", "..")))
        return os.path.join(base, "assets")

    def _load_tab_icon(self, name: str, state: str):
        """Load a 16px tab icon as a PhotoImage, or None if unavailable.
        References are held in self._tab_icons so Tk doesn't GC them."""
        import os

        try:
            p = os.path.join(self._asset_dir(), "tab-icons", f"{name}-{state}-16.png")
            if os.path.exists(p):
                return tk.PhotoImage(file=p)
        except Exception:
            pass
        return None

    def _on_tab_changed(self, _event=None):
        """Swap the selected tab's icon to its 'active' variant (others to
        'idle') and give the now-visible tab a chance to refresh its data."""
        try:
            idx = self.notebook.index("current")
        except Exception:
            return
        for i, (_widget, _label, icon) in enumerate(self._tab_specs):
            img = self._tab_icons.get(icon, {}).get("active" if i == idx else "idle")
            if img is not None:
                try:
                    self.notebook.tab(i, image=img)
                except Exception:
                    pass
        if 0 <= idx < len(self._tab_specs):
            tab = self._tab_specs[idx][0]
            if hasattr(tab, "on_show"):
                try:
                    tab.on_show()
                except Exception:
                    pass

    def _save_window_geometry(self):
        try:
            cfg = config.load_config()
            cfg["window_width"] = self.winfo_width()
            cfg["window_height"] = self.winfo_height()
            cfg["window_x"] = self.winfo_x()
            cfg["window_y"] = self.winfo_y()
            config.save_config(cfg)
        except Exception:
            pass

    def _on_close(self):
        self._save_window_geometry()
        if getattr(self, "_migration_after_id", None) is not None:
            try:
                self.after_cancel(self._migration_after_id)
            except Exception:
                pass
            self._migration_after_id = None
        self.destroy()


class AboutDialog(tk.Toplevel):
    """Modal About box: logo, version, description, acknowledgements."""

    def __init__(self, master):
        super().__init__(master)
        self.title("About CampaignScribe")
        self.transient(master)
        self.resizable(False, False)
        self.grab_set()

        self._logo = None
        try:
            import os

            p = os.path.join(master._asset_dir(), "icon-128.png")
            if os.path.exists(p):
                self._logo = tk.PhotoImage(file=p)
                ttk.Label(self, image=self._logo).pack(pady=(16, 4))
        except Exception:
            pass

        ttk.Label(self, text="CampaignScribe", style=LBL_TITLE).pack()
        ttk.Label(self, text=f"Version {__version__}", style=LBL_EYEBROW).pack(pady=(2, 10))
        ttk.Label(
            self,
            text="Transcribe and summarize tabletop RPG sessions.",
            wraplength=420,
            justify="center",
        ).pack(padx=24)
        ttk.Label(
            self,
            text=(
                "Built on WhisperX, pyannote.audio, and the Anthropic Claude API.\n"
                "github.com/Imagination-Industries-LLC/CampaignScribe"
            ),
            wraplength=420,
            justify="center",
        ).pack(padx=24, pady=(8, 4))
        ttk.Button(self, text="Close", command=self.destroy).pack(pady=12)

        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + 80
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")


class PrivacyDialog(tk.Toplevel):
    """Scrollable Help → Privacy & Data dialog rendering PRIVACY.md."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Privacy & Data — CampaignScribe")
        self.transient(master)
        self.geometry("640x560")
        self.minsize(520, 420)
        self.grab_set()

        ttk.Label(self, text="Privacy & Data", style=LBL_TITLE).pack(
            anchor="w", padx=S_4, pady=(S_4, S_2)
        )

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=S_4)
        text = tk.Text(
            body,
            wrap="word",
            borderwidth=0,
            highlightthickness=0,
            background=color("BG_INPUT"),
            foreground=color("FG"),
        )
        scroll = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.insert("1.0", privacy.load_privacy_text())
        make_readonly(text)

        links = ttk.Frame(self)
        links.pack(fill="x", padx=S_4, pady=S_3)
        ttk.Button(
            links,
            text="Anthropic Privacy Policy",
            style=BTN_LINK,
            command=lambda: open_url(privacy.ANTHROPIC_PRIVACY_URL),
        ).pack(side="left")
        ttk.Button(
            links,
            text="View PRIVACY.md on GitHub",
            style=BTN_LINK,
            command=lambda: open_url(privacy.PRIVACY_MD_URL),
        ).pack(side="left", padx=(S_3, 0))
        ttk.Button(links, text="Close", style=BTN_GHOST, command=self.destroy).pack(side="right")

        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + 60
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
