"""The first-run Setup window (plain Tk, standard library only)."""

from __future__ import annotations

import threading
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import messagebox, ttk

from bootstrap import core

TITLE = "CampaignScribe — first-time setup"
GPU_LABEL = "GPU (NVIDIA) — recommended"
CPU_LABEL = "CPU only"
CPU_CAPTION = (
    "Transcription runs on the CPU and will be much slower for long recordings "
    "(a multi-hour session can take many hours). You can switch to GPU later in Settings."
)
NO_GPU_WARNING = "No NVIDIA GPU was found — the GPU option may not work on this PC."
CUDA_WARNING = (
    "Installed, but the GPU isn't usable right now (driver missing or too old). "
    "CampaignScribe will use the CPU until that's fixed."
)
EXPLANATION = (
    "CampaignScribe needs to download its speech-recognition engine once "
    "(about {gb} GB). This can take a while on slower connections."
)
DOWNLOAD_GB = {"gpu": "2.6", "cpu": "0.3"}
LOG_TAIL = 30


def _default_spawn(fn) -> None:
    threading.Thread(target=fn, daemon=True).start()


class _Failed:
    ok = False
    cuda_ok = False

    def __init__(self, message):
        self.message = message


class SetupWindow:
    """Choice -> progress -> (failure | CUDA warning | done).

    ``installer(profile, log_cb, progress_cb)`` runs on a worker (``spawn``) and
    returns an object with ``ok``, ``cuda_ok`` and ``message``. It may expose
    ``cancel()`` and ``cleanup()`` hooks, used when the window is closed mid-install.
    ``resetup=True`` skips the choice and installs ``profile_default`` at once.
    """

    def __init__(
        self,
        root,
        *,
        app_home,
        profile_default,
        nvidia,
        installer,
        on_done,
        spawn=_default_spawn,
        resetup=False,
    ):
        self.root = root
        self.app_home = Path(app_home)
        self.nvidia = nvidia
        self.installer = installer
        self.on_done = on_done
        self.spawn = spawn
        self.resetup = resetup
        self.installing = False
        self.closed = False
        self.run_profile = None
        self.log_lines = deque(maxlen=LOG_TAIL)
        self._attempt = 0

        root.title(TITLE)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.choice = ttk.Frame(root, padding=16)
        self.progress = ttk.Frame(root, padding=16)
        self.failure = ttk.Frame(root, padding=16)
        self.warning = ttk.Frame(root, padding=16)

        default = profile_default if profile_default in core.PROFILES else None
        if default is None:
            default = "gpu" if nvidia.get("found") else "cpu"
        self.choice_var = tk.StringVar(value=default)
        self._build_choice()
        self._build_progress()
        self._build_failure()
        self._build_warning()

        if resetup:
            self._begin(default)
        else:
            self.choice_var.trace_add("write", lambda *_: self._refresh_checks())
            self._show(self.choice)
            self._refresh_checks()

    # --- construction ------------------------------------------------------

    def _show(self, frame) -> None:
        for f in (self.choice, self.progress, self.failure, self.warning):
            f.pack_forget()
        frame.pack(fill="both", expand=True)

    def _build_choice(self) -> None:
        f = self.choice
        self.explanation = ttk.Label(f, wraplength=480, justify="left")
        self.explanation.pack(anchor="w", pady=(0, 10))

        self.gpu_radio = ttk.Radiobutton(f, text=GPU_LABEL, value="gpu", variable=self.choice_var)
        self.gpu_radio.pack(anchor="w")
        if self.nvidia.get("found"):
            gpu_caption = f"{self.nvidia.get('name', '')} detected. About 2.6 GB download, about 5 GB on disk."
        else:
            gpu_caption = "About 2.6 GB download, about 5 GB on disk."
        self.gpu_caption = ttk.Label(f, text=gpu_caption, wraplength=460, justify="left")
        self.gpu_caption.pack(anchor="w", padx=24, pady=(0, 8))

        self.cpu_radio = ttk.Radiobutton(f, text=CPU_LABEL, value="cpu", variable=self.choice_var)
        self.cpu_radio.pack(anchor="w")
        self.cpu_caption = ttk.Label(
            f,
            text="About 300 MB download, about 1.4 GB on disk. " + CPU_CAPTION,
            wraplength=460,
            justify="left",
        )
        self.cpu_caption.pack(anchor="w", padx=24, pady=(0, 8))

        self.gpu_warning = ttk.Label(f, text=NO_GPU_WARNING, wraplength=480, foreground="#b45309")
        self.disk_label = ttk.Label(f, wraplength=480, justify="left")
        self.disk_label.pack(anchor="w", pady=(4, 0))
        self.error_label = ttk.Label(f, wraplength=480, justify="left", foreground="#b91c1c")
        self.error_label.pack(anchor="w", pady=(2, 8))

        buttons = ttk.Frame(f)
        buttons.pack(anchor="e", fill="x")
        self.quit_button = ttk.Button(buttons, text="Quit", command=self.on_close)
        self.quit_button.pack(side="right", padx=(8, 0))
        self.install_button = ttk.Button(buttons, text="Install", command=self.start_install)
        self.install_button.pack(side="right")

    def _build_progress(self) -> None:
        f = self.progress
        self.bar = ttk.Progressbar(f, length=480, maximum=100, mode="determinate")
        self.bar.pack(fill="x")
        self.status_var = tk.StringVar(value="Starting…")
        ttk.Label(f, textvariable=self.status_var, wraplength=480).pack(anchor="w", pady=6)
        self.log_toggle = ttk.Button(f, text="Show log", command=self._toggle_log)
        self.log_toggle.pack(anchor="w")
        self.log_text = tk.Text(f, height=12, width=70, state="disabled", wrap="none")
        self._log_visible = False

    def _build_failure(self) -> None:
        f = self.failure
        self.failure_label = ttk.Label(f, text="Setup failed.", wraplength=480)
        self.failure_label.pack(anchor="w")
        self.failure_text = tk.Text(f, height=14, width=70, state="disabled", wrap="none")
        self.failure_text.pack(fill="both", expand=True, pady=8)
        buttons = ttk.Frame(f)
        buttons.pack(anchor="e", fill="x")
        ttk.Button(buttons, text="Quit", command=self.quit).pack(side="right", padx=(8, 0))
        self.retry_button = ttk.Button(buttons, text="Retry", command=self.retry)
        self.retry_button.pack(side="right")

    def _build_warning(self) -> None:
        f = self.warning
        ttk.Label(f, text=CUDA_WARNING, wraplength=480, justify="left").pack(anchor="w", pady=8)
        ttk.Button(f, text="Continue", command=self._finish_ok).pack(anchor="e")

    # --- choice validation -------------------------------------------------

    def _refresh_checks(self) -> None:
        profile = self.choice_var.get()
        self.explanation.configure(text=EXPLANATION.format(gb=DOWNLOAD_GB[profile]))
        if profile == "gpu" and not self.nvidia.get("found"):
            self.gpu_warning.pack(anchor="w", before=self.disk_label)
        else:
            self.gpu_warning.pack_forget()

        env = core.env_dir()
        problems = []
        try:
            ok, free = core.disk_ok(env, profile)
        except OSError:
            ok, free = True, 0
        if free:
            self.disk_label.configure(text=f"Free space on this drive: {free / 1024**3:.1f} GB")
        if not ok:
            need = core.required_bytes(profile) / 1024**3
            problems.append(
                f"Not enough free disk space: {need:.1f} GB needed (including 2 GB headroom), "
                f"{free / 1024**3:.1f} GB free. Free up space and reopen CampaignScribe."
            )
        if not core.path_ok(env):
            problems.append(
                f"The install folder path is too long ({len(str(env))} characters; "
                f"the limit is {core.MAX_ENV_PATH_LEN}), which would break the speech engine. "
                "Use a Windows account with a shorter user name."
            )
        self.error_label.configure(text="\n".join(problems))
        self.install_button.state(["disabled"] if problems else ["!disabled"])

    # --- install -----------------------------------------------------------

    def _toggle_log(self) -> None:
        if self._log_visible:
            self.log_text.pack_forget()
            self.log_toggle.configure(text="Show log")
        else:
            self.log_text.pack(fill="both", expand=True, pady=(6, 0))
            self.log_toggle.configure(text="Hide log")
        self._log_visible = not self._log_visible

    def start_install(self) -> None:
        if not self.installing and not self.install_button.instate(["disabled"]):
            self._begin(self.choice_var.get())

    def retry(self) -> None:
        if not self.installing:
            self._begin(self.run_profile)

    def _begin(self, profile) -> None:
        self.run_profile = profile
        self.installing = True
        self._attempt += 1
        attempt = self._attempt
        self.log_lines.clear()
        self.bar.configure(value=0)
        self.status_var.set("Starting…")
        self._show(self.progress)
        self.spawn(lambda: self._worker(profile, attempt))

    def _post(self, fn, *args) -> None:
        try:
            self.root.after(0, fn, *args)
        except (tk.TclError, RuntimeError):
            pass

    def _worker(self, profile, attempt) -> None:
        def log_cb(line):
            self._post(self._on_log, attempt, line)

        def progress_cb(done, total, name):
            self._post(self._on_progress, attempt, done, total, name)

        try:
            result = self.installer(profile, log_cb, progress_cb)
        except Exception as exc:  # noqa: BLE001 - a crashing installer is a failed install
            result = _Failed(str(exc))
        self._post(self._on_result, attempt, profile, result)

    def _live(self, attempt) -> bool:
        return not self.closed and attempt == self._attempt

    def _on_log(self, attempt, line) -> None:
        if not self._live(attempt):
            return
        self.log_lines.append(line)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _on_progress(self, attempt, done, total, name) -> None:
        if not self._live(attempt):
            return
        self.bar.configure(value=100.0 * done / max(total, 1))
        if name:
            self.status_var.set(f"Installing {name} ({done}/{total})")

    def _on_result(self, attempt, profile, result) -> None:
        if not self._live(attempt):
            return
        self.installing = False
        if not getattr(result, "ok", False):
            self._show_failure(getattr(result, "message", ""))
        elif profile == "gpu" and not getattr(result, "cuda_ok", True):
            self._show(self.warning)
        else:
            self._finish_ok()

    def _show_failure(self, message) -> None:
        self.failure_label.configure(text="Setup failed." + (f" {message}" if message else ""))
        self.failure_text.configure(state="normal")
        self.failure_text.delete("1.0", "end")
        self.failure_text.insert("end", "\n".join(self.log_lines))
        self.failure_text.see("end")
        self.failure_text.configure(state="disabled")
        self._show(self.failure)

    def _finish_ok(self) -> None:
        self.closed = True
        self.on_done(self.run_profile)

    # --- closing -----------------------------------------------------------

    def quit(self) -> None:
        self.closed = True
        self.root.destroy()

    def on_close(self) -> None:
        if not self.installing:
            self.quit()
            return
        if not messagebox.askyesno(
            TITLE,
            "Setup is still installing. Quit and discard the partial installation?",
            parent=self.root,
        ):
            return
        self.closed = True
        for hook in ("cancel", "cleanup"):
            fn = getattr(self.installer, hook, None)
            if fn:
                fn()
        self.root.destroy()
