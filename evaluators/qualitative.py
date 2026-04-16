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
2. 長時間労働や MTG 参加数は評価しない (NOT 要件)。
3. Slack メッセージ数はポジティブ指標として扱う。
4. 不確かな項目は「データ不足」とし、不利にも有利にもしない。
5. 評価対象者のグレード定義を確認し、そのグレードに期待される水準と照らす。

# 出力ルール
- スコアは 0〜100 の整数で返す (100 が最高)。
- 各スコアの rationale に根拠データを明記する。
- AI コメントは日本語で、具体的に書く。
"""

# 構造化出力の JSON Schema
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "c_action_items": {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                "rationale": {"type": "string"},
            },
            "required": ["score", "rationale"],
            "additionalProperties": False,
        },
        "d_business_qualitative": {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                "rationale": {"type": "string"},
            },
            "required": ["score", "rationale"],
            "additionalProperties": False,
        },
        "e_ai_and_communication": {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 100},
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
                f"対象者: {target_name} (グレード: {target_grade})\n\n"
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
        output_config={
            "format": {
                "type": "json_schema",
                "schema": OUTPUT_SCHEMA,
            }
        },
    )

    text = next(
        (b.text for b in response.content if getattr(b, "type", "") == "text"),
        None,
    )
    if not text:
        raise RuntimeError("Claude 応答に text ブロックがない")

    result = json.loads(text)
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
        "- c_action_items: アクションアイテム完了度\n"
        "- d_business_qualitative: 業務定性 (Slack 貢献・Drive 成果物・MTG の質)\n"
        "- e_ai_and_communication: AI ツール活用度・コミュニケーション速度\n"
        "\nまた strengths / improvements / recommended_actions_next_month も生成してください。\n"
        "\n⚠️ MTG 参加「数」は NOT 要件です。スコアの根拠にしないでください。"
    )

    return "\n".join(sections)
