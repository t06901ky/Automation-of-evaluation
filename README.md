# VALANCE 月次評価自動化システム

COO（Kota）を対象とした PoC。毎月 1 日に前月分のデータを自動収集し、
Claude が定性評価を行い、PDF レポートを生成する。

---

## 評価項目と重みづけ

| | カテゴリ | 重み | データソース |
|---|---|---|---|
| **a** | Tier1 KPI 達成率 (売上・ARR・OTR・HC) | 30% | Google Sheets |
| **b** | Tier2 KPI 達成率 (churn・MQL・SQL・コスト) | 25% | Google Sheets |
| **c** | アクションアイテム完了数 | 20% | Google Slides + Claude |
| **d** | 業務定性 (Slack 貢献・Drive 成果物・MTG の質) | 15% | Slack + Drive + Calendar |
| **e** | AI ツール活用・コミュニケーション速度 | 10% | Slack (キーワード検出) |

### NOT 要件 (評価に含めない・減点もしない)
- 長時間労働・残業時間
- MTG 参加数
- ※ Slack メッセージ数はポジティブ指標として d に含める

---

## セットアップ

### 1. 依存インストール

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> **WeasyPrint のシステム依存**: PDF 生成に WeasyPrint を使用。
> Ubuntu: `sudo apt install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0`
> macOS: `brew install pango`
> 詳細: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html

### 2. Google サービスアカウント

1. [GCP Console](https://console.cloud.google.com/) でプロジェクト作成
2. 以下 API を有効化:
   - Google Sheets API
   - Google Slides API
   - Google Drive API
   - Google Calendar API
3. サービスアカウントを作成 → JSON キーをダウンロード
4. `credentials/service_account.json` に配置
5. **以下のリソースに SA メールアドレスの閲覧権限を付与:**
   - グレード定義シート: `16N2D1hCDlx2Vl-Ez19WrA_lK5YLueSnaDvivL7rhSfU`
   - KPI シート: `1Lo_udJ5YeYlacpMOyJRHMNSl-Ph7tilL`
   - 事業計画スライド: `1eJ6BB14aYBnWXa1kCUS0BDXIe29cNbb8`
   - 対象者のカレンダー
   - Drive フォルダ (ドキュメント集計用)

### 3. Slack Bot

[Slack API](https://api.slack.com/apps) で App を作成。

必要な Bot Token Scopes:
- `channels:history` / `channels:read`
- `groups:history` / `groups:read`
- `users:read` / `users:read.email`

ワークスペースにインストールして Bot Token (xoxb-) を取得。

### 4. 環境変数

```bash
cp .env.example .env
# .env を編集して各キーを埋める
```

| 変数 | 説明 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API キー |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | SA JSON パス |
| `SLACK_BOT_TOKEN` | xoxb- |
| `TARGET_USER_EMAIL` | 評価対象者メール |
| `TARGET_USER_NAME` | 表示名 |
| `TARGET_USER_GRADE` | グレード (例: `役員`) |
| `TARGET_CALENDAR_ID` | カレンダー ID (通常はメール) |
| `DRIVE_FOLDER_ID` | Drive フォルダ ID (任意) |

---

## 使い方

### 本番実行 (前月分を評価)

```bash
python main.py
```

`output/` に以下が生成される:
- `2026年3月_Kota_evaluation.pdf` — PDF レポート
- `2026年3月_Kota_evaluation.json` — 構造化データ (監査用)

### Dry Run (ダミーデータで PDF の見た目確認)

```bash
python main.py --dry-run
```

API を叩かずにダミーデータで PDF のみ生成。レイアウト確認用。

---

## PDF レポートの構成

1. **表紙** — 評価対象者・評価期間・総合スコア
2. **グレード定義** — 適用されたグレードの期待値
3. **定量 KPI** — Tier1/Tier2 の計画 vs 実績、達成率
4. **アクションアイテム** — 事業計画目標に対する進捗
5. **定性評価** — Slack/Drive/AI 活用の Claude 評価
6. **NOT 要件** — 除外項目の明示
7. **総合評価** — 加重平均スコア・強み・改善点
8. **来月の推奨アクション**

---

## ディレクトリ構成

```
├── main.py                  # エントリーポイント
├── config.py                # API 認証・設定・データソース ID
├── collectors/
│   ├── sheets.py            # Google Sheets (グレード定義・KPI)
│   ├── slides.py            # Google Slides (アクションアイテム)
│   ├── slack.py             # Slack (投稿内容・メッセージ数・AI キーワード)
│   ├── drive.py             # Google Drive (ドキュメント作成数)
│   └── calendar.py          # Google Calendar (MTG 情報)
├── evaluators/
│   ├── quantitative.py      # KPI スコアリング (a, b)
│   └── qualitative.py       # Claude 定性評価 (c, d, e)
├── report/
│   └── pdf_generator.py     # HTML → PDF (WeasyPrint)
├── credentials/             # .gitignore 対象
├── output/                  # 生成 PDF 保存先
├── requirements.txt
└── .env.example
```

---

## 未解決事項

### AI ツール使用頻度の取得方法
Claude/Gemini/NotebookLM の使用履歴は API から直接取得できない。
現在の実装では **Slack 投稿内の AI キーワード言及数** をプロキシ指標として使用。
検出キーワード: `claude`, `gemini`, `notebooklm`, `chatgpt`, `copilot`, `ai` 等。

### KPI 実績値の入力方法
事業計画の「計画値」はシートから自動取得。「実績値」の入力方法は要検討:
- 案 A: KPI シートに実績列を追加して手入力
- 案 B: 別途入力フォーム (Google Forms) を用意

### Slack 全チャンネルのレート制限
Slack API の Tier 2 制限 (20 req/min) に対応済み:
- ページネーション + `tenacity` によるリトライ
- チャンネル間に 1.2 秒のスリープ

---

## 評価ロジック

1. **グレード確認**: シートからグレード定義を読み込み、評価基準として使用
2. **データ収集**: 前月 1 日〜末日を対象に各 API からデータ取得
3. **定量評価 (a・b)**: 計画値 vs 実績値の達成率をスコア化 (達成率 100% → 80 点、120% 以上 → 100 点)
4. **定性評価 (c・d・e)**: 収集データを Claude が読みグレード定義に照らして 0〜100 でスコアリング
5. **総合スコア**: 重みづけ加重平均で算出
6. **AI コメント**: 強み・改善点・来月の推奨アクションを Claude が生成
7. **PDF 出力**: 日本語レポートとして保存
