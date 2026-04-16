"""定量評価 — KPI 達成率をスコア化する。

a. Tier1 KPI 達成率 (売上・ARR・OTR・HC)  → 30%
b. Tier2 KPI 達成率 (churn・MQL・SQL・コスト) → 25%

スコアリング関数:
  - 達成率 100% → 80 点
  - 達成率 120% → 100 点
  - 達成率 80%  → 60 点
  - 線形補間。0% で 0 点、120% 以上で 100 点キャップ
"""

from __future__ import annotations

from typing import Any


def achievement_to_score(achievement_rate: float) -> float:
    """達成率 (0.0〜∞) → 0〜100 スコア。"""
    if achievement_rate <= 0:
        return 0.0
    if achievement_rate >= 1.2:
        return 100.0
    # 線形: 0% → 0, 100% → 80, 120% → 100
    if achievement_rate <= 1.0:
        return achievement_rate * 80.0
    # 100% 〜 120% の 20% 幅で 80 → 100
    return 80.0 + (achievement_rate - 1.0) * 100.0


def score_kpis(
    kpi_data: list[dict[str, Any]],
    kpi_raw_text: str,
) -> dict[str, Any]:
    """KPI データからスコアを算出。

    kpi_data: sheets.fetch_kpi_data() の結果。ヘッダ構造不定のため柔軟に解析。
    kpi_raw_text: シートのテキスト (スコアリングできない場合に LLM に渡す用)。

    Returns:
        {
            "tier1": {"score": float, "details": [...]},
            "tier2": {"score": float, "details": [...]},
            "raw_text": str,  # LLM 用テキスト
        }
    """
    tier1_scores: list[float] = []
    tier2_scores: list[float] = []
    tier1_details: list[dict[str, Any]] = []
    tier2_details: list[dict[str, Any]] = []

    for row in kpi_data:
        name = _find_value(row, ["指標名", "name", "指標", "KPI", "項目"])
        tier = _find_value(row, ["tier", "Tier", "ティア", "区分"])
        plan = _to_float(_find_value(row, ["計画", "plan", "target", "目標"]))
        actual = _to_float(_find_value(row, ["実績", "actual", "result", "結果"]))

        if plan is None or plan == 0:
            continue
        if actual is None:
            # 実績未入力 → LLM に任せる
            continue

        rate = actual / plan
        score = achievement_to_score(rate)
        detail = {
            "name": name,
            "plan": plan,
            "actual": actual,
            "achievement_rate": round(rate, 3),
            "score": round(score, 1),
        }

        tier_str = str(tier).strip()
        if tier_str in ("2", "Tier2", "tier2"):
            tier2_scores.append(score)
            tier2_details.append(detail)
        else:
            # デフォルトは Tier1
            tier1_scores.append(score)
            tier1_details.append(detail)

    return {
        "tier1": {
            "score": _avg(tier1_scores),
            "details": tier1_details,
        },
        "tier2": {
            "score": _avg(tier2_scores),
            "details": tier2_details,
        },
        "raw_text": kpi_raw_text,
    }


def _find_value(row: dict[str, Any], candidates: list[str]) -> Any:
    """辞書から候補キーのいずれかに一致する値を返す。"""
    for key in candidates:
        if key in row:
            return row[key]
    # 部分一致
    for key in candidates:
        for rk, rv in row.items():
            if key.lower() in rk.lower():
                return rv
    return None


def _to_float(v: Any) -> float | None:
    if v in (None, "", "—", "-"):
        return None
    try:
        return float(str(v).replace(",", "").replace("¥", "").replace("円", ""))
    except (TypeError, ValueError):
        return None


def _avg(scores: list[float]) -> float:
    if not scores:
        return 50.0  # データなし → 中立
    return sum(scores) / len(scores)
