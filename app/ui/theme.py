"""
CampaignScribe — Mike's DM Tools Design System adoption.

This module owns *every* visual decision in the app. Per-tab code should
never set colors, fonts, or pads inline — instead reference named styles
declared here (e.g. ``ttk.Button(..., style="Accent.TButton")``).

Architecture
------------
* All design tokens live as module-level constants (``COLOR_*``, ``FONT_*``,
  ``S_*`` for spacing, ``R_*`` for radii — note: ttk has no real radius,
  these are referenced by ad-hoc widgets that want rounded canvases).
* :func:`apply_theme` configures :class:`ttk.Style` for every widget class
  the app uses *and* registers every named style the tab modules reference.
* A ``THEME_NAME`` variant switcher (``"dark"`` / ``"light"``) lets us swap
  palettes from a single setting later; the default is ``"dark"`` to match
  the rest of the MDMT lineup. Both palettes share the same accent (rune
  cyan) so the brand stays consistent regardless of mode.

How to extend
-------------
* New color: add a constant, then reference it from inside
  :func:`_configure_styles` (or wherever it is consumed).
* New widget style: declare a ``NAME = "Accent.TButton"`` constant for the
  callers to import, then configure it inside :func:`_configure_styles`.
* New variant: add another branch to :data:`_PALETTES` and call
  ``set_theme_variant("name")`` before constructing the window.

PyInstaller / frozen mode
-------------------------
Embedded fonts live in ``assets/fonts/``. When frozen, Tk reads them via
:class:`pathlib.Path` resolved against ``sys._MEIPASS``; we register them
with the platform font system before any widget is constructed.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Literal

# ============================================================================
# Variant + palette
# ============================================================================

ThemeVariant = Literal["dark", "light"]

_active_variant: ThemeVariant = "dark"


def set_theme_variant(variant: ThemeVariant) -> None:
    """Choose between ``"dark"`` (default) and ``"light"`` before
    :func:`apply_theme` is called. Has no effect after styles are configured;
    rebuild the window if you need to switch at runtime."""
    global _active_variant
    if variant not in ("dark", "light"):
        raise ValueError(f"Unknown theme variant: {variant!r}")
    _active_variant = variant


_PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        # Surfaces
        "BG": "#0D1018",  # app background (obsidian)
        "BG_CHROME": "#0A0D14",  # title bar, status bar
        "BG_RAISED": "#1A2030",  # frames, labelframe interior
        "BG_INPUT": "#07080D",  # entry, combobox, listbox, text
        "BG_TAB_IDLE": "#0D1018",
        "BG_TAB_ACTIVE": "#1A2030",
        # Borders
        "BORDER": "#2E3650",
        "BORDER_HI": "#3D4668",
        "BORDER_RUNE": "#1DC8E6",  # at 35% alpha via stipple/blend
        # Text
        "FG": "#DFE4F2",  # primary
        "FG_DIM": "#B4BDD6",
        "FG_MUTED": "#8892B0",  # tab idle, secondary
        "FG_DISABLED": "#5E6788",
        # Accents
        "ACCENT": "#1DC8E6",  # rune-500 — primary action
        "ACCENT_HI": "#4DE3FF",  # rune-300 — hover, active tab
        "ACCENT_DIM": "#0A7A93",  # rune-700
        "NEBULA": "#7D5BFF",  # speaker avatars, magic chip
        # Semantic
        "EMBER": "#E8A53D",  # warn, banner, draft
        "MOSS": "#3EA663",  # success, GPU ready
        "BLOOD": "#C0392B",  # danger, error
    },
    "light": {
        # Parchment-mode (kept for parity with the design system's daylight variant)
        "BG": "#ECE6D3",
        "BG_CHROME": "#E0D8C0",
        "BG_RAISED": "#F6F0DD",
        "BG_INPUT": "#FDF8E7",
        "BG_TAB_IDLE": "#DDD4B8",
        "BG_TAB_ACTIVE": "#F6F0DD",
        "BORDER": "#B8A983",
        "BORDER_HI": "#8E7D56",
        "BORDER_RUNE": "#0A7A93",
        "FG": "#1A1812",
        "FG_DIM": "#3A3325",
        "FG_MUTED": "#5E533C",
        "FG_DISABLED": "#8A7D5E",
        "ACCENT": "#0A7A93",
        "ACCENT_HI": "#0A9FBC",
        "ACCENT_DIM": "#085F73",
        "NEBULA": "#4A2BB8",
        "EMBER": "#A86B15",
        "MOSS": "#1F5C37",
        "BLOOD": "#7A1D18",
    },
}


def color(name: str) -> str:
    """Look up a token in the active palette. Raises KeyError on typos —
    intentional, so we never silently fall back to a wrong color."""
    return _PALETTES[_active_variant][name]


# ============================================================================
# Typography
# ============================================================================

# Fonts ship with the bundle in ``assets/fonts/`` so PyInstaller users get
# consistent rendering. Each tuple is (family, size, weight, slant) — Tk
# applies them via ``tkfont.Font(family=..., size=..., weight=..., slant=...)``.
#
# Family fallback chain: if the embedded font isn't available, Tk falls
# back to the next family in the system's font matcher. Segoe UI is the
# canonical Windows fallback.

FONT_DISPLAY_FAMILY = "Cinzel"  # carved-stone display, eyebrows, headers
FONT_SANS_FAMILY = "Inter"  # everything functional
FONT_MONO_FAMILY = "JetBrains Mono"  # timestamps, JSON, copyable IDs
FONT_SERIF_FAMILY = "Cormorant Garamond"  # italicized lore lines only
FONT_FALLBACK = "Segoe UI"

# Size scale (point sizes — ttk uses points by default on Windows)
FS_XS = 9
FS_SM = 10
FS_BASE = 11
FS_MD = 12
FS_LG = 14
FS_XL = 18
FS_2XL = 22


def _font(family: str, size: int, weight: str = "normal", slant: str = "roman") -> tuple:
    """Build a valid Tkinter font spec: ``(family, size, *styles)``.

    Tk resolves ``family`` via the system/registered font matcher and falls
    back to a default face automatically if the family is missing (we bundle
    the four families in ``assets/fonts/``, so they resolve). A fallback
    family CANNOT be embedded in the tuple — Tk requires element 2 to be the
    integer size, so ``(family, FALLBACK, size, ...)`` raises a TclError."""
    styles = []
    if weight == "bold":
        styles.append("bold")
    if slant == "italic":
        styles.append("italic")
    if styles:
        return (family, size, " ".join(styles))
    return (family, size)


# Named font roles — the tab modules import these so a future family swap
# (e.g., licensing a real bespoke display face) is a one-line change here.
FONT_BODY = _font(FONT_SANS_FAMILY, FS_BASE)
FONT_BODY_BOLD = _font(FONT_SANS_FAMILY, FS_BASE, weight="bold")
FONT_BUTTON = _font(FONT_SANS_FAMILY, FS_BASE, weight="bold")
FONT_TITLE = _font(FONT_DISPLAY_FAMILY, FS_XL, weight="bold")
FONT_HEADER = _font(FONT_DISPLAY_FAMILY, FS_LG, weight="bold")
FONT_EYEBROW = _font(FONT_DISPLAY_FAMILY, FS_XS, weight="bold")
FONT_MONO = _font(FONT_MONO_FAMILY, FS_SM)
FONT_MONO_LG = _font(FONT_MONO_FAMILY, FS_BASE)
FONT_LORE = _font(FONT_SERIF_FAMILY, FS_MD, slant="italic")
FONT_STATUS = _font(FONT_MONO_FAMILY, FS_XS)
FONT_TAB = _font(FONT_SANS_FAMILY, FS_BASE, weight="bold")


# ============================================================================
# Spacing & geometry
# ============================================================================
# 4px scale. Use these everywhere instead of magic numbers.
S_1, S_2, S_3, S_4, S_5, S_6, S_7, S_8 = 4, 8, 12, 16, 20, 24, 32, 40

PAD_BUTTON = (S_3, S_2)  # (x, y) — ttk applies as (left, top, right, bottom)
PAD_ENTRY = (S_2, S_2)
PAD_TAB = (S_3, S_2)
PAD_FRAME = S_4
PAD_LABELFRAME = (S_3, S_3)

ROW_HEIGHT_TREE = 28
ROW_HEIGHT_LIST = 24


# ============================================================================
# Named ttk style identifiers — import these from tab modules
# ============================================================================

# Buttons
BTN_ACCENT = "Accent.TButton"
BTN_GHOST = "Ghost.TButton"
BTN_DANGER = "Danger.TButton"
BTN_LINK = "Link.TButton"

# Labels
LBL_EYEBROW = "Eyebrow.TLabel"
LBL_TITLE = "Title.TLabel"
LBL_HEADER = "Header.TLabel"
LBL_LORE = "Lore.TLabel"
LBL_MONO = "Mono.TLabel"
LBL_DIM = "Dim.TLabel"
LBL_STATUS_OK = "Status.OK.TLabel"
LBL_STATUS_WARN = "Status.Warn.TLabel"
LBL_STATUS_ERR = "Status.Err.TLabel"
LBL_STATUS_INFO = "Status.Info.TLabel"

# LabelFrames
LF_RUNE = "Rune.TLabelframe"
LF_RUNE_LABEL = "Rune.TLabelframe.Label"


# ============================================================================
# Public entry point
# ============================================================================


def apply_theme(root: tk.Tk) -> None:
    """Configure ttk styles, classic-Tk colors, fonts, and the window icon.

    Call this once at the top of ``AppWindow.__init__``, *before* any
    widget is constructed. Re-calling is safe but doesn't pick up variant
    changes mid-flight; rebuild the window for that.
    """
    _register_bundled_fonts(root)
    _configure_root_window(root)
    _configure_styles(root)
    _configure_tk_widget_defaults(root)
    _set_window_icon(root)


# ============================================================================
# Internals
# ============================================================================


def _asset_path(*parts: str) -> Path:
    """Resolve a path under ``assets/``. Works in dev mode (cwd = repo
    root) and in PyInstaller-frozen mode (``sys._MEIPASS``)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent.parent
    return base.joinpath("assets", *parts)


def _register_bundled_fonts(root: tk.Tk) -> None:
    """Best-effort font registration. Tk on Windows reads system-installed
    fonts; ``Pillow`` is used to import font files at runtime when present.
    Missing files are silently skipped — :func:`_font` falls back to Segoe UI."""
    fonts_dir = _asset_path("fonts")
    if not fonts_dir.is_dir():
        return
    try:
        # On Windows, AddFontResourceEx makes the font available process-wide
        # without polluting the user's font collection.
        import ctypes

        for path in fonts_dir.glob("*.[ot]tf"):
            ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, 0)  # FR_PRIVATE
    except Exception:
        # On non-Windows or missing Pillow/ctypes, just continue without
        # the embedded fonts; the family fallback handles it.
        pass


def _configure_root_window(root: tk.Tk) -> None:
    """Set the top-level window background so frames inherit it correctly."""
    root.configure(background=color("BG"))


def _set_window_icon(root: tk.Tk) -> None:
    """Apply the multi-resolution icon. Wrapped in try/except because
    older Windows or missing assets/icon.ico should not crash the app."""
    try:
        ico = _asset_path("icon.ico")
        if ico.is_file():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass


def _configure_styles(root: tk.Tk) -> None:
    """Configure every ttk widget class the app uses, then every named style.

    Reads from the active palette via :func:`color`."""
    style = ttk.Style(root)

    # Start from 'clam' — the only built-in theme that lets us fully restyle
    # buttons/treeview/tabs. 'vista' / 'xpnative' refuse most overrides.
    style.theme_use("clam")

    bg = color("BG")
    bg_raised = color("BG_RAISED")
    bg_chrome = color("BG_CHROME")
    bg_input = color("BG_INPUT")
    bg_tab_idle = color("BG_TAB_IDLE")
    bg_tab_active = color("BG_TAB_ACTIVE")
    border = color("BORDER")
    border_hi = color("BORDER_HI")
    fg = color("FG")
    fg_dim = color("FG_DIM")
    fg_muted = color("FG_MUTED")
    fg_disabled = color("FG_DISABLED")
    accent = color("ACCENT")
    accent_hi = color("ACCENT_HI")
    accent_dim = color("ACCENT_DIM")
    ember = color("EMBER")
    moss = color("MOSS")
    blood = color("BLOOD")

    # ---- Base widget classes ----

    style.configure(
        ".",
        background=bg,
        foreground=fg,
        fieldbackground=bg_input,
        bordercolor=border,
        lightcolor=border,
        darkcolor=border,
        troughcolor=bg_input,
        focuscolor=accent,
        selectbackground=accent_dim,
        selectforeground=fg,
        insertcolor=accent_hi,
        font=FONT_BODY,
    )

    style.configure("TFrame", background=bg)
    style.configure("Chrome.TFrame", background=bg_chrome)
    style.configure("Raised.TFrame", background=bg_raised)

    # ---- Label ----
    style.configure("TLabel", background=bg, foreground=fg, font=FONT_BODY)

    style.configure(
        LBL_EYEBROW,
        background=bg,
        foreground=accent,
        font=FONT_EYEBROW,
    )
    style.configure(LBL_TITLE, background=bg, foreground=fg, font=FONT_TITLE)
    style.configure(LBL_HEADER, background=bg, foreground=fg, font=FONT_HEADER)
    style.configure(LBL_LORE, background=bg, foreground=fg_muted, font=FONT_LORE)
    style.configure(LBL_MONO, background=bg, foreground=fg_dim, font=FONT_MONO)
    style.configure(LBL_DIM, background=bg, foreground=fg_muted, font=FONT_BODY)
    style.configure(LBL_STATUS_OK, background=bg_chrome, foreground=moss, font=FONT_STATUS)
    style.configure(LBL_STATUS_WARN, background=bg_chrome, foreground=ember, font=FONT_STATUS)
    style.configure(LBL_STATUS_ERR, background=bg_chrome, foreground=blood, font=FONT_STATUS)
    style.configure(LBL_STATUS_INFO, background=bg_chrome, foreground=fg_muted, font=FONT_STATUS)

    # ---- Button ----
    style.configure(
        "TButton",
        background=bg_raised,
        foreground=fg,
        bordercolor=border_hi,
        lightcolor=bg_raised,
        darkcolor=bg_raised,
        padding=PAD_BUTTON,
        font=FONT_BUTTON,
        relief="solid",
        borderwidth=1,
    )
    style.map(
        "TButton",
        background=[("active", border), ("pressed", bg_input), ("disabled", bg_raised)],
        foreground=[("disabled", fg_disabled)],
        bordercolor=[("active", accent_hi), ("focus", accent_hi)],
    )

    style.configure(
        BTN_ACCENT,
        background=accent,
        foreground="#03222A",
        bordercolor=accent,
        lightcolor=accent,
        darkcolor=accent_dim,
        padding=PAD_BUTTON,
        font=FONT_BUTTON,
    )
    style.map(
        BTN_ACCENT,
        background=[("active", accent_hi), ("pressed", accent_dim), ("disabled", border)],
        foreground=[("disabled", fg_disabled)],
        bordercolor=[("active", accent_hi)],
    )

    style.configure(
        BTN_GHOST,
        background=bg,
        foreground=accent_hi,
        bordercolor=accent,
        padding=PAD_BUTTON,
        font=FONT_BUTTON,
    )
    style.map(
        BTN_GHOST,
        background=[("active", bg_raised)],
        foreground=[("active", accent_hi), ("disabled", fg_disabled)],
    )

    style.configure(
        BTN_DANGER,
        background=blood,
        foreground="#FFFFFF",
        bordercolor=blood,
        padding=PAD_BUTTON,
        font=FONT_BUTTON,
    )
    style.map(
        BTN_DANGER,
        background=[("active", "#EF6A6A"), ("pressed", "#8B2A1F")],
    )

    style.configure(
        BTN_LINK,
        background=bg,
        foreground=accent_hi,
        bordercolor=bg,
        padding=(S_1, S_1),
        font=FONT_BODY,
        relief="flat",
    )
    style.map(
        BTN_LINK,
        foreground=[("active", accent), ("disabled", fg_disabled)],
        background=[("active", bg)],
    )

    # ---- Entry / Spinbox ----
    style.configure(
        "TEntry",
        fieldbackground=bg_input,
        foreground=fg,
        bordercolor=border,
        lightcolor=border,
        darkcolor=border,
        insertcolor=accent_hi,
        padding=PAD_ENTRY,
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", accent), ("invalid", blood)],
        lightcolor=[("focus", accent)],
        darkcolor=[("focus", accent)],
    )

    style.configure(
        "TSpinbox",
        fieldbackground=bg_input,
        foreground=fg,
        bordercolor=border,
        arrowcolor=accent_hi,
        padding=PAD_ENTRY,
    )
    style.map(
        "TSpinbox",
        bordercolor=[("focus", accent)],
    )

    # ---- Combobox ----
    style.configure(
        "TCombobox",
        fieldbackground=bg_input,
        background=bg_raised,
        foreground=fg,
        bordercolor=border,
        arrowcolor=accent_hi,
        padding=PAD_ENTRY,
        selectbackground=accent_dim,
        selectforeground=fg,
    )
    style.map(
        "TCombobox",
        bordercolor=[("focus", accent)],
        fieldbackground=[("readonly", bg_input)],
        foreground=[("readonly", fg)],
    )
    # The dropdown listbox is configured separately — Tk doesn't expose
    # it through ttk.Style. ``option_add`` reaches it.
    root.option_add("*TCombobox*Listbox.background", bg_input)
    root.option_add("*TCombobox*Listbox.foreground", fg)
    root.option_add("*TCombobox*Listbox.selectBackground", accent_dim)
    root.option_add("*TCombobox*Listbox.selectForeground", fg)
    root.option_add("*TCombobox*Listbox.font", FONT_BODY)

    # ---- Checkbutton / Radiobutton ----
    style.configure(
        "TCheckbutton",
        background=bg,
        foreground=fg,
        indicatorbackground=bg_input,
        indicatorforeground=accent_hi,
        focuscolor=accent,
        font=FONT_BODY,
        padding=(S_2, S_1),
    )
    style.map(
        "TCheckbutton",
        background=[("active", bg)],
        indicatorbackground=[("selected", accent), ("active", bg_raised)],
    )

    style.configure(
        "TRadiobutton",
        background=bg,
        foreground=fg,
        indicatorbackground=bg_input,
        focuscolor=accent,
        font=FONT_BODY,
        padding=(S_2, S_1),
    )
    style.map(
        "TRadiobutton",
        background=[("active", bg)],
        indicatorforeground=[("selected", accent)],
    )

    # ---- Notebook (tabs) ----
    style.configure(
        "TNotebook",
        background=bg_chrome,
        bordercolor=border,
        tabmargins=(S_3, S_2, S_3, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=bg_tab_idle,
        foreground=fg_muted,
        bordercolor=border,
        lightcolor=bg_tab_idle,
        padding=PAD_TAB,
        font=FONT_TAB,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", bg_tab_active), ("active", bg_raised)],
        foreground=[("selected", fg), ("active", fg_dim)],
        lightcolor=[("selected", bg_tab_active)],
        bordercolor=[("selected", accent)],
    )

    # ---- LabelFrame ----
    style.configure(
        "TLabelframe",
        background=bg,
        bordercolor=border,
        lightcolor=border,
        darkcolor=border,
        relief="solid",
        borderwidth=1,
        padding=PAD_LABELFRAME,
    )
    style.configure(
        "TLabelframe.Label",
        background=bg,
        foreground=accent,
        font=FONT_EYEBROW,
    )

    # Variant used by tab modules that want a stronger "rune frame" treatment
    style.configure(
        LF_RUNE,
        background=bg_raised,
        bordercolor=accent_dim,
        lightcolor=accent_dim,
        darkcolor=accent_dim,
        relief="solid",
        borderwidth=1,
        padding=PAD_LABELFRAME,
    )
    style.configure(
        LF_RUNE_LABEL,
        background=bg_raised,
        foreground=accent_hi,
        font=FONT_EYEBROW,
    )

    # ---- Treeview ----
    style.configure(
        "Treeview",
        background=bg_input,
        fieldbackground=bg_input,
        foreground=fg,
        bordercolor=border,
        rowheight=ROW_HEIGHT_TREE,
        font=FONT_BODY,
    )
    style.map(
        "Treeview",
        background=[("selected", accent_dim)],
        foreground=[("selected", fg)],
    )
    style.configure(
        "Treeview.Heading",
        background=bg_chrome,
        foreground=accent,
        font=FONT_EYEBROW,
        relief="flat",
        padding=(S_3, S_2),
        bordercolor=border,
    )
    style.map(
        "Treeview.Heading",
        background=[("active", bg_raised)],
        foreground=[("active", accent_hi)],
    )

    # ---- Progressbar ----
    style.configure(
        "TProgressbar",
        background=accent,
        troughcolor=bg_input,
        bordercolor=border,
        lightcolor=accent,
        darkcolor=accent_dim,
    )

    # ---- Scrollbar ----
    style.configure(
        "Vertical.TScrollbar",
        background=bg_raised,
        troughcolor=bg,
        bordercolor=border,
        arrowcolor=fg_muted,
    )
    style.map(
        "Vertical.TScrollbar",
        background=[("active", border_hi)],
        arrowcolor=[("active", accent_hi)],
    )
    style.configure(
        "Horizontal.TScrollbar",
        background=bg_raised,
        troughcolor=bg,
        bordercolor=border,
        arrowcolor=fg_muted,
    )
    style.map(
        "Horizontal.TScrollbar",
        background=[("active", border_hi)],
        arrowcolor=[("active", accent_hi)],
    )

    # ---- Separator ----
    style.configure("TSeparator", background=border)

    # ---- PanedWindow ----
    style.configure("TPanedwindow", background=bg)
    style.configure("Sash", background=border, sashthickness=4)


def _configure_tk_widget_defaults(root: tk.Tk) -> None:
    """Configure the *classic* Tk widgets (not ttk) — Listbox, Text, Menu, Canvas.
    These don't participate in ttk.Style; we set their defaults via ``option_add``.
    """
    bg = color("BG")
    bg_input = color("BG_INPUT")
    bg_chrome = color("BG_CHROME")
    fg = color("FG")
    accent = color("ACCENT")
    accent_dim = color("ACCENT_DIM")

    # Listbox
    root.option_add("*Listbox.background", bg_input)
    root.option_add("*Listbox.foreground", fg)
    root.option_add("*Listbox.selectBackground", accent_dim)
    root.option_add("*Listbox.selectForeground", fg)
    root.option_add("*Listbox.borderWidth", 1)
    root.option_add("*Listbox.highlightThickness", 0)
    root.option_add("*Listbox.relief", "solid")
    root.option_add("*Listbox.font", FONT_BODY)
    root.option_add("*Listbox.activeStyle", "none")

    # Text
    root.option_add("*Text.background", bg_input)
    root.option_add("*Text.foreground", fg)
    root.option_add("*Text.selectBackground", accent_dim)
    root.option_add("*Text.selectForeground", fg)
    root.option_add("*Text.insertBackground", accent)
    root.option_add("*Text.borderWidth", 1)
    root.option_add("*Text.highlightThickness", 0)
    root.option_add("*Text.relief", "solid")
    root.option_add("*Text.font", FONT_MONO_LG)

    # Menu (right-click context menus, settings dialog menus)
    root.option_add("*Menu.background", bg_chrome)
    root.option_add("*Menu.foreground", fg)
    root.option_add("*Menu.activeBackground", accent_dim)
    root.option_add("*Menu.activeForeground", fg)
    root.option_add("*Menu.borderWidth", 1)
    root.option_add("*Menu.relief", "solid")
    root.option_add("*Menu.font", FONT_BODY)

    # Toplevel (dialogs, including the settings dialog)
    root.option_add("*Toplevel.background", bg)

    # Canvas (used by status-bar dot, any ad-hoc drawing)
    root.option_add("*Canvas.background", bg)
    root.option_add("*Canvas.highlightThickness", 0)


# ============================================================================
# Status-bar helper
# ============================================================================


class StatusLevel:
    """The four states the status bar reports. Each maps to a named label
    style + a colored dot."""

    OK = ("OK", LBL_STATUS_OK, "MOSS")
    WARN = ("WARN", LBL_STATUS_WARN, "EMBER")
    ERR = ("ERR", LBL_STATUS_ERR, "BLOOD")
    INFO = ("INFO", LBL_STATUS_INFO, "FG_MUTED")


def make_status_dot(parent: tk.Widget, level: tuple, size: int = 10) -> tk.Canvas:
    """Build a small filled-circle Canvas as the colored status indicator.
    Use with :data:`StatusLevel.OK` / ``.WARN`` / ``.ERR`` / ``.INFO``."""
    _, _, color_token = level
    c = tk.Canvas(
        parent, width=size + 4, height=size + 4, background=color("BG_CHROME"), highlightthickness=0
    )
    pad = 2
    c.create_oval(
        pad, pad, pad + size, pad + size, fill=color(color_token), outline=color(color_token)
    )
    return c
