@echo off
setlocal
echo Building CampaignScribe...
set ROOT=%~dp0
set PY=%ROOT%.venv\Scripts\python.exe
if not exist "%PY%" (
    echo ERROR: venv not found at %PY%
    exit /b 1
)
if not exist "%ROOT%ffmpeg\ffmpeg.exe" (
    echo ERROR: ffmpeg\ffmpeg.exe not found. Download a Windows ffmpeg build ^(e.g. https://www.gyan.dev/ffmpeg/builds/ or winget install Gyan.FFmpeg^) and copy ffmpeg.exe into the ffmpeg folder.
    exit /b 1
)
echo Fetching bundled diarization weights...
"%PY%" scripts\fetch_diarization_weights.py
if errorlevel 1 (
    echo ERROR: diarization weights missing or invalid; see message above.
    exit /b 1
)
"%PY%" -m PyInstaller --noconfirm --onedir --windowed ^
    --icon=assets\icon.ico ^
    --name CampaignScribe ^
    --add-data "ffmpeg\ffmpeg.exe;ffmpeg" ^
    --add-data "assets;assets" ^
    --add-data "PRIVACY.md;." ^
    --add-data "THIRD-PARTY-NOTICES.md;." ^
    --add-data "models\speaker-diarization-community-1;models\speaker-diarization-community-1" ^
    --collect-all torch ^
    --collect-all whisperx ^
    --collect-all pyannote ^
    --collect-all faster_whisper ^
    --collect-all lightning_fabric ^
    --collect-all speechbrain ^
    --collect-all torchaudio ^
    --collect-all transformers ^
    --collect-data anthropic ^
    --copy-metadata torchcodec ^
    --copy-metadata transformers ^
    --copy-metadata tokenizers ^
    --copy-metadata huggingface_hub ^
    --copy-metadata safetensors ^
    --copy-metadata regex ^
    --copy-metadata requests ^
    --copy-metadata packaging ^
    --copy-metadata filelock ^
    --copy-metadata numpy ^
    --copy-metadata tqdm ^
    --copy-metadata pyyaml ^
    --copy-metadata pyannote.audio ^
    --copy-metadata pyannote.core ^
    --hidden-import=anthropic ^
    --hidden-import=google.genai ^
    --hidden-import=openai ^
    --collect-data google.genai ^
    --hidden-import=keyring.backends.Windows ^
    --hidden-import=docx ^
    --hidden-import=ffmpeg ^
    --hidden-import=app ^
    --hidden-import=app.ui.app_window ^
    main.py
if errorlevel 1 (
    echo ERROR: PyInstaller failed; see the output above. No usable build was produced.
    exit /b 1
)
if not exist "dist\CampaignScribe\CampaignScribe.exe" (
    echo ERROR: dist\CampaignScribe\CampaignScribe.exe was not produced.
    exit /b 1
)
echo.
echo Build complete. Output: dist\CampaignScribe\CampaignScribe.exe
echo (--onedir mode: keep the entire dist\CampaignScribe folder together;
echo  the .exe will not work alone.)
endlocal
exit /b 0
