"""Start-menu entry point: run `{app}\\python\\pythonw.exe {app}\\bootstrap\\launcher.py`.

Standard library only. Decides between launching the app and first-run setup.

Dev checkout: when ``{app}\\python`` does not exist, the environment is still
created from ``python.exe`` next to ``sys.executable`` (see ``install.Installer``),
so the flow can be exercised manually without an installed layout.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_APP_HOME = Path(__file__).resolve().parent.parent
if str(_APP_HOME) not in sys.path:  # running as a script: sys.path[0] is bootstrap/, not {app}
    sys.path.insert(0, str(_APP_HOME))

from bootstrap import core, install  # noqa: E402
from bootstrap.core import decide, launch_command  # noqa: E402

try:
    from bootstrap.setup_window import SetupWindow
except ImportError:  # tkinter missing: setup cannot show, launch path still works
    SetupWindow = None


def _env_python(name: str) -> Path:
    return core.env_dir() / "Scripts" / name


def _new_root():
    import tkinter as tk

    return tk.Tk()


def _native_message(title: str, text: str) -> None:
    """A message box that needs no tkinter (Windows only; silently skipped elsewhere)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    except Exception:  # noqa: BLE001 - best effort, nothing else to fall back to
        pass


def _log_error(text: str) -> None:
    try:
        path = core.setup_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    except OSError:
        pass


def _error_box(title: str, text: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        try:
            messagebox.showerror(title, text, parent=root)
        finally:
            root.destroy()
    except Exception:  # noqa: BLE001 - no usable Tk: fall back to the native box
        _native_message(title, text)


def _launch_app(app_home: Path) -> bool:
    """Start the app; on failure log it, tell the user, and return False."""
    argv, env = launch_command(_env_python("pythonw.exe"), app_home)
    try:
        subprocess.Popen(  # noqa: S603  # nosec B603 - fixed argv, no shell
            argv,
            env=env,
            cwd=str(app_home),
            creationflags=core.no_window_flags(),
        )
    except OSError as exc:
        text = (
            f"CampaignScribe could not start: {exc}\n\nEnvironment: {core.env_dir()}\n"
            "Reinstalling or switching the speech engine in Settings may repair it."
        )
        _log_error(text)
        _error_box("CampaignScribe", text)
        return False
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="launcher")
    parser.add_argument("--switch", choices=core.PROFILES, default=None)
    args = parser.parse_args(argv)

    app_home = Path(__file__).resolve().parent.parent
    action, profile = decide(
        core.read_state(), app_home, _env_python("pythonw.exe").exists(), args.switch
    )

    if action == "launch":
        return 0 if _launch_app(app_home) else 3

    if SetupWindow is None:
        text = "CampaignScribe setup needs tkinter, which is missing from the bundled Python."
        _log_error(text)
        _native_message("CampaignScribe", text)
        return 2
    root = _new_root()
    result = {"done": False, "launched": False}

    def on_done(_profile):
        result["done"] = True
        root.destroy()
        result["launched"] = _launch_app(app_home)

    SetupWindow(
        root,
        app_home=app_home,
        profile_default=profile,
        nvidia=core.detect_nvidia(),
        installer=install.make_installer(app_home),
        on_done=on_done,
        resetup=(action == "resetup"),
    )
    root.mainloop()
    if not result["done"]:
        return 1
    return 0 if result["launched"] else 3


if __name__ == "__main__":
    sys.exit(main())
