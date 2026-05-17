#!/bin/bash
set -e

echo "================================================"
echo "  AI ブログジェネレーター セットアップ"
echo "================================================"
echo ""

# uv を探す（引数 > プロジェクト内 > PATH の順）
UV="${1:-}"
[ -z "$UV" ] && [ -x "$(pwd)/.uv" ] && UV="$(pwd)/.uv"
[ -z "$UV" ] && UV=$(command -v uv 2>/dev/null || true)

if [ -z "$UV" ] || [ ! -x "$UV" ]; then
    echo "❌ uv が見つかりません。"
    echo "   アプリを再起動してセットアップを行ってください。"
    exit 1
fi

echo "✅ uv: $("$UV" --version 2>/dev/null)"

echo ""
echo "Python 3.12 を準備中..."
"$UV" python install 3.12

echo ""
echo "仮想環境を作成中..."
"$UV" venv .venv --python 3.12

echo ""
echo "パッケージをインストール中（初回は数分かかります）..."
"$UV" pip install -r requirements.txt

echo ""
echo "================================================"
echo "  セットアップ完了！"
echo "================================================"
echo ""
echo "次のステップ:"
echo ""
echo "  1. Ollama をインストール (まだの場合)"
echo "     https://ollama.ai"
echo ""
echo "  2. アプリを再起動してください"
echo "     AIブログジェネレーター.app をダブルクリック"
echo ""
