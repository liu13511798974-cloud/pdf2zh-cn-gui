@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   PDF Translator Tool - Offline Setup - no internet needed
echo ============================================================
echo.

if not exist "python\python.exe" (
    echo [1/5] Setting up embedded Python 3.13...
    powershell -NoProfile -Command "Expand-Archive -Path 'resources\python-3.13.15-embed-amd64.zip' -DestinationPath 'python' -Force"
    powershell -NoProfile -Command "$p='python\python313._pth'; $c=[IO.File]::ReadAllText($p); $c=$c.Replace('#import site','import site'); [IO.File]::WriteAllText($p,$c)"
    if not exist "python\python.exe" (
        echo.
        echo [ERROR] Python setup failed.
        echo Please make sure resources\python-3.13.15-embed-amd64.zip exists.
        pause
        exit /b 1
    )
) else (
    echo [1/5] Embedded Python already present, skip.
)

echo [2/5] Installing VC++ runtime - silent...
if exist "resources\vc_redist.x64.exe" (
    "resources\vc_redist.x64.exe" /install /quiet /norestart
)

echo [3/5] Bootstrapping pip - offline...
"python\python.exe" "resources\get-pip.py" --no-index --find-links "wheels" --no-warn-script-location
if errorlevel 1 (
    echo.
    echo [ERROR] pip bootstrap failed. Please check the wheels folder.
    pause
    exit /b 1
)

echo [4/5] Installing dependencies - offline, 3-8 min, please wait...
"python\python.exe" -m pip install --no-index --find-links "wheels" pdf2zh==1.7.9 --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed.
    echo Please make sure the wheels folder is complete.
    pause
    exit /b 1
)

echo [5/5] Applying patches...
copy /y "patches\high_level.py" "python\Lib\site-packages\pdf2zh\" >nul
copy /y "patches\converter.py" "python\Lib\site-packages\pdf2zh\" >nul
copy /y "patches\translator.py" "python\Lib\site-packages\pdf2zh\" >nul

echo [6/6] Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "make_shortcut.ps1"

echo.
echo ============================================================
echo    Setup finished!
echo    Double-click "PDF Translator Tool" on your desktop.
echo    Your browser will open http://127.0.0.1:7860
echo    Translated PDFs are saved in the output folder under
echo    this directory. Do NOT move or delete this tool folder.
echo    See the file "????.md" for the Chinese manual.
echo ============================================================
pause