"""EvaluationReport を Markdown / JSON で書き出す。"""

from __future__ import annotations

import json
from pathlib import Path

from app.models import EvaluationReport


def write_report(report: EvaluationReport, output_dir: Path) -> tuple[Path, Path]:
    """Markdown と JSON 両方で書き出し、パスのタプルを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_email = report.employee.email.replace("@", "_at_").replace(".", "_")
    base = output_dir / f"{report.period_end}_{safe_email}"

    md_path = base.with_suffix(".md")
    md_path.write_text(_to_markdown(report), encoding="utf-8")

    json_path = base.with_suffix(".json")
    json_path.write_text(
        report.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
    )

    return md_path, json_path


def _to_markdown(r: EvaluationReport) -> str:
    lines = [
        f"# 評価レポート: {r.employee.name} ({r.employee.email})",
        "",
        f"- グレード: **{r.employee.grade}**",
        f"- 部門: {r.employee.department or '不明'}",
        f"- 評価期間: {r.period_start} 〜 {r.period_end}",
        f"- 総合スコア: **{r.overall_score:.2f} / 5.00** ({r.overall_rating})",
        f"- 生成時刻: {r.generated_at.isoformat(timespec='seconds')}",
        "",
        "## サマリ",
        r.summary,
        "",
        "## カテゴリ別スコア",
        "| カテゴリ | スコア | 重み | 加重 | フラグ |",
        "|---|---|---|---|---|",
    ]
    for cs in r.category_scores:
        flags = ", ".join(cs.flags) if cs.flags else "—"
        lines.append(
            f"| {cs.category.value} | {cs.score:.2f} | {cs.weight:.2f} "
            f"| {cs.weighted_score:.2f} | {flags} |"
        )
    lines.append("")

    lines.append("## 各カテゴリの根拠")
    for cs in r.category_scores:
        lines.append(f"### {cs.category.value} — {cs.score:.2f}")
        lines.append(cs.rationale)
        if cs.evidence:
            lines.append("")
            lines.append("**根拠データ:**")
            for ev in cs.evidence:
                lines.append(f"- {ev}")
        lines.append("")

    if r.recommended_actions:
        lines.append("## 推奨アクション")
        for a in r.recommended_actions:
            lines.append(f"- {a}")
        lines.append("")

    if r.fairness_notes:
        lines.append("## フェアネス検証メモ")
        for n in r.fairness_notes:
            lines.append(f"- {n}")
        lines.append("")

    lines.append("---")
    lines.append("## 適用グレード定義 (要約)")
    lines.append("```")
    lines.append(r.grade_definition_summary)
    lines.append("```")

    return "\n".join(lines)
