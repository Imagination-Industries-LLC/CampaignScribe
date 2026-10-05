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


def _launch_app(app_home: Path) -> None:
    argv, env = launch_command(_env_python("pythonw.exe"), app_home)
    subprocess.Popen(  # noqa: S603  # nosec B603 - fixed argv, no shell
        argv,
        env=env,
        cwd=str(app_home),
        creationflags=core.no_window_flags(),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="launcher")
    parser.add_argument("--switch", choices=core.PROFILES, default=None)
    args = parser.parse_args(argv)

    app_home = Path(__file__).resolve().parent.parent
    action, profile = decide(
        core.read_state(), app_home, _env_python("pythonw.exe").exists(), args.switch
    )

    if action == "launch":
        _launch_app(app_home)
        return 0

    if SetupWindow is None:
        return 2
    root = _new_root()
    result = {"done": False}

    def on_done(_profile):
        result["done"] = True
        root.destroy()
        _launch_app(app_home)

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
    return 0 if result["done"] else 1


if __name__ == "__main__":
    sys.exit(main())
