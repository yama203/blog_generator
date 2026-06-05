@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion

set "APP_NAME=AI Blog Generator"
set "PORT=8501"

:: Project root is one level up from launcher\
set "PROJECT_DIR=%~dp0.."
for %%i in ("%PROJECT_DIR%") do set "PROJECT_DIR=%%~fi"
cd /d "%PROJECT_DIR%"

title %APP_NAME%

echo ==================================================
echo   %APP_NAME%
echo ==================================================
echo.

:: ── Find uv ──────────────────────────────────────────────────
set "UV="
if exist "%PROJECT_DIR%\uv.exe" set "UV=%PROJECT_DIR%\uv.exe"
if not defined UV (
    where uv >nul 2>&1 && for /f "tokens=*" %%i in ('where uv 2^>nul') do set "UV=%%i"
)
if not defined UV (
    echo uv をダウンロード中...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$url='https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip';" ^
        "$tmp=[IO.Path]::Combine($env:TEMP,'uv_dl');" ^
        "New-Item -ItemType Directory -Force $tmp | Out-Null;" ^
        "Invoke-WebRequest -Uri $url -OutFile \"$tmp\uv.zip\" -UseBasicParsing;" ^
        "Expand-Archive -Path \"$tmp\uv.zip\" -DestinationPath \"$tmp\extract\" -Force;" ^
        "$src=Get-ChildItem \"$tmp\extract\" -Recurse -Filter uv.exe | Select-Object -First 1;" ^
        "Copy-Item $src.FullName -Destination '%PROJECT_DIR%\uv.exe';" ^
        "Remove-Item $tmp -Recurse -Force"
    if exist "%PROJECT_DIR%\uv.exe" (
        set "UV=%PROJECT_DIR%\uv.exe"
    ) else (
        echo.
        echo ERROR: uv のダウンロードに失敗しました。
        echo インターネット接続を確認してください。
        pause
        exit /b 1
    )
)

:: ── uv のデータ/Python インストール先をアプリ内に固定 ────────
:: （OneDrive やネットワークドライブ上のパスでの os error 448 を回避）
set "UV_DATA_DIR=%PROJECT_DIR%\.uv_data"
set "UV_PYTHON_INSTALL_DIR=%PROJECT_DIR%\.python"

:: ── First-run setup ──────────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo 初回セットアップ中です（5〜10分かかる場合があります）...
    echo.
    "%UV%" python install 3.12
    if !errorlevel! neq 0 (
        echo ERROR: Python 3.12 のインストールに失敗しました。
        pause
        exit /b 1
    )
    "%UV%" venv .venv --python 3.12
    "%UV%" pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo ERROR: パッケージのインストールに失敗しました。
        pause
        exit /b 1
    )
    echo.
    echo セットアップ完了！
    echo.
)

:: ── Activate venv ────────────────────────────────────────────
call .venv\Scripts\activate.bat

:: ── Check if already running ─────────────────────────────────
powershell -NoProfile -Command ^
    "try{Invoke-WebRequest 'http://localhost:%PORT%/_stcore/health' -UseBasicParsing -TimeoutSec 2|Out-Null;exit 0}catch{exit 1}" >nul 2>&1
if !errorlevel! equ 0 (
    echo アプリはすでに起動しています。ブラウザを開きます...
    start "" "http://localhost:%PORT%"
    exit /b 0
)

:: ── Kill stale process on port ───────────────────────────────
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%PORT% "') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo %APP_NAME% を起動しています...
echo ブラウザが自動で開きます。
echo 終了するにはこのウィンドウを閉じてください。
echo.

:: ── Open browser when ready (background) ─────────────────────
start /b "" powershell -NoProfile -Command ^
    "for($i=0;$i-lt30;$i++){Start-Sleep 1;try{Invoke-WebRequest 'http://localhost:%PORT%/_stcore/health' -UseBasicParsing -TimeoutSec 1|Out-Null;Start-Process 'http://localhost:%PORT%';break}catch{}}"

:: ── Start Streamlit (foreground, keeps window open) ──────────
streamlit run app.py ^
    --server.headless true ^
    --browser.gatherUsageStats false ^
    --server.port %PORT%

pause
