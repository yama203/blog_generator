#Requires -Version 5.1
$ErrorActionPreference = 'Stop'

$APP_NAME   = "AI Blog Generator"
$PORT       = 8501
$SCRIPT_DIR = Split-Path $MyInvocation.MyCommand.Path -Parent
$PROJECT_DIR = Split-Path $SCRIPT_DIR -Parent

Set-Location $PROJECT_DIR
$host.UI.RawUI.WindowTitle = $APP_NAME

Write-Host "=================================================="
Write-Host "  $APP_NAME"
Write-Host "=================================================="
Write-Host ""

# --- Find uv --------------------------------------------------
$uvInProject = Join-Path $PROJECT_DIR "uv.exe"
if (Test-Path $uvInProject) {
    $UV = $uvInProject
} else {
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    $UV = if ($uvCmd) { $uvCmd.Source } else { $null }
}

if (-not $UV) {
    Write-Host "Downloading uv..."
    try {
        $tmp      = Join-Path $env:TEMP "uv_dl"
        $zipPath  = Join-Path $tmp "uv.zip"
        $exPath   = Join-Path $tmp "extract"
        New-Item -ItemType Directory -Force $tmp | Out-Null
        Invoke-WebRequest -Uri "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $exPath -Force
        $uvExe = Get-ChildItem $exPath -Recurse -Filter "uv.exe" | Select-Object -First 1
        Copy-Item $uvExe.FullName -Destination $uvInProject
        Remove-Item $tmp -Recurse -Force
        $UV = $uvInProject
        Write-Host "uv downloaded OK."
    } catch {
        Write-Host "ERROR: Failed to download uv. Check your internet connection."
        Write-Host "Detail: $_"
        Read-Host "Press Enter to close"
        exit 1
    }
}

# --- First-run setup ------------------------------------------
$venvPython = Join-Path $PROJECT_DIR ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "First-time setup (may take 5-10 minutes)..."
    Write-Host ""

    # Find Python: prefer system Python via py launcher to avoid
    # uv python install os error 448 on OneDrive/redirected-folder paths.
    $PYTHON3 = $null

    try {
        $out = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            $PYTHON3 = $out.Trim()
            Write-Host "Found system Python 3.12: $PYTHON3"
        }
    } catch {}

    if (-not $PYTHON3) {
        try {
            $out = & py -3 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) {
                $PYTHON3 = $out.Trim()
                Write-Host "Found system Python 3: $PYTHON3"
            }
        } catch {}
    }

    if (-not $PYTHON3) {
        Write-Host "Installing Python 3.12 via uv..."
        & $UV python install 3.12
        if ($LASTEXITCODE -eq 0) {
            $out = & $UV python find 3.12 2>$null
            if ($out) { $PYTHON3 = $out.Trim() }
        } else {
            Write-Host ""
            Write-Host "ERROR: Python installation failed."
            Write-Host ""
            Write-Host "Please install Python 3.12 manually and restart this app:"
            Write-Host "  https://www.python.org/downloads/"
            Write-Host "  (Check 'Add Python to PATH' during install)"
            Read-Host "Press Enter to close"
            exit 1
        }
    }

    Write-Host "Creating virtual environment..."
    & $PYTHON3 -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create virtual environment."
        Read-Host "Press Enter to close"
        exit 1
    }

    Write-Host "Installing packages..."
    & $UV pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Package installation failed."
        Read-Host "Press Enter to close"
        exit 1
    }

    Write-Host ""
    Write-Host "Setup complete!"
    Write-Host ""
}

# --- Activate venv --------------------------------------------
$venvScripts     = Join-Path $PROJECT_DIR ".venv\Scripts"
$env:PATH        = "$venvScripts;$env:PATH"
$env:VIRTUAL_ENV = Join-Path $PROJECT_DIR ".venv"

# --- Check if already running ---------------------------------
try {
    Invoke-WebRequest -Uri "http://localhost:$PORT/_stcore/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
    Write-Host "App is already running. Opening browser..."
    Start-Process "http://localhost:$PORT"
    exit 0
} catch {}

# --- Kill stale process on port -------------------------------
$lines = netstat -ano 2>$null | Select-String ":$PORT\s"
foreach ($line in $lines) {
    $parts = $line.ToString().Trim() -split '\s+'
    $pid   = $parts[-1]
    if ($pid -match '^\d+$') {
        Stop-Process -Id ([int]$pid) -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Starting $APP_NAME..."
Write-Host "Browser will open automatically."
Write-Host "Close this window to stop the app."
Write-Host ""

# --- Browser opener (background job) -------------------------
$null = Start-Job -ScriptBlock {
    param($port)
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep 1
        try {
            Invoke-WebRequest -Uri "http://localhost:$port/_stcore/health" -UseBasicParsing -TimeoutSec 1 | Out-Null
            Start-Process "http://localhost:$port"
            break
        } catch {}
    }
} -ArgumentList $PORT

# --- Start Streamlit (foreground) -----------------------------
$streamlit = Join-Path $venvScripts "streamlit.exe"
& $streamlit run app.py --server.headless true --browser.gatherUsageStats false --server.port $PORT

Read-Host "Finished. Press Enter to close"
