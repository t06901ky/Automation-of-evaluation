# Automation of Evaluation — HR 評価自動化アプリケーション

> 「誰もが尊重され、公平に評価される組織でありたい。
> 立場や背景に関わらず、機会が与えられ、成果や挑戦が正しく認められる環境をつくる。
> 互いの違いを力に変え、信頼と透明性を基盤としたチームで、真にフェアな社会を体現していきます。」

このフェアネス憲章を貫くため、HR 業務のうち最も時間がかかる「評価」について
**工数をほぼゼロにする** ことを目指したアプリケーションです。

---

## 何ができるか

Google Workspace / Slack / Google カレンダーから評価対象者のデータを自動収集し、
グレード定義に照らし合わせた評価レポート (Markdown + JSON) を生成します。

### 評価項目 (優先順位順)

| | カテゴリ | データソース | 重み (既定) |
|---|---|---|---|
| **a** | tier1 KPI (売上、ARR、OTR、HC) の定量 | KPI シート | 0.30 |
| **b** | tier2 KPI (churn、MQL/SQL、コストダウン) | KPI シート | 0.20 |
| **c** | 重要 countable アクション (ケーススタディ、ISMS、特許等) | アクションアイテムシート | 0.18 |
| **d** | 業務系定性 (事業推進貢献、有効アウトプット、mtg/Ops 貢献) | カレンダー + Slack | 0.13 |
| **e** | その他定性 (AI ツール活用、社内コミュニケーション) | Slack | 0.09 |
| **f** | not 要件 (業務量 × 「私頑張った！」アピールの無力化) | カレンダー + Slack | 0.05 (減点) |
| **g** | 上司からの補足コメント | コメントシート | 0.05 |

評価エンジンは Claude (Opus 4.6) を用い、**事実ベース・グレード定義準拠** で判定します。
重みづけは `app/models.py` の `DEFAULT_WEIGHTS` を編集すれば変更できます。

---

## アーキテクチャ

```
┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐
│ Google Calendar    │  │ Google Sheets      │  │ Slack              │
│ (会議・会議貢献)     │  │ (グレード定義/KPI/   │  │ (コミュニケーション   │
│                    │  │  アクションアイテム)  │  │  量・質・時間外活動)  │
└─────────┬──────────┘  └─────────┬──────────┘  └─────────┬──────────┘
          │                       │                       │
          ▼                       ▼                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Collectors (app/collectors/)                       │
│   calendar_collector / sheets_collector / slack_collector             │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
                  EvaluationContext (Pydantic)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│              Evaluator (app/evaluators/engine.py)                     │
│   1. payload_builder で Markdown 化                                   │
│   2. Claude (フェアネス憲章 + グレード定義は prompt cache 済み) に投入   │
│   3. JSON Schema で構造化出力 → カテゴリスコア取得                     │
│   4. 重みづけして総合スコア                                           │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
                EvaluationReport → Markdown + JSON
```

### Claude API 設計のポイント

- **prompt caching**: グレード定義 + フェアネス憲章は system プロンプトに置き
  `cache_control: ephemeral` を付与。同じグレードの評価が複数走るときに
  入力トークンコストを ~90% 削減します (`app/llm/claude_client.py`)。
- **構造化出力 (`output_config.format`)**: スコア / 根拠 / フラグを JSON Schema で
  固定し、後段のレポート生成を堅牢にします。
- **adaptive thinking**: 微妙な定性判断には Claude が自動で思考時間を確保します。

---

## セットアップ

### 1. 依存関係のインストール

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Google Workspace の準備

評価では他のメンバーのカレンダー・シートにアクセスする必要があるので、
**サービスアカウント + Domain-Wide Delegation** を使います。

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成
2. 以下 API を有効化:
   - Google Calendar API
   - Google Sheets API
   - Google Drive API
   - Admin SDK API (任意。従業員一覧の自動取得に利用)
3. サービスアカウントを作成し、JSON キーをダウンロード
4. Google Workspace 管理コンソール → セキュリティ → API コントロール →
   ドメイン全体の委任 で、サービスアカウントの Client ID と次のスコープを登録:

   ```
   https://www.googleapis.com/auth/calendar.readonly
   https://www.googleapis.com/auth/spreadsheets.readonly
   https://www.googleapis.com/auth/drive.metadata.readonly
   https://www.googleapis.com/auth/admin.directory.user.readonly
   ```

5. JSON キーを `./credentials/service_account.json` に配置

### 3. Slack の準備

[Slack API](https://api.slack.com/apps) で App を作成し、以下スコープを付与:

- **Bot Token Scopes**: `users:read`, `users:read.email`, `channels:history`,
  `channels:read`, `groups:read`
- **User Token Scopes**: `search:read` (search.messages を使うため必須)

ワークスペースにインストールし、Bot Token (xoxb-) と User Token (xoxp-) を取得。

### 4. Anthropic API キー

[Anthropic Console](https://console.anthropic.com/) で API キーを発行。

### 5. 環境変数

`.env.example` を `.env` にコピーして埋めます:

```bash
cp .env.example .env
$EDITOR .env
```

主な項目:

| 変数 | 内容 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API キー |
| `CLAUDE_MODEL` | 既定 `claude-opus-4-6` |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | サービスアカウント JSON のパス |
| `GOOGLE_DELEGATED_USER` | 委任先のドメイン管理者メール |
| `GRADE_DEFINITION_SHEET_ID` | グレード定義シートの ID |
| `KPI_SHEET_ID` | KPI シートの ID (任意) |
| `ACTION_ITEMS_SHEET_ID` | アクションアイテム / 上司コメントシートの ID (任意) |
| `SLACK_BOT_TOKEN` | xoxb- |
| `SLACK_USER_TOKEN` | xoxp- |
| `EVALUATION_WINDOW_DAYS` | 評価対象期間 (既定 90 日) |

### 6. シート構造

各シートで期待する列名は以下の通り。1 行目をヘッダにしてください。

#### 従業員マスタ (`employees`)
| email | name | grade | department | manager_email |
|---|---|---|---|---|

#### KPI (`kpis`)
| name | tier | target | actual | owner_email | notes |
|---|---|---|---|---|---|

#### アクションアイテム (`action_items`)
| title | owner_email | status | due_date | completed_date | importance | description |
|---|---|---|---|---|---|---|

#### 上司コメント (`manager_notes`)
| employee_email | manager_email | text | created_at |
|---|---|---|---|

シート名 (タブ名) は CLI / `sheets_collector` の引数で変更可能です。

---

## 使い方

### 1 名のみ評価

```bash
python -m app.cli evaluate \
  --email alice@example.com \
  --name "Alice" \
  --grade G3 \
  --department Sales \
  --manager-email bob@example.com
```

実行後、以下が `./reports/` に生成されます:

- `2026-04-15_alice_at_example_com.md` — 人間が読むレポート
- `2026-04-15_alice_at_example_com.json` — 構造化データ (集計用)

### 全員一括評価 (従業員シートを起点に)

```bash
python -m app.cli evaluate-all \
  --employees-sheet-id <EMPLOYEES_SHEET_ID>
```

---

## ディレクトリ構成

```
.
├── app/
│   ├── cli.py                  # CLI エントリーポイント (Typer)
│   ├── config.py               # .env ベースの設定
│   ├── models.py               # Pydantic データモデル
│   ├── collectors/             # データ収集
│   │   ├── google_auth.py
│   │   ├── calendar_collector.py
│   │   ├── sheets_collector.py
│   │   └── slack_collector.py
│   ├── evaluators/             # 評価ロジック
│   │   ├── engine.py           # オーケストレータ
│   │   ├── payload_builder.py  # LLM 入力を Markdown 化
│   │   └── report_writer.py    # MD / JSON 出力
│   └── llm/
│       └── claude_client.py    # フェアネス憲章 + prompt caching
├── requirements.txt
├── .env.example
└── README.md
```

---

## カスタマイズ

### 重みづけを変える

`app/models.py` の `DEFAULT_WEIGHTS` を編集。合計が 1.0 になるようにしてください。

```python
DEFAULT_WEIGHTS = {
    EvaluationCategory.A_TIER1_KPI: 0.40,  # KPI 偏重に
    EvaluationCategory.B_TIER2_KPI: 0.20,
    ...
}
```

### フェアネス憲章 / 評価原則を変える

`app/llm/claude_client.py` の `FAIRNESS_PREAMBLE` を編集。
ここを変えると prompt cache が無効になるので、運用安定後は変更を控えめに。

### 別のデータソースを足す

`app/collectors/` に新しいモジュールを追加し、`EvaluationContext` を拡張、
`payload_builder.py` に新セクションを追加するだけで LLM が利用してくれます。

---

## 設計上の意思決定

- **なぜ Pull 型?** Slack / Google Workspace の Webhook を待たずに「評価したいタイミングで」
  全データを取りに行ける方が運用が単純。
- **なぜ Markdown payload?** Claude が最も得意とする入力形式で、人間レビューも容易。
- **なぜ JSON Schema?** スコア・根拠・フラグの揺れを排除し、レポート生成と監査を堅牢化。
- **なぜ Prompt Caching?** 同期間に同グレードを複数評価することが多く、コストが ~90% 下がる。

---

## ロードマップ (Update 中)

- [ ] 勤怠データの統合 (HR システム連携)
- [ ] Google Drive 上のドキュメント生成数を d/e カテゴリに反映
- [ ] 評価レポートの Slack DM 配信
- [ ] 360 度フィードバックの取り込み (peer review)
- [ ] バイアス検査 (同グレード間でスコア分布の異常検知)
