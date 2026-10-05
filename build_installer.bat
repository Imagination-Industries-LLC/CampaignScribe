@echo off
setlocal
rem Builds the slim Inno Setup installer (version from the app package).
rem The legacy PyInstaller build is build.bat.
cd /d "%~dp0"
set "ROOT=%CD%\"
set "PY=%ROOT%.venv\Scripts\python.exe"
set "STAGE=%ROOT%build\installer-root"

if not exist "%PY%" (
    echo ERROR: venv not found at %PY%. Run setup_venv.bat first.
    exit /b 1
)
if not exist "ffmpeg\ffmpeg.exe" (
    echo ERROR: ffmpeg\ffmpeg.exe not found. Download a Windows ffmpeg build and copy ffmpeg.exe into the ffmpeg folder.
    exit /b 1
)

echo [1/7] Fetching bundled diarization weights...
"%PY%" scripts\fetch_diarization_weights.py
if errorlevel 1 (
    echo ERROR: diarization weights missing or invalid; see message above.
    exit /b 1
)

rem The Discord recorder (node + recorder\) is bundled only once its lockfile is tracked in git.
set "HAVE_RECORDER="
for /f %%f in ('git ls-files recorder/package-lock.json') do set "HAVE_RECORDER=1"

if not defined HAVE_RECORDER goto :after_node
echo [2/7] Fetching the Node runtime and installing recorder dependencies...
"%PY%" scripts\fetch_node_runtime.py
if errorlevel 1 (
    echo ERROR: Node runtime fetch failed.
    exit /b 1
)
pushd recorder
call npm ci --omit=dev
if errorlevel 1 (
    popd
    echo ERROR: npm ci failed in recorder.
    exit /b 1
)
popd
:after_node

echo [3/7] Fetching the Python runtime...
"%PY%" scripts\fetch_python_runtime.py
if errorlevel 1 (
    echo ERROR: Python runtime fetch failed; see message above.
    exit /b 1
)

echo [4/7] Assembling %STAGE% ...
if exist "%STAGE%" rmdir /s /q "%STAGE%"
if exist "%STAGE%" (
    echo ERROR: could not clear %STAGE%.
    exit /b 1
)
mkdir "%STAGE%"
if errorlevel 1 (
    echo ERROR: could not create %STAGE%.
    exit /b 1
)
robocopy "app" "%STAGE%\app" /E /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :copyfail
robocopy "bootstrap" "%STAGE%\bootstrap" /E /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :copyfail
robocopy "locks" "%STAGE%\locks" /E /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :copyfail
robocopy "assets" "%STAGE%\assets" /E /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :copyfail
robocopy "ffmpeg" "%STAGE%\ffmpeg" ffmpeg.exe /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :copyfail
robocopy "models\speaker-diarization-community-1" "%STAGE%\models\speaker-diarization-community-1" /E /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :copyfail
robocopy "vendor\python" "%STAGE%\python" /E /XD __pycache__ Doc /XF *.pyc /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :copyfail
if defined HAVE_RECORDER (
    robocopy "recorder" "%STAGE%\recorder" /E /XD "%ROOT%recorder\test" __pycache__ /NFL /NDL /NJH /NJS /NP
    if errorlevel 8 goto :copyfail
    robocopy "vendor\node" "%STAGE%\node" /E /NFL /NDL /NJH /NJS /NP
    if errorlevel 8 goto :copyfail
)
for %%f in (main.py LICENSE PRIVACY.md THIRD-PARTY-NOTICES.md) do (
    copy /y "%%f" "%STAGE%\%%f" >nul
    if errorlevel 1 goto :copyfail
)
goto :copied
:copyfail
echo ERROR: assembling the installer root failed.
exit /b 1
:copied

echo [5/7] Reading the version...
set "VER="
for /f "tokens=2 delims==" %%v in ('findstr /b "__version__" app\__init__.py') do set "VER=%%v"
if defined VER set "VER=%VER: =%"
if defined VER set "VER=%VER:"=%"
if not defined VER (
    echo ERROR: could not read __version__ from app\__init__.py.
    exit /b 1
)
echo Version %VER%

echo [6/7] Locating the Inno Setup compiler...
set "ISCC="
if defined INNO_SETUP if exist "%INNO_SETUP%\ISCC.exe" set "ISCC=%INNO_SETUP%\ISCC.exe"
if defined INNO_SETUP if not defined ISCC if exist "%INNO_SETUP%" set "ISCC=%INNO_SETUP%"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if defined ISCC goto :have_iscc
echo ERROR: ISCC.exe not found.
echo Install Inno Setup 6 (https://jrsoftware.org/isinfo.php) or set INNO_SETUP.
exit /b 1
:have_iscc

echo [7/7] Compiling the installer with %ISCC% ...
"%ISCC%" /DAppVersion=%VER% /O"%ROOT%dist-installer" installer\CampaignScribe.iss
if errorlevel 1 (
    echo ERROR: Inno Setup compile failed; see the output above.
    exit /b 1
)
set "OUT=%ROOT%dist-installer\CampaignScribe-Setup-%VER%.exe"
if not exist "%OUT%" (
    echo ERROR: %OUT% was not produced.
    exit /b 1
)
echo.
echo Build complete.
for %%f in ("%OUT%") do echo Installer: %%~ff  ^(%%~zf bytes^)
endlocal
exit /b 0
