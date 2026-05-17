#!/bin/bash
# ============================================================
#  create_app.sh — AIブログジェネレーター.app を作成します
#  実行方法: bash create_app.sh
# ============================================================
set -e

APP_NAME="AIブログジェネレーター"
APP_BUNDLE="${APP_NAME}.app"
MACOS_DIR="${APP_BUNDLE}/Contents/MacOS"
RES_DIR="${APP_BUNDLE}/Contents/Resources"

echo "🔨 ${APP_NAME}.app を作成中..."

# 既存の .app を削除
rm -rf "${APP_BUNDLE}"
mkdir -p "${MACOS_DIR}" "${RES_DIR}"

# 開発者Mac用: 現在のプロジェクトパスを保存
printf "%s" "$(pwd)" > "${RES_DIR}/project_path.txt"

# ── ソースファイルを .app 内に同梱（別Macへの配布用）──────────
echo "📦 ソースファイルを同梱中..."
SRC_DIR="${RES_DIR}/app_source"
mkdir -p "$SRC_DIR"
rsync -a \
    --exclude='.venv/' \
    --exclude='.python/' \
    --exclude='__pycache__/' \
    --exclude='*.app' \
    --exclude='.DS_Store' \
    --exclude='AppIcon.icns' \
    --exclude='AppIcon.iconset' \
    --exclude='*.zip' \
    --exclude='launcher/' \
    . "$SRC_DIR/"

# ── uv バイナリを両アーキテクチャ分ダウンロード ───────────────
echo "⬇️  uv をダウンロード中（arm64 / x86_64）..."
download_uv() {
    local arch="$1"   # arm64 or x86_64
    local dest="${RES_DIR}/uv_${arch}"
    local url
    if [ "$arch" = "arm64" ]; then
        url="https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz"
    else
        url="https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-apple-darwin.tar.gz"
    fi
    local tmp
    tmp=$(mktemp -d)
    if curl -fsSL "$url" -o "$tmp/uv.tar.gz" 2>/dev/null; then
        tar -xzf "$tmp/uv.tar.gz" -C "$tmp" 2>/dev/null || true
        local bin
        bin=$(find "$tmp" -name "uv" -not -name "uvx" -type f 2>/dev/null | head -1)
        if [ -n "$bin" ]; then
            cp "$bin" "$dest"
            chmod +x "$dest"
            echo "  ✅ uv (${arch})"
        else
            echo "  ⚠️  uv (${arch}) の展開に失敗しました"
        fi
    else
        echo "  ⚠️  uv (${arch}) のダウンロードに失敗しました（インターネット接続を確認）"
    fi
    rm -rf "$tmp"
}
download_uv arm64
download_uv x86_64

# ── launch 実行スクリプト ─────────────────────────────────────
cat > "${MACOS_DIR}/launch" << 'LAUNCH_SCRIPT'
#!/bin/bash
# .app/Contents/MacOS/launch

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUNDLE_RES="${SCRIPT_DIR}/../Resources"
PROJECT_DIR="$(cat "${BUNDLE_RES}/project_path.txt" 2>/dev/null | tr -d '[:space:]')"

# ── プロジェクトフォルダが存在しない場合は ~/Documents に展開 ──
if [ -z "$PROJECT_DIR" ] || [ ! -d "$PROJECT_DIR" ]; then
    PROJECT_DIR="$HOME/Documents/AIブログジェネレーター"
    mkdir -p "$PROJECT_DIR"
    printf "%s" "$PROJECT_DIR" > "${BUNDLE_RES}/project_path.txt" 2>/dev/null || true
fi

# ── ソースファイルを常に同期（バグ修正が即時反映されるよう）──
rsync -a --checksum \
    --exclude='.venv/' \
    --exclude='.python/' \
    --exclude='.uv' \
    --exclude='__pycache__/' \
    --exclude='.DS_Store' \
    --exclude='config.json' \
    "${BUNDLE_RES}/app_source/." "$PROJECT_DIR/"
# 古いバイトコードキャッシュを削除（古い .pyc が残ると修正が反映されない）
find "$PROJECT_DIR" -name "*.pyc" -not -path "*/.venv/*" -delete 2>/dev/null || true
find "$PROJECT_DIR" -path "*/__pycache__" -not -path "*/.venv/*" -type d -exec rm -rf {} + 2>/dev/null || true

cd "$PROJECT_DIR"
export PATH="/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"
export PYTHONIOENCODING="utf-8"
export PYTHONUTF8="1"

LOG="/tmp/ai_blog_generator.log"
PORT=8501

# ── Ollama チェック ───────────────────────────────────────────
OLLAMA=""
for p in /usr/local/bin/ollama /opt/homebrew/bin/ollama /usr/bin/ollama; do
    [ -x "$p" ] && OLLAMA="$p" && break
done

if [ -z "$OLLAMA" ]; then
    BTN=$(osascript -e 'button returned of (display dialog "Ollama がインストールされていません。\n\nOllama は AI テキスト生成エンジンです。\nインストールページを開きますか？" buttons {"キャンセル", "インストールページを開く"} default button "インストールページを開く" with icon caution with title "AI ブログジェネレーター")')
    [ "$BTN" = "インストールページを開く" ] && open "https://ollama.ai"
    exit 0
fi

# ── uv を取得（同梱バイナリ優先、なければダウンロード）─────────
# uname -m は Rosetta 環境では x86_64 を返すため sysctl でハードウェアを判定する
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
    ARCH="arm64"
else
    ARCH="x86_64"
fi
UV="${BUNDLE_RES}/uv_${ARCH}"

if [ ! -x "$UV" ]; then
    # アーキテクチャに合ったバイナリが同梱されていない場合はダウンロード
    UV="$PROJECT_DIR/.uv"
    if [ ! -x "$UV" ]; then
        osascript -e 'display notification "uv をダウンロード中..." with title "AI ブログジェネレーター"'
        if [ "$ARCH" = "arm64" ]; then
            UV_URL="https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz"
        else
            UV_URL="https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-apple-darwin.tar.gz"
        fi
        TMP_DIR=$(mktemp -d)
        if curl -fsSL "$UV_URL" -o "$TMP_DIR/uv.tar.gz" 2>/dev/null; then
            tar -xzf "$TMP_DIR/uv.tar.gz" -C "$TMP_DIR" 2>/dev/null || true
            UV_BIN=$(find "$TMP_DIR" -name "uv" -not -name "uvx" -type f 2>/dev/null | head -1)
            [ -n "$UV_BIN" ] && cp "$UV_BIN" "$PROJECT_DIR/.uv" && chmod +x "$PROJECT_DIR/.uv"
        fi
        rm -rf "$TMP_DIR"
    fi
fi

if [ ! -x "$UV" ]; then
    osascript -e 'display dialog "セットアップツール（uv）のダウンロードに失敗しました。\n\nインターネット接続を確認してから再起動してください。" buttons {"OK"} with icon stop with title "AI ブログジェネレーター"'
    exit 1
fi

# ── Python 3.12 の準備（uv が自動でダウンロード・管理）─────────
PYTHON3=$("$UV" python find 3.12 2>/dev/null || true)

# ── 初回セットアップ or 破損チェック ─────────────────────────
VENV_SITE="$PROJECT_DIR/.venv/lib/python3.12/site-packages"
NEEDS_SETUP=false

if [ -z "$PYTHON3" ]; then
    NEEDS_SETUP=true
elif [ ! -d "$VENV_SITE" ]; then
    NEEDS_SETUP=true
elif ! PYTHONPATH="$VENV_SITE" "$PYTHON3" -c "import streamlit" 2>/dev/null; then
    NEEDS_SETUP=true
fi

if [ "$NEEDS_SETUP" = true ]; then
    osascript -e 'display dialog "初めての起動です。\n\n必要なパッケージを自動でインストールします（5〜10分かかる場合があります）。\nターミナルが開きますのでそのままお待ちください。\n\n完了後にもう一度アプリをダブルクリックしてください。" buttons {"OK"} default button "OK" with title "AI ブログジェネレーター"'
    rm -rf "$PROJECT_DIR/.venv"
    osascript -e "tell application \"Terminal\"
        do script \"cd '$PROJECT_DIR' && '$UV' python install 3.12 && '$UV' venv .venv --python 3.12 && '$UV' pip install -r requirements.txt && echo '\\n✅ セットアップ完了。このウィンドウを閉じてアプリをもう一度ダブルクリックしてください。'\"
        activate
    end tell"
    exit 0
fi

# ── Ollama 起動 ───────────────────────────────────────────────
if ! pgrep -x "ollama" > /dev/null 2>&1; then
    "$OLLAMA" serve > /dev/null 2>&1 &
    sleep 2
fi

# ── Streamlit 起動 ────────────────────────────────────────────
# /_stcore/health が 200 を返せば本当に準備完了
is_streamlit_ready() {
    curl -sf "http://localhost:$PORT/_stcore/health" > /dev/null 2>&1
}

if ! is_streamlit_ready; then
    # 古いプロセスがポートを占有していれば強制終了
    lsof -ti ":$PORT" | xargs kill -9 2>/dev/null || true
    sleep 1

    PYTHONPATH="$VENV_SITE" "$PYTHON3" -m streamlit run "$PROJECT_DIR/app.py" \
        --server.headless true \
        --browser.gatherUsageStats false \
        --server.port "$PORT" > "$LOG" 2>&1 &
    STREAMLIT_PID=$!

    STARTED=false
    for i in $(seq 1 40); do
        sleep 1
        if is_streamlit_ready; then
            STARTED=true
            break
        fi
        if ! kill -0 "$STREAMLIT_PID" 2>/dev/null; then
            ERROR=$(tail -20 "$LOG" | tr '"' "'" | tr '\n' ' ')
            osascript -e "display dialog \"アプリの起動に失敗しました。\n\nエラー:\n$ERROR\n\nログ: $LOG\" buttons {\"OK\"} default button \"OK\" with icon stop with title \"AI ブログジェネレーター\""
            exit 1
        fi
    done

    if [ "$STARTED" = false ]; then
        osascript -e "display dialog \"タイムアウト: アプリが起動しませんでした。\n\nログを確認してください:\n$LOG\" buttons {\"OK\"} with icon caution with title \"AI ブログジェネレーター\""
        exit 1
    fi
fi

# ── ブラウザを開く ────────────────────────────────────────────
open "http://localhost:$PORT"
LAUNCH_SCRIPT

chmod +x "${MACOS_DIR}/launch"

# ── Info.plist ────────────────────────────────────────────────
cat > "${APP_BUNDLE}/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>AIブログジェネレーター</string>
  <key>CFBundleDisplayName</key>
  <string>AI ブログジェネレーター</string>
  <key>CFBundleExecutable</key>
  <string>launch</string>
  <key>CFBundleIdentifier</key>
  <string>com.local.ai-blog-generator</string>
  <key>CFBundleVersion</key>
  <string>1.0</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

# ── アイコン生成 ──────────────────────────────────────────────
PYTHON=""
[ -f ".venv/bin/python3" ] && PYTHON=".venv/bin/python3"
[ -z "$PYTHON" ] && command -v python3 &>/dev/null && PYTHON="python3"

if [ -n "$PYTHON" ] && $PYTHON -c "import PIL" 2>/dev/null; then
    echo "🎨 アイコンを生成中..."
    $PYTHON generate_icon.py
    cp AppIcon.icns "${RES_DIR}/"
    rm -f AppIcon.icns
else
    echo "⚠️  Pillow が見つからないためアイコンをスキップしました"
fi

echo ""
echo "✅ ${APP_BUNDLE} を作成しました！"
echo ""
echo "── 配布方法 ──────────────────────────────────────────────"
echo "  .app 単体を渡すだけでOKです:"
echo "  ① ${APP_BUNDLE} を相手に渡す（AirDrop / USB / クラウドなど）"
echo "  ② 相手は右クリック →「開く」→「開く」（初回のみ）"
echo "  ③ セットアップ画面に従って Ollama をインストール"
echo "  ④ セットアップ後にもう一度起動するだけ"
echo ""
echo "  ⚠️  受け取った側のPCに必要なもの:"
echo "     - macOS 12 以上"
echo "     - Ollama（アプリ初回起動時に案内が表示されます）"
echo "     - インターネット接続（初回セットアップ時のみ）"
echo "     ※ Python は自動でインストールされます"
echo "─────────────────────────────────────────────────────────"
