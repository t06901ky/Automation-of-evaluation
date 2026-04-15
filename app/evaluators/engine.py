"""評価オーケストレータ。

入力: EvaluationContext
処理:
  1. payload_builder で LLM 入力を組み立てる
  2. ClaudeEvaluator で各カテゴリのスコアと根拠を取得
  3. 重みづけして総合スコアを算出
出力: EvaluationReport
"""

from __future__ import annotations

from app.evaluators.payload_builder import (
    build_employee_summary,
    build_evidence_payload,
)
from app.llm.claude_client import ClaudeEvaluator
from app.models import (
    DEFAULT_WEIGHTS,
    CategoryScore,
    EvaluationCategory,
    EvaluationContext,
    EvaluationReport,
)


def run_evaluation(
    ctx: EvaluationContext,
    evaluator: ClaudeEvaluator,
    weights: dict[EvaluationCategory, float] | None = None,
) -> EvaluationReport:
    """1 名分の評価を実施し、レポートを返す。"""
    weights = weights or DEFAULT_WEIGHTS

    employee_summary = build_employee_summary(ctx)
    evidence = build_evidence_payload(ctx)

    raw = evaluator.evaluate(
        grade_definition=ctx.grade_definition_text,
        employee_summary=employee_summary,
        evidence_payload=evidence,
    )

    category_scores: list[CategoryScore] = []
    for cs in raw.get("category_scores", []):
        try:
            cat = EvaluationCategory(cs["category"])
        except ValueError:
            continue
        weight = weights.get(cat, 0.0)
        score = float(cs["score"])
        category_scores.append(
            CategoryScore(
                category=cat,
                score=score,
                weight=weight,
                weighted_score=score * weight,
                rationale=cs.get("rationale", ""),
                evidence=list(cs.get("evidence", [])),
                flags=list(cs.get("flags", [])),
            )
        )

    overall = _aggregate(category_scores)

    return EvaluationReport(
        employee=ctx.employee,
        period_start=ctx.period_start,
        period_end=ctx.period_end,
        grade_definition_summary=_truncate(ctx.grade_definition_text, 600),
        overall_score=overall,
        overall_rating=raw.get("overall_rating", "Meets Expectations"),
        category_scores=category_scores,
        summary=raw.get("summary", ""),
        recommended_actions=list(raw.get("recommended_actions", [])),
        fairness_notes=list(raw.get("fairness_notes", [])),
    )


def _aggregate(scores: list[CategoryScore]) -> float:
    """重みづけ総合スコア (0〜5)。

    f カテゴリ (not 要件) は減点側として機能させる:
      f が 1.0 未満なら他カテゴリ合計から 0.3 ペナルティを引く。
    """
    total_weight = sum(s.weight for s in scores) or 1.0
    base = sum(s.weighted_score for s in scores) / total_weight

    f_score = next(
        (s.score for s in scores if s.category == EvaluationCategory.F_NOT_REQUIREMENT),
        None,
    )
    penalty = 0.0
    if f_score is not None and f_score < 1.0:
        penalty = 0.3

    return max(0.0, min(5.0, base - penalty))


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"
