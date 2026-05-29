@echo off
setlocal
echo Building CampaignScribe...
set ROOT=%~dp0
set PY=%ROOT%.venv\Scripts\python.exe
if not exist "%PY%" (
    echo ERROR: venv not found at %PY%
    exit /b 1
)
"%PY%" -m PyInstaller --noconfirm --onedir --windowed ^
    --icon=assets\icon.ico ^
    --name CampaignScribe ^
    --add-data "ffmpeg\ffmpeg.exe;ffmpeg" ^
    --add-data "assets;assets" ^
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
    --hidden-import=keyring.backends.Windows ^
    --hidden-import=docx ^
    --hidden-import=ffmpeg ^
    --hidden-import=app ^
    --hidden-import=app.ui.app_window ^
    main.py
echo.
echo Build complete. Output: dist\CampaignScribe\CampaignScribe.exe
echo (--onedir mode: keep the entire dist\CampaignScribe folder together;
echo  the .exe will not work alone.)
endlocal
