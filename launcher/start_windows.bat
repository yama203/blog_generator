@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion

set "APP_NAME=AI Blog Generator"
set "PORT=8501"

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
    where uv >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=*" %%i in ('where uv 2^>nul') do set "UV=%%i"
    )
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
        echo ERROR: uv のダウンロードに失敗しました。インターネット接続を確認してください。
        pause
        exit /b 1
    )
)

:: ── First-run setup ──────────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo 初回セットアップ中です（5〜10分かかる場合があります）...
    echo.

    :: ── Python を探す（優先順位: システム Python > uv 管理 Python）──
    ::
    :: uv python install は OneDrive/フォルダリダイレクト環境で
    :: os error 448 が発生する場合があるため最後の手段とする。
    :: Windows Python Launcher (py.exe) があれば先に使う。

    set "PYTHON3="

    :: 1. Python 3.12 (Windows Python Launcher)
    py -3.12 --version >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "usebackq tokens=*" %%p in (`py -3.12 -c "import sys; print(sys.executable)" 2^>nul`) do set "PYTHON3=%%p"
        if defined PYTHON3 echo Python 3.12 をシステムから検出しました。
    )

    :: 2. Python 3.x 系 (任意バージョン)
    if not defined PYTHON3 (
        py -3 --version >nul 2>&1
        if !errorlevel! equ 0 (
            for /f "usebackq tokens=*" %%p in (`py -3 -c "import sys; print(sys.executable)" 2^>nul`) do set "PYTHON3=%%p"
            if defined PYTHON3 echo Python 3 をシステムから検出しました。
        )
    )

    :: 3. uv python install (最終手段)
    if not defined PYTHON3 (
        echo Python 3.12 をインストール中...
        "%UV%" python install 3.12
        if !errorlevel! equ 0 (
            for /f "usebackq tokens=*" %%p in (`"%UV%" python find 3.12 2^>nul`) do set "PYTHON3=%%p"
        ) else (
            echo.
            echo [エラー] Python の自動インストールに失敗しました。
            echo.
            echo 以下の手順で Python 3.12 を手動インストール後、再起動してください:
            echo   1. https://www.python.org/downloads/ を開く
            echo   2. Python 3.12.x をダウンロードしてインストール
            echo   3. インストール時に "Add Python to PATH" にチェックを入れる
            echo   4. このアプリを再起動する
            echo.
            pause
            exit /b 1
        )
    )

    :: ── 仮想環境を作成 ───────────────────────────────────────
    "%PYTHON3%" -m venv .venv
    if !errorlevel! neq 0 (
        echo ERROR: 仮想環境の作成に失敗しました。
        pause
        exit /b 1
    )

    :: ── パッケージをインストール ─────────────────────────────
    call .venv\Scripts\activate.bat
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
