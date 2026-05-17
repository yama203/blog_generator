#!/bin/bash
# Move to project root (one level up from this file)
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

# Activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "❌ 仮想環境が見つかりません。"
    echo "   先に setup.sh を実行してください。"
    read -p "Enterキーを押して閉じてください..."
    exit 1
fi

echo "✅ AI ブログジェネレーターを起動しています..."
echo "   ブラウザが自動で開きます。"
echo "   終了するにはこのウィンドウを閉じてください。"
echo ""

streamlit run app.py \
    --server.headless true \
    --browser.gatherUsageStats false \
    --server.port 8501

read -p "終了しました。Enterキーを押して閉じてください..."
