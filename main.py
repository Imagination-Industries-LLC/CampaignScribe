"""CampaignScribe entry point."""

from __future__ import annotations

import sys
import traceback
import types


def _install_optional_dep_stubs() -> None:
    """Inject a stub `k2` module so speechbrain.integrations.k2_fsa imports
    cleanly.

    speechbrain.integrations.k2_fsa does `import k2` at module top, and k2
    has no Windows wheel — without this, the eventual LazyModule wakeup
    (see _patch_speechbrain_lazymodule) crashes pyannote's diarization load.

    We only stub `k2` (not flair/spacy/etc.) because:
     - `k2_fsa/__init__.py` does a hard `import k2` that we need to satisfy.
     - Other optional deps are checked via `importlib.util.find_spec`, which
       cleanly returns None when the module is absent from sys.modules but
       raises `ValueError: X.__spec__ is None` if we leave a stub module
       without a spec. So for those: just leave sys.modules alone.

    The stub also needs a real `__spec__` so future find_spec("k2") calls
    return a spec instead of raising.
    """
    import importlib.machinery

    if "k2" not in sys.modules:
        mod = types.ModuleType("k2")
        mod.__spec__ = importlib.machinery.ModuleSpec("k2", loader=None)
        sys.modules["k2"] = mod


def _patch_speechbrain_lazymodule() -> None:
    r"""Patch speechbrain's LazyModule so a failed lazy import raises
    AttributeError (what `hasattr` expects) instead of ImportError.

    Workaround #2: speechbrain has a guard against being woken up by
    `inspect.py` walking sys.modules, but it does
    `importer_frame.filename.endswith("/inspect.py")` — broken on Windows where
    the path is `…\inspect.py`. So the guard never fires, ImportError leaks
    out of `__getattr__`, and `inspect.getmodule` crashes the whole pyannote
    diarization load chain.

    We replace `__getattr__` with a wrapper that catches ImportError and
    re-raises AttributeError. `hasattr` then returns False cleanly and
    `inspect.getmodule` keeps walking.
    """
    try:
        import speechbrain.utils.importutils as siu  # noqa
    except Exception:
        return

    orig_getattr = siu.LazyModule.__getattr__

    def patched_getattr(self, attr):
        try:
            return orig_getattr(self, attr)
        except ImportError:
            raise AttributeError(attr) from None

    siu.LazyModule.__getattr__ = patched_getattr


_install_optional_dep_stubs()
_patch_speechbrain_lazymodule()


def main() -> int:
    try:
        from app.config import get_app_data_dir

        get_app_data_dir()  # ensure %APPDATA%\CampaignScribe exists
        from app.data import db as _db

        _db.init_db()
        from app.ui.app_window import AppWindow

        # Relaunch loop: a theme change calls AppWindow.request_rebuild(), which
        # sets _rebuild_requested and destroys the window. We then construct a
        # fresh AppWindow (apply_theme re-reads theme_mode and applies the new
        # palette). Any other exit (window close) ends the loop.
        while True:
            win = AppWindow()
            win.mainloop()
            if not getattr(win, "_rebuild_requested", False):
                break
        return 0
    except Exception:
        traceback.print_exc()
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "CampaignScribe — fatal error",
                "An unexpected error prevented startup:\n\n" + traceback.format_exc(),
            )
            root.destroy()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
