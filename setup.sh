#!/bin/bash
# VALANCE 月次評価システム — ローカルセットアップ
set -e

echo "=== 1. Python 仮想環境 ==="
python3 -m venv .venv
source .venv/bin/activate

echo "=== 2. 依存インストール ==="
pip install -r requirements.txt

echo "=== 3. .env 確認 ==="
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  .env を作成しました。以下を編集してください:"
    echo "    - ANTHROPIC_API_KEY"
    echo "    - SLACK_BOT_TOKEN"
    echo "    - TARGET_USER_EMAIL / TARGET_USER_NAME"
    echo ""
    echo "    vi .env"
    exit 1
fi

echo "=== 4. credentials 確認 ==="
if [ ! -f credentials/service_account.json ]; then
    echo "⚠️  credentials/service_account.json が見つかりません"
    echo "    GCP Console からダウンロードして配置してください"
    exit 1
fi

echo "=== 5. Dry Run (PDF レイアウト確認) ==="
python main.py --dry-run

echo ""
echo "✅ セットアップ完了！"
echo ""
echo "本番実行:  python main.py"
echo "Dry Run:   python main.py --dry-run"
