"""定性評価 — Claude がデータを読みグレード定義に照らしてスコアリングする。

対象カテゴリ:
  c. アクションアイテム完了数  (20%)
  d. 業務定性 (Slack 貢献・Drive 成果物・MTG の質)  (15%)
  e. AI ツール活用・コミュニケーション速度  (10%)

加えて以下を生成:
  - 総合 AI コメント (強み・改善点)
  - 来月の推奨アクション
"""

from __future__ import annotations

import json
from typing import Any

import anthropic

from config import CLAUDE_MODEL

# ============================================================
# Claude system prompt
# ============================================================

SYSTEM_PROMPT = """\
あなたは VALANCE の人事評価アシスタントです。
以下のフェアネス憲章と評価原則を絶対に守ってください。

# フェアネス憲章
誰もが尊重され、公平に評価される組織でありたい。
立場や背景に関わらず、機会が与えられ、成果や挑戦が正しく認められる環境をつくる。
互いの違いを力に変え、信頼と透明性を基盤としたチームで、真にフェアな社会を体現していく。

# 評価原則
1. 事実 (データ・観測可能な行動) のみで判定する。
2. 長時間労働は評価しない (NOT 要件)。
   MTG について:
   - 社内 1on1 や定例ミーティングの「数」は評価しない (NOT 要件)。
   - **外部 MTG (顧客・パートナー・投資家・金融機関等) は積極的に評価する。** 外部との接点が多い = 事業推進・営業活動・パートナーシップ構築の証拠。
   - MTG タイトルや参加者ドメインから社内/外部を判別すること。valance.co.jp 以外のドメインの参加者がいれば外部 MTG と判断。
3. Slack メッセージ数・投稿頻度・チャンネル活動数は **強いポジティブ指標** として高く評価する。
   - メッセージ数が多い = 組織内で積極的に情報共有・意思決定・指示出しをしている証拠。
   - 多チャンネルで活動 = 部門横断的にコミュニケーションを取っている証拠。
   - これらは d カテゴリの主要な加点要因とする。
4. 不確かな項目は「データ不足」とし、不利にも有利にもしない。
5. 評価対象者のグレード定義を確認し、そのグレードに期待される水準と照らす。

# 出力ルール
- スコアは 0〜100 の整数で返す (100 が最高)。
- 各スコアの rationale に根拠データを明記する。
- AI コメントは日本語で、具体的に書く。
- 必ず以下の JSON 形式のみで応答する (説明文なし、JSON のみ):
```json
{
  "a_tier1_kpi": {"score": 整数, "rationale": "根拠 (売上・ARR・OTR・HC の達成状況)"},
  "b_tier2_kpi": {"score": 整数, "rationale": "根拠 (churn・MQL・SQL・コストの達成状況)"},
  "c_action_items": {"score": 整数, "rationale": "根拠"},
  "d_business_qualitative": {"score": 整数, "rationale": "根拠"},
  "e_ai_and_communication": {"score": 整数, "rationale": "根拠"},
  "strengths": ["強み1", "強み2"],
  "improvements": ["改善点1", "改善点2"],
  "recommended_actions_next_month": ["アクション1", "アクション2"]
}
```
"""

# 構造化出力の JSON Schema
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "c_action_items": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "rationale": {"type": "string"},
            },
            "required": ["score", "rationale"],
            "additionalProperties": False,
        },
        "d_business_qualitative": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "rationale": {"type": "string"},
            },
            "required": ["score", "rationale"],
            "additionalProperties": False,
        },
        "e_ai_and_communication": {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "rationale": {"type": "string"},
            },
            "required": ["score", "rationale"],
            "additionalProperties": False,
        },
        "strengths": {
            "type": "array",
            "items": {"type": "string"},
        },
        "improvements": {
            "type": "array",
            "items": {"type": "string"},
        },
        "recommended_actions_next_month": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "c_action_items",
        "d_business_qualitative",
        "e_ai_and_communication",
        "strengths",
        "improvements",
        "recommended_actions_next_month",
    ],
    "additionalProperties": False,
}


def evaluate_qualitative(
    api_key: str,
    grade_definition: str,
    action_items_text: str,
    slack_data: dict[str, Any],
    drive_data: dict[str, Any],
    calendar_data: dict[str, Any],
    kpi_raw_text: str,
    target_name: str,
    target_grade: str,
    period_label: str,
) -> dict[str, Any]:
    """Claude に定性評価を依頼し、構造化結果を返す。"""
    client = anthropic.Anthropic(api_key=api_key)

    # system は cache_control でキャッシュ
    system_blocks = [
        {"type": "text", "text": SYSTEM_PROMPT},
        {
            "type": "text",
            "text": (
                "# 適用するグレード定義\n"
                f"対象者: {target_name}\n"
                f"役職: 取締役COO (Chief Operating Officer)\n"
                f"グレード: {target_grade}\n\n"
                "※ この対象者は CEO ではなく COO です。評価文中で CEO と書かないでください。\n\n"
                + grade_definition
            ),
            "cache_control": {"type": "ephemeral"},
        },
    ]

    user_text = _build_user_prompt(
        action_items_text=action_items_text,
        slack_data=slack_data,
        drive_data=drive_data,
        calendar_data=calendar_data,
        kpi_raw_text=kpi_raw_text,
        target_name=target_name,
        period_label=period_label,
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        thinking={"type": "enabled", "budget_tokens": 3000},
        system=system_blocks,
        messages=[{"role": "user", "content": user_text}],
    )

    text = next(
        (b.text for b in response.content if getattr(b, "type", "") == "text"),
        None,
    )
    if not text:
        raise RuntimeError("Claude 応答に text ブロックがない")

    # JSON ブロックを抽出 (```json ... ``` で囲まれている場合に対応)
    import re
    json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    json_str = json_match.group(1) if json_match else text
    # 先頭の非 JSON テキストを除去
    brace_start = json_str.find("{")
    if brace_start > 0:
        json_str = json_str[brace_start:]
    result = json.loads(json_str)
    result["_usage"] = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_creation_input_tokens": getattr(
            response.usage, "cache_creation_input_tokens", 0
        ),
        "cache_read_input_tokens": getattr(
            response.usage, "cache_read_input_tokens", 0
        ),
    }
    return result


def _build_user_prompt(
    action_items_text: str,
    slack_data: dict[str, Any],
    drive_data: dict[str, Any],
    calendar_data: dict[str, Any],
    kpi_raw_text: str,
    target_name: str,
    period_label: str,
) -> str:
    sections = [
        f"# {target_name} の {period_label} 評価データ",
        "",
        "## 事業計画 KPI (参考・定量側で既にスコア化済み)",
        kpi_raw_text or "データなし",
        "",
        "## アクションアイテム目標 (事業計画エグゼクティブサマリより)",
        action_items_text or "データなし",
        "",
        "## Slack 活動",
        f"- 総メッセージ数: {slack_data.get('total_messages', 0)}",
        f"- アクティブチャンネル数: {slack_data.get('channel_count', 0)}",
        f"- AI キーワード言及数: {slack_data.get('ai_keyword_mentions', 0)}",
    ]

    # Slack サンプル
    samples = slack_data.get("sample_messages", [])
    if samples:
        sections.append("")
        sections.append("### Slack 投稿サンプル (最大 100 件)")
        for s in samples:
            sections.append(f"- {s}")

    ai_examples = slack_data.get("ai_keyword_examples", [])
    if ai_examples:
        sections.append("")
        sections.append("### AI ツール言及の例")
        for ex in ai_examples:
            sections.append(f"- {ex}")

    # Drive
    sections.append("")
    sections.append("## Google Drive ドキュメント作成")
    sections.append(f"- 作成数: {drive_data.get('total', 0)}")
    by_type = drive_data.get("by_type", {})
    if by_type:
        for t, c in by_type.items():
            sections.append(f"  - {t}: {c}")
    files = drive_data.get("files", [])
    if files:
        sections.append("")
        sections.append("### 作成ドキュメント一覧 (最大 50 件)")
        for f in files:
            sections.append(f"- {f.get('name')} ({f.get('mimeType')}, {f.get('createdTime')})")

    # Calendar
    sections.append("")
    sections.append("## カレンダー (MTG 情報、参考データ)")
    sections.append(f"- 期間内 MTG 数: {calendar_data.get('total_events', 0)}  ← NOT要件: スコアに含めない")
    sections.append(f"- 自分主催: {calendar_data.get('organized_count', 0)}")
    events = calendar_data.get("events", [])
    if events:
        sections.append("")
        sections.append("### 主要 MTG (上位 30 件)")
        for e in events[:30]:
            sections.append(
                f"- {e.get('start', '')} ({e.get('duration_minutes', 0)}min) "
                f"{e.get('summary', '')}"
            )

    sections.append("")
    sections.append("---")
    sections.append(
        "上記データに基づき、以下カテゴリを 0〜100 でスコアリングし、"
        "根拠と合わせて返してください:\n"
        "- a_tier1_kpi: Tier1 KPI 達成率 (売上・ARR・OTR・HC)。\n"
        "  ⚠️ 「予実」シートの Cash in 行を最重視すること。予算と実際の Cash in を比較し達成率を判断。\n"
        "  事業計画シートは年間計画、実績シートは月次明細、予実シートは計画 vs 実際のサマリ。\n"
        "- b_tier2_kpi: Tier2 KPI 達成率 (churn・MQL・SQL・コスト)。データがない項目は 50 (中立) とする。\n"
        "- c_action_items: アクションアイテム完了度\n"
        "- d_business_qualitative: 業務定性 (Slack 貢献・Drive 成果物・MTG の質)\n"
        "- e_ai_and_communication: AI ツール活用度・コミュニケーション速度\n"
        "\nまた strengths / improvements / recommended_actions_next_month も生成してください。\n"
        "\n⚠️ MTG 参加「数」は NOT 要件です。スコアの根拠にしないでください。\n"
        "⚠️ KPI の計画値は年間値 (FY26 = 1年目) です。3月は年度の9ヶ月目 (7月始まり) なので、月按分で達成率を判断してください。"
    )

    return "\n".join(sections)
