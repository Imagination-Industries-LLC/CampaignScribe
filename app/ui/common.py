"""Tiny UI helpers shared across tabs."""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional


def open_path_native(path: str) -> None:
    """Open a file or folder in the OS default app."""
    if not path:
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def reveal_in_folder(path: str) -> None:
    """Open the OS file browser at a file's containing folder, selecting the
    file where the platform supports it."""
    if not path:
        return
    try:
        if sys.platform.startswith("win"):
            if os.path.isfile(path):
                # explorer returns exit code 1 even on success; don't check it.
                subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
            else:
                os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path] if os.path.isfile(path) else ["open", path])
        else:
            target = path if os.path.isdir(path) else (os.path.dirname(path) or ".")
            subprocess.Popen(["xdg-open", target])
    except Exception:
        pass


def make_readonly(text: tk.Text) -> None:
    """Make a tk.Text widget read-only but still selectable/copyable.
    Keeps state='normal' (so selection works) and blocks edit keystrokes while
    allowing copy (Ctrl+C), select-all (Ctrl+A), and navigation."""
    def _block(event):
        ctrl = bool(event.state & 0x4)
        if ctrl and event.keysym.lower() in ("c", "a"):
            return None
        if event.keysym in (
            "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
            "Shift_L", "Shift_R", "Control_L", "Control_R",
        ):
            return None
        return "break"
    text.bind("<Key>", _block)


class ScrollableFrame(ttk.Frame):
    """A ttk.Frame that contains a vertically scrollable inner frame."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = ttk.Frame(self.canvas)
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    def _on_inner_configure(self, _evt):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, evt):
        self.canvas.itemconfig(self.inner_id, width=evt.width)

    def _on_mousewheel(self, evt):
        # Only scroll when the pointer is over us
        if not str(evt.widget).startswith(str(self.canvas)):
            return
        self.canvas.yview_scroll(int(-1 * (evt.delta / 120)), "units")


class LabeledEntry(ttk.Frame):
    def __init__(self, master, label: str, value: str = "", width: int = 30,
                 on_change: Optional[Callable[[str], None]] = None):
        super().__init__(master)
        ttk.Label(self, text=label).pack(side="left")
        self.var = tk.StringVar(value=value)
        ttk.Entry(self, textvariable=self.var, width=width).pack(side="left", padx=4)
        if on_change:
            self.var.trace_add("write", lambda *_: on_change(self.var.get()))

    def get(self) -> str:
        return self.var.get()

    def set(self, v: str) -> None:
        self.var.set(v)


def short_path(p: str, max_len: int = 60) -> str:
    if len(p) <= max_len:
        return p
    return "…" + p[-(max_len - 1):]


class TranscriptEditorDialog(tk.Toplevel):
    """Light modal transcript viewer/editor. Loads a .txt, lets the user fix
    diarization/speaker-label mistakes, and saves back atomically."""

    def __init__(self, master, path: str):
        super().__init__(master)
        self.path = path
        self.title(f"Edit Transcript — {os.path.basename(path)}")
        self.transient(master)
        self.grab_set()
        self.geometry("900x640")

        top = ttk.Frame(self)
        top.pack(side="top", fill="x", padx=8, pady=6)
        ttk.Label(top, text=short_path(path, 90)).pack(side="left")

        wrap = ttk.Frame(self)
        wrap.pack(side="top", fill="both", expand=True, padx=8, pady=4)
        self.text = tk.Text(wrap, wrap="word", undo=True)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        try:
            with open(path, "r", encoding="utf-8") as f:
                self.text.insert("1.0", f.read())
        except Exception as e:
            messagebox.showerror("CampaignScribe", f"Could not open transcript:\n{e}", parent=self)
            self.destroy()
            return

        btns = ttk.Frame(self)
        btns.pack(side="bottom", fill="x", padx=8, pady=8)
        ttk.Button(btns, text="Save", command=self._save).pack(side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=4)

    def _save(self):
        content = self.text.get("1.0", "end-1c")
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except Exception as e:
            messagebox.showerror("CampaignScribe", f"Could not save:\n{e}", parent=self)
            return
        self.destroy()


def open_transcript_editor(master, path: str) -> None:
    """Open the transcript editor on a .txt path, with a friendly guard."""
    if not path or not os.path.isfile(path):
        messagebox.showinfo("CampaignScribe", "Select a transcript (.txt) file first.")
        return
    dlg = TranscriptEditorDialog(master, path)
    master.wait_window(dlg)
