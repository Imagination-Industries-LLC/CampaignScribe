@echo off
setlocal
cd /d "%~dp0"

rem CampaignScribe dev environment setup.
rem
rem Creates .venv and installs all dependencies. Wraps `pip install` because
rem whisperx 3.8.5's metadata pins torch~=2.8.0 (a stale constraint that the
rem code actually works around) and would block our torch==2.11.0+cu128 pin.
rem A two-step install gets around it.

if exist ".venv\Scripts\python.exe" (
    echo [setup_venv] .venv already exists. Delete it first if you want a fresh install:
    echo [setup_venv]   rmdir /s /q .venv
    exit /b 0
)

echo [setup_venv] Creating .venv with Python 3.11...
py -3.11 -m venv .venv
if errorlevel 1 (
    echo [setup_venv] ERROR: failed to create venv. Is Python 3.11 installed?
    exit /b 1
)

set "PY=.venv\Scripts\python.exe"

echo [setup_venv] Upgrading pip...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

echo.
echo [setup_venv] Step 1/2: installing app dependencies (whisperx will pull torch 2.8.x temporarily)...
"%PY%" -m pip install ^
    anthropic ^
    keyring ^
    ffmpeg-python ^
    python-docx ^
    pyinstaller ^
    faster-whisper ^
    whisperx==3.8.5 ^
    pyannote.audio==4.0.4 ^
    transformers==4.57.6 ^
    huggingface_hub==0.36.2 ^
    lightning==2.6.1 ^
    pytorch-lightning==2.6.1
if errorlevel 1 exit /b 1

echo.
echo [setup_venv] Step 2/2: removing torchvision and forcing torch/torchaudio to 2.11.0+cu128...
rem whisperx declares torchvision~=0.23.0 as a hard dep but the app never uses it.
rem Leaving it installed makes torchmetrics try to load torchvision, whose C extension
rem was built against torch 2.8 and crashes when we upgrade torch to 2.11.
"%PY%" -m pip uninstall -y torchvision
"%PY%" -m pip install --force-reinstall --no-deps ^
    --extra-index-url https://download.pytorch.org/whl/cu128 ^
    torch==2.11.0+cu128 ^
    torchaudio==2.11.0+cu128
if errorlevel 1 exit /b 1

echo.
echo [setup_venv] Done. Run run_dev.bat to launch the app.
endlocal
