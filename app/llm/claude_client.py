"""Claude API クライアント。

設計ポイント:
  - グレード定義 + 評価フレームの大きな system プロンプトはほぼ不変なので、
    prompt caching (ephemeral) を有効化してコストを下げる。
  - 出力は JSON Schema で固定し、後段でパースしやすくする。
  - thinking: adaptive を有効にして難しい判断は深く考えさせる。
"""

from __future__ import annotations

import json
from typing import Any

import anthropic

# 評価哲学 (フェアネス憲章)。すべての評価で system プロンプトの先頭に置く。
FAIRNESS_PREAMBLE = """\
あなたは HR の評価アシスタントです。以下の「フェアネス憲章」を絶対に守ってください。

# フェアネス憲章
誰もが尊重され、公平に評価される組織でありたい。
立場や背景に関わらず、機会が与えられ、成果や挑戦が正しく認められる環境をつくる。
互いの違いを力に変え、信頼と透明性を基盤としたチームで、真にフェアな社会を体現していく。

# 評価原則
1. 評価は事実 (定量データ・観測可能な行動) に基づいて行う。
2. 「業務量 × 努力アピール」に騙されない。アウトプット (顧客価値・事業インパクト) で判断する。
3. 不確かな項目は「不明」と明示する。憶測で減点しない。
4. 個人属性 (性別・年齢・国籍・出身大学・職歴の長短など) を理由にしない。
5. 評価対象者のグレード定義 (期待値) と照らし合わせて判断する。

# 出力ルール
- スコアは 0.0〜5.0 の数値で返す (5.0 が最高評価)。
- スコアの根拠 (rationale) には必ず「どの事実を根拠にしたか」を書く。
- evidence にはスコア算出に使った具体データを最低 2 件挙げる (なければ空配列)。
- 「私頑張った系」アピールが見つかったら flags に "effort_overclaim" を付ける。
"""


# 出力 JSON Schema (構造化出力で固定)
EVALUATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "a_tier1_kpi",
                            "b_tier2_kpi",
                            "c_action_item",
                            "d_business_qual",
                            "e_other_qual",
                            "f_not_requirement",
                            "g_manager_note",
                        ],
                    },
                    "score": {"type": "number", "minimum": 0.0, "maximum": 5.0},
                    "rationale": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "flags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["category", "score", "rationale", "evidence", "flags"],
                "additionalProperties": False,
            },
        },
        "overall_rating": {
            "type": "string",
            "enum": [
                "Exceeds Expectations",
                "Meets Expectations",
                "Partially Meets",
                "Below Expectations",
            ],
        },
        "summary": {"type": "string"},
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
        "fairness_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "category_scores",
        "overall_rating",
        "summary",
        "recommended_actions",
        "fairness_notes",
    ],
    "additionalProperties": False,
}


class ClaudeEvaluator:
    """Claude による評価実行クライアント。"""

    def __init__(self, api_key: str, model: str = "claude-opus-4-6") -> None:
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def evaluate(
        self,
        grade_definition: str,
        employee_summary: str,
        evidence_payload: str,
    ) -> dict[str, Any]:
        """評価実行。

        Args:
            grade_definition: 対象者グレードの定義 (期待値) テキスト
            employee_summary: 評価対象者の基本情報 (氏名・部門・期間)
            evidence_payload: 収集された全データ (KPI / カレンダ / Slack / 行動) を
                Markdown もしくは JSON 文字列で連結したもの
        """
        # システムプロンプトは「フェアネス憲章 + グレード定義」で構成する。
        # 同じグレードの評価が複数走ることが多いので cache_control を付与し、
        # 2 回目以降は cache hit でコストを 9 割削減する。
        system_blocks = [
            {
                "type": "text",
                "text": FAIRNESS_PREAMBLE,
            },
            {
                "type": "text",
                "text": (
                    "# 適用するグレード定義\n"
                    "以下が評価対象者のグレードに対する期待値です。\n"
                    "このグレードに照らし合わせて評価してください。\n\n"
                    + grade_definition
                ),
                "cache_control": {"type": "ephemeral"},
            },
        ]

        user_text = (
            "# 評価対象者\n"
            f"{employee_summary}\n\n"
            "# 収集データ (定量 + 定性)\n"
            f"{evidence_payload}\n\n"
            "上記データに基づき、a〜g の各カテゴリでスコアと根拠を出してください。\n"
            "- a: tier1 KPI (売上、ARR、OTR、HC)\n"
            "- b: tier2 KPI (churn、MQL/SQL、コストダウン)\n"
            "- c: 重要 countable アクション (ケーススタディ、ISMS、特許等)\n"
            "- d: 業務系定性 (事業推進貢献、有効アウトプット、mtg/Ops 貢献)\n"
            "- e: その他定性 (AI ツール活用、社内コミュニケーション)\n"
            "- f: not 要件 (業務量 × 「私頑張った！」アピールの無力化)\n"
            "- g: 上司からの補足コメント\n"
            "対象データがない項目はスコアを 2.5 (中立) とし、rationale に「データ不足」と書いてください。"
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=system_blocks,
            messages=[{"role": "user", "content": user_text}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": EVALUATION_SCHEMA,
                }
            },
        )

        # 構造化出力により最初の text ブロックは確実に valid JSON
        text = next(
            (b.text for b in response.content if getattr(b, "type", "") == "text"),
            None,
        )
        if not text:
            raise RuntimeError("Claude からの応答に text ブロックがありません")

        # キャッシュヒット状況をログ用に保持できるよう usage を埋め込む
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
