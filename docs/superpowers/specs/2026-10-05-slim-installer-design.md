# Slim Installer & First-Run Setup (Phase 5a) — Design

- **Feature:** Phase 5, part a, of #1 Auto-Update & Slim Distribution (planning issue CampaignScribe-planning#14)
- **Date:** 2026-10-05
- **Supersedes:** §1–§2 of the May 2026 spec "Auto-Update & Slim Distribution". Auto-update is Phase 5b; signing and release CI are Phase 5c.
- **Prerequisite:** "Step 0", which moves development and CI to Python 3.13, is merged first.
- **Evidence (spike, 2026-10-05):** the full stack runs on official CPython 3.13.16 with no version pin changes.
  - The test suite passes (562).
  - GPU transcription is identical to the 3.11 baseline.
  - The CPU build works (60 s of audio in about 70 s).
  - Environment sizes: GPU about 5.1 GB, CPU about 1.4 GB.
  - Windows' 260-character path limit breaks `import torch` when the environment sits under a very deep path.

## Decisions (Mike, 2026-10-05)

1. **Python:** the **official python.org** 3.13 runtime, shipped privately with the app. uv is the backup only.
2. **Install scope:** a wizard choice between "Install for me only", the default with no admin, going to `%LOCALAPPDATA%\Programs\CampaignScribe`, and "Install for all users", which needs admin and goes to `%ProgramFiles%\CampaignScribe`.
3. **Installer tool:** **Inno Setup**, an independent open-source tool.
4. **License:** GPL-3.0-only, © Imagination Industries LLC. The installer shows it.
5. **Heavy ML libraries** (torch, CUDA and friends) are installed on first run, with a GPU/CPU choice.

## Goals

- **A small installer:** about 200 MB, down from about 4.9 GB today. It installs without admin by default and looks and behaves like a normal Windows app installer, with a wizard, a Start-menu entry, an "Installed apps" entry and an uninstaller.
- **First-run setup** installs the heavy libraries once, into a short per-user path. It has a GPU/CPU choice, progress and retry.
- **Deterministic library installs** from locked versions.
- **A way to switch** between GPU and CPU later.
- **A foundation for 5b:** a recorded "installed library set" fingerprint, so an update reinstalls libraries only when their versions change.

## Non-goals (5a)

- Auto-update and release publishing (5b, 5c).
- Code signing (5c).
- Installing NVIDIA drivers or the CUDA toolkit. The torch wheel carries the CUDA runtime, and the driver remains the user's responsibility, with guidance shown.
- Delta or binary patching.

## Layout on disk

| What | Where | Notes |
|---|---|---|
| App files (read-only) | `{app}` = `%LOCALAPPDATA%\Programs\CampaignScribe` (me only) or `%ProgramFiles%\CampaignScribe` (all users) | `app\`, `main.py`, `bootstrap\`, `assets\`, `ffmpeg\`, `models\`, `node\`, `recorder\`, `python\`, `locks\`, `LICENSE`, `PRIVACY.md`, `THIRD-PARTY-NOTICES.md` |
| Private Python 3.13 | `{app}\python\` | Extracted from the python.org zip, with no registry entries |
| ML library environment | `%LOCALAPPDATA%\CampaignScribe\env\` | **Always per-user and a short path.** Program Files isn't writable without admin, and deep paths break torch DLL loading. |
| Setup state | `%LOCALAPPDATA%\CampaignScribe\env\cs-setup.json` | `{"profile":"gpu"\|"cpu","lock_sha256":…,"python":"3.13.16","completed_at":…}` |
| User data (unchanged) | `%APPDATA%\CampaignScribe\` | config, database, logs and recordings, as today |

All-users installs share the read-only app files. Each user gets their own `env` the first time they launch.

## 1. Locked library sets — `locks/`

- **Lock files:**
  - `locks/gpu.txt` holds exact `name==version` lines for **every** distribution in the tested GPU environment, including transitive ones. It carries `--extra-index-url https://download.pytorch.org/whl/cu128` and the `+cu128` torch and torchaudio.
  - `locks/cpu.txt` is the same, with `https://download.pytorch.org/whl/cpu` and `+cpu`.
- **Generator:** `scripts/make_locks.py` produces both. It runs `pip freeze --exclude-editable` (or `pip list --format=freeze`) in a freshly built GPU or CPU app environment that **excludes** dev tools. It drops `torchvision`, adds the index lines and a header comment with the date and Python version, and sorts.
- **Updating the locks** is a deliberate developer action: rebuild the environment, run the generator, run the tests, commit. The generator refuses to emit `torchvision` or any package listed in `requirements-dev.txt` that isn't also an app dependency.
- **Installing** uses `python -m pip install --no-deps --require-virtualenv -r locks/<profile>.txt`. Because every transitive dependency is listed and `--no-deps` is used, pip does no dependency resolution. That retires `setup_venv.bat`'s two-step torch workaround for end users. `setup_venv.bat` stays for developers.
- **Lock fingerprint:** `lock_sha256` is the SHA-256 of the lock file's bytes with line endings normalised. Phase 5b compares it.
- **Hash-pinning** (`--require-hashes`) is out of scope for 5a. It is deferred, because torch's large multi-index wheels make hash lists brittle, and it's noted for 5c.

## 2. First-run bootstrap — `bootstrap/` (standard library only)

`bootstrap/launcher.py` is what the Start-menu shortcut runs with `{app}\python\pythonw.exe`. It uses **only the Python standard library**, including tkinter, because the ML libraries may not exist yet.

**Flow on launch:**
1. Read `cs-setup.json`.
   - If it's present, its `lock_sha256` matches the bundled lock for its profile, and `env\Scripts\pythonw.exe` exists, launch the app (§4) and exit.
   - Otherwise show the **Setup window**.
2. **The Setup window,** in plain Tk, titled "CampaignScribe — first-time setup":
   - **Explanation:** "CampaignScribe needs to download its speech-recognition engine once (about N GB). This can take a while on slower connections."
   - **GPU detection:** look for `nvidia-smi.exe` on PATH or in `%SystemRoot%\System32`. If found, run `nvidia-smi --query-gpu=name,driver_version --format=csv,noheader` with `CREATE_NO_WINDOW` and a 10 s timeout, and parse the name and driver.
   - **Radio choice:**
     - **GPU (NVIDIA) — recommended**, preselected when an NVIDIA GPU is found. Caption: "<GPU name> detected. About 2.6 GB download, about 5 GB on disk."
     - **CPU only**, preselected otherwise. Caption: "About 300 MB download, about 1.4 GB on disk. Transcription runs on the CPU and will be much slower for long recordings (a multi-hour session can take many hours). You can switch to GPU later in Settings."
     - If GPU is chosen but no NVIDIA GPU was found, show a warning line: "No NVIDIA GPU was found — the GPU option may not work on this PC."
   - **Disk space:** the free space on the `%LOCALAPPDATA%` drive is shown. If it is below what the profile needs plus 2 GB headroom, an error blocks Continue.
   - **Buttons:** **Install** and **Quit**.
3. **Install,** on a worker thread with UI updates through `after()`:
   1. **Create the environment:** `{app}\python\python.exe -m venv %LOCALAPPDATA%\CampaignScribe\env`, with the folder first deleted if it is a partial or old install.
   2. **Upgrade pip** to the version pinned in the lock header.
   3. **Install the libraries:** `env\Scripts\python.exe -m pip install --no-deps --require-virtualenv --progress-bar off --disable-pip-version-check -r {app}\locks\<profile>.txt`, with `--retries 5 --timeout 60`. Stdout and stderr stream into the window: a status line with the current package, a log box that is collapsed by default, and a bar that counts installed or downloaded lines against the number of lock lines.
   4. **Verify:** `env\Scripts\python.exe -c "import torch, whisperx, pyannote.audio, faster_whisper; print(torch.__version__, torch.cuda.is_available())"` with a 120 s timeout. For the GPU profile, if `cuda.is_available()` is False, the setup **completes with a warning**: "Installed, but the GPU isn't usable right now (driver missing or too old). CampaignScribe will use the CPU until that's fixed."
   5. **Record success:** write `cs-setup.json` atomically (temp file, then replace), then launch the app.
4. **Failure** (network error, a pip error, or a failed verify):
   - The window shows the last 30 log lines and **Retry** and **Quit** buttons.
   - The full log is kept at `%LOCALAPPDATA%\CampaignScribe\env-setup.log`.
   - Retry reuses pip's cache, so downloaded wheels aren't fetched again.
   - Nothing is recorded as complete until verification passes.
5. **Subprocesses:** every one uses `CREATE_NO_WINDOW`. The window can't be closed while pip is running without confirming. On confirm, pip is terminated, the partial environment is deleted, and the app quits.

**`bootstrap/launcher.py --switch gpu|cpu`** runs the same flow for the other profile. It is invoked from Settings (§5).

## 3. App code changes

- `main.py` runs inside the environment as today. **The packaged-app assumption changes** from frozen PyInstaller (`sys._MEIPASS`) to an **installed layout.** A new `app/core/paths.py` resolves the following, in this order:
  - **installed:** `sys.executable` is under `%LOCALAPPDATA%\CampaignScribe\env`, and an environment variable `CAMPAIGNSCRIBE_HOME={app}` is set by the launcher;
  - **frozen PyInstaller:** kept for one release as a fallback;
  - **dev checkout.**
- `models.models_root()`, `audio.get_ffmpeg_path()`, `discord_recorder.node_exe()` and `recorder_script()`, `notices` and the privacy loader, and the asset dir all go through `paths.app_home()`.
- **Taskbar identity:** at startup, `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ImaginationIndustries.CampaignScribe")` and the window icon are set, so the taskbar shows CampaignScribe, not Python. The shortcut uses the same AppUserModelID.

## 4. Launching the app

- The launcher starts `env\Scripts\pythonw.exe {app}\main.py` with `CAMPAIGNSCRIBE_HOME` set and `CREATE_NO_WINDOW`, then exits.
- `pythonw` means no console window appears.
- The working directory is `{app}`.

## 5. Settings: switch GPU/CPU

Settings gains "Speech engine: GPU (CUDA) / CPU", showing the current profile from `cs-setup.json`, and a **Switch to CPU…** or **Switch to GPU…** button.
- It confirms first: "CampaignScribe will close and download the other engine (about N GB)."
- It then launches `launcher.py --switch <other>` and closes the app.
- In a dev checkout (no `cs-setup.json`), the control is hidden.

## 6. The installer — `installer/CampaignScribe.iss` (Inno Setup 6)

- **Scope:** `PrivilegesRequired=lowest` with `PrivilegesRequiredOverridesAllowed=dialog`. That gives the standard "Install for me only / Install for all users" choice, me only by default. `DefaultDirName={autopf}\CampaignScribe`, which resolves per scope.
- **Identity:**
  - `AppId` is a fixed GUID that never changes;
  - `AppName=CampaignScribe`;
  - `AppVersion` comes from `app/__init__.py` via the build script;
  - `AppPublisher=Imagination Industries LLC`;
  - `AppPublisherURL` is the GitHub repo;
  - `SetupIconFile` and `UninstallDisplayIcon` use the app icon.
- **Pages:**
  - Welcome.
  - **License:** `LicenseFile=LICENSE`, the GPL-3.0.
  - **Information before install:** `InfoBeforeFile=PRIVACY.md`, rendered as text. This is required later for SignPath.
  - Select directory, which is hidden for me-only installs unless the user wants it.
  - Tasks: an optional desktop icon.
  - Ready, install, then Finish with "Launch CampaignScribe", which runs the launcher.
- **Files:** everything in the app-files layout row. `python\` is extracted at build time from the python.org zip.
- **Shortcuts:** in the Start menu, plus the optional desktop one. The target is `{app}\python\pythonw.exe`, the parameters are `"{app}\bootstrap\launcher.py"`, the icon is `{app}\assets\icon.ico`, and `AppUserModelID` is as in §3.
- **Uninstall:**
  - It removes `{app}`.
  - `[UninstallDelete]` cleans `{app}\python` caches.
  - A `[Code]` uninstall step asks: "Also remove the downloaded speech engine (about N GB in %LOCALAPPDATA%\CampaignScribe)?" with **Yes** as the default. For all-users installs, this only touches the uninstalling user's folder.
  - User data in `%APPDATA%\CampaignScribe` is **never** removed by the uninstaller. The final page says where it is.
- **Upgrade in place:** the same `AppId` installs over the old version. Before copying, Inno closes a running CampaignScribe using Restart Manager with `CloseApplications=yes`.

## 7. Build — `build_installer.bat` + `scripts/fetch_python_runtime.py`

- **`scripts/fetch_python_runtime.py`** follows the same pattern as the Node and weights fetch scripts.
  - It downloads `https://www.python.org/ftp/python/3.13.16/python-3.13.16-amd64.zip`, pinned by SHA-256 `bbf675bb5e763c1efbb09a3a461b259d81598a63c30c4b0d7ea11b9f063df159`.
  - It verifies the hash and extracts into `vendor/python/`, which is git-ignored.
  - It does nothing when the files are already present and valid, and has an https guard.
- **`build_installer.bat`:**
  1. fetch the weights, Node runtime and Python runtime;
  2. run `npm ci --omit=dev` in recorder;
  3. assemble `build/installer-root/` with the app files, excluding tests, `__pycache__`, dev files and `recorder/test`;
  4. run `ISCC.exe installer\CampaignScribe.iss` with `/DAppVersion=<version>`;
  5. print the output path and size.

  Every step checks its error level, the same lesson learned in `build.bat`.
- **Inno Setup compiler:** `ISCC.exe` is found through the `INNO_SETUP` environment variable, then the default install paths. If it's missing, the build fails with "Install Inno Setup 6 (https://jrsoftware.org/isinfo.php) or set INNO_SETUP."
- **Old build:** `build.bat` (PyInstaller) stays for one release as a fallback and is labelled "legacy" in the README.

## 8. Notices, privacy, README

- **THIRD-PARTY-NOTICES:** adds Python (PSF License, bundled in `{app}\python`, including its LICENSE.txt) and Inno Setup, which builds the installer. Its license terms are read from its own license file at implementation time, and it is credited.
- **PRIVACY.md:** the first-run download section states that CampaignScribe downloads the speech engine from PyPI and download.pytorch.org once, and sends no user data.
- **README:** user install instructions (download the installer, run it, first-run setup) and developer notes for the build.

## Testing

**Unit tests** (Linux-safe, standard library only, where possible):
- `make_locks` filtering: no torchvision, no dev-only packages, the index lines, sorting.
- The lock fingerprint, with line endings normalised.
- Reading and writing `cs-setup.json`: atomic, with corrupt-file handling meaning "not set up".
- The bootstrap decision logic: launch, set up, or switch, from the state and the lock hash.
- `nvidia-smi` output parsing.
- The disk-space check.
- `paths.app_home()` resolution: installed, frozen and dev.
- `fetch_python_runtime`: a hash mismatch deletes the file, an already-installed runtime is a no-op, and a network error returns 1 (the same pattern as the Node fetch tests).

**GUI tests** (Windows): the Setup window with a fake installer step that emits progress lines. They check:
- the GPU preselected when the fake detection finds a GPU;
- the CPU warning text;
- the low-disk block;
- the retry path after a fake failure;
- the close confirmation while installing;
- the Settings switch control hidden in dev and shown with a fake `cs-setup.json`.

**Packaging tests:** `build_installer.bat` step order with error-level checks; `.iss` invariants (`PrivilegesRequired=lowest`, `PrivilegesRequiredOverridesAllowed=dialog`, `LicenseFile`, `InfoBeforeFile`, the AppUserModelID on shortcuts, the uninstall step present).

**Manual acceptance** (controller, on this PC, in a throwaway Windows user profile or after uninstalling the dev bits):
1. Build the installer, then install for me only. There's no admin prompt, and the Start-menu entry and "Installed apps" entry appear.
2. **First run, GPU:** the download and install run with progress, and GPU transcription of the test clip matches 238 segments and 6 speakers.
3. **Switch to CPU** from Settings, then switch back.
4. **Install for all users:** the admin prompt appears, the files go to Program Files, and a second Windows user gets their own first-run setup. This step is optional if no second user is available.
5. **Uninstall:** the engine prompt appears, and `%APPDATA%` data is kept.
6. **Kill the network** mid-install, then Retry: it resumes from cache.
