#!/usr/bin/env bash
# ngrokで一時的に公開する起動スクリプト
# 使い方:
#   1. brew install ngrok （初回のみ）
#   2. ngrok config add-authtoken <YOUR_TOKEN>  （初回のみ、https://dashboard.ngrok.com/get-started/your-authtoken）
#   3. bash scripts/start_ngrok.sh
#
# 実行するとStreamlit起動 + ngrokトンネル作成、URLがターミナルに表示される
set -e

cd "$(dirname "$0")/.."

# ngrokがあるか確認
if ! command -v ngrok &> /dev/null; then
    echo "❌ ngrok が見つかりません。以下でインストールしてください:"
    echo "   brew install ngrok"
    echo "   ngrok config add-authtoken <YOUR_TOKEN>"
    exit 1
fi

# .env を読み込む（API_KEY等）
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

PORT=${PORT:-8501}

echo "🚀 Streamlit を起動..."
streamlit run admin/streamlit_app.py --server.port $PORT --server.headless true &
STREAMLIT_PID=$!

# Streamlit起動待ち
sleep 4

echo "🌐 ngrok トンネル作成..."
ngrok http $PORT &
NGROK_PID=$!

trap "echo 'shutting down...'; kill $STREAMLIT_PID $NGROK_PID 2>/dev/null" EXIT

echo ""
echo "✅ 起動完了。ngrok の Forwarding URL を隅田さんに共有してください。"
echo "   Ctrl+C で停止します。"
wait
