@echo off
chcp 65001 > nul
cd /d "%~dp0.."

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo 仮想環境が見つかりません。
    echo 先に setup.bat を実行してください。
    pause
    exit /b 1
)

echo AI ブログジェネレーターを起動しています...
echo ブラウザが自動で開きます。
echo 終了するにはこのウィンドウを閉じてください。
echo.

streamlit run app.py --server.headless true --browser.gatherUsageStats false --server.port 8501
pause
