"""PDF レポート生成 — WeasyPrint で HTML → PDF 変換。

構成:
  1. サマリ（対象者・期間・総合スコア・一言評価）
  2. グレード定義に対する評価
  3. カテゴリ別スコアと根拠
  4. 来月の推奨アクション
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from weasyprint import HTML

CSS = """\
@page {
    size: A4;
    margin: 20mm 15mm;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-size: 9px;
        color: #888;
    }
}
body {
    font-family: "Noto Sans JP", "Hiragino Sans", "Yu Gothic", sans-serif;
    font-size: 11px;
    line-height: 1.7;
    color: #0f0f26;
}
h1 { font-size: 20px; color: #0f0f26; border-bottom: 3px solid #02c491; padding-bottom: 6px; margin-bottom: 16px; }
h2 { font-size: 14px; color: #0f0f26; margin-top: 20px; border-bottom: 1px solid #e0e0e0; padding-bottom: 4px; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; }
th, td { border: 1px solid #d0d0d0; padding: 6px 10px; text-align: left; font-size: 10px; }
th { background: #f0faf7; font-weight: bold; color: #0f0f26; }
.score-box {
    display: inline-block; background: #0f0f26; color: #02c491;
    font-size: 32px; font-weight: bold; padding: 10px 28px; border-radius: 8px;
}
.header { text-align: center; margin-bottom: 20px; }
.header p { margin: 4px 0; color: #555; }
.grade-box { background: #f7fdfb; border-left: 3px solid #02c491; padding: 10px 14px; border-radius: 4px; font-size: 10px; margin: 8px 0; }
.score-bar-bg { height: 14px; border-radius: 4px; background: #e8e8e8; width: 100%; margin: 4px 0; }
.score-bar-fill { height: 14px; border-radius: 4px; }
.not-req { background: #fafafa; border-left: 4px solid #d0d0d0; padding: 8px 12px; margin: 10px 0; font-size: 10px; }
ul { margin: 4px 0; padding-left: 18px; }
li { margin: 2px 0; font-size: 10px; }
.meta { color: #888; font-size: 9px; margin-top: 20px; }
.rationale { font-size: 10px; color: #555; margin: 4px 0 12px 0; }
"""


def generate_pdf(data: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    html_content = _build_html(data)
    filename = f"{data['period_label'].replace(' ', '_')}_{data['target_name']}_evaluation.pdf"
    pdf_path = output_dir / filename
    HTML(string=html_content).write_pdf(str(pdf_path))
    return pdf_path


def _build_html(d: dict[str, Any]) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="ja">
<head><meta charset="utf-8"><style>{CSS}</style></head>
<body>
{_section_header(d)}
{_section_grade(d)}
{_section_scores(d)}
{_section_values(d)}
{_section_not_requirements(d)}
{_section_actions(d)}
<p class="meta">生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | VALANCE 評価自動化システム</p>
</body></html>"""


def _section_header(d: dict[str, Any]) -> str:
    qual = d.get("qualitative", {})
    strengths = qual.get("strengths", [])
    improvements = qual.get("improvements", [])
    summary_points = []
    if strengths:
        summary_points.append(f"<strong>強み:</strong> {strengths[0]}")
    if improvements:
        summary_points.append(f"<strong>課題:</strong> {improvements[0]}")
    summary_html = "<br>".join(summary_points) if summary_points else ""

    return f"""\
<div class="header">
    <h1>月次評価レポート</h1>
    <p style="font-size:16px; color:#222;"><strong>{_esc(d['target_name'])}</strong> ({_esc(d.get('target_grade', ''))})</p>
    <p>評価期間: {_esc(d['period_label'])}</p>
    <div class="score-box">{d['overall_score']:.1f}<span style="font-size:16px;"> / 100</span></div>
</div>
<div style="text-align:center; margin-bottom:16px;">
    <p style="font-size:11px; color:#4a5568;">{summary_html}</p>
</div>"""


def _section_grade(d: dict[str, Any]) -> str:
    grade_raw = d.get("grade_definition", "")
    grade_num = str(d.get("target_grade", ""))
    lines = grade_raw.splitlines()

    # 対象グレードの行を「グレード番号\t」で開始する行から、
    # 次のグレード番号 (数字\t) が出るまで、または --- まで抽出
    grade_lines = []
    capturing = False
    for line in lines:
        # 対象グレードの開始行
        if not capturing and line.startswith(grade_num + "\t"):
            capturing = True
            grade_lines.append(line)
            continue
        if capturing:
            # 次のグレード行 (数字\tで始まる) または --- で終了
            if line.startswith("---"):
                break
            if len(line) > 0 and line[0].isdigit() and "\t" in line[:3]:
                break
            grade_lines.append(line)

    grade_text = _esc("\n".join(grade_lines) if grade_lines else grade_raw).replace("\n", "<br>")
    return f"""\
<h2>グレード定義 (Grade {_esc(grade_num)})</h2>
<div class="grade-box">{grade_text}</div>"""


def _section_scores(d: dict[str, Any]) -> str:
    qual = d.get("qualitative", {})
    breakdown = d.get("score_breakdown", {})

    categories = [
        ("a", "Tier1 KPI (売上・ARR・OTR・HC)", "30%", "a_tier1_kpi"),
        ("b", "Tier2 KPI (churn・MQL・SQL・コスト)", "25%", "b_tier2_kpi"),
        ("c", "アクションアイテム完了", "20%", "c_action_items"),
        ("d", "業務定性 (Slack・Drive・MTG)", "15%", "d_business_qualitative"),
        ("e", "AI活用・コミュニケーション", "10%", "e_ai_and_communication"),
    ]

    # スコアテーブル
    rows = ""
    for key, label, weight, _ in categories:
        score = breakdown.get(key, {}).get("score", "—")
        weighted = breakdown.get(key, {}).get("weighted", "—")
        rows += f"<tr><td><strong>{key}.</strong> {label}</td><td>{weight}</td><td>{score}</td><td>{weighted}</td></tr>"
    rows += f'<tr style="font-weight:bold; background:#f0faf7;"><td>総合</td><td>100%</td><td colspan="2">{d["overall_score"]:.1f}</td></tr>'

    table = f"""\
<h2>カテゴリ別スコア</h2>
<table>
<tr><th>カテゴリ</th><th>重み</th><th>スコア</th><th>加重</th></tr>
{rows}
</table>"""

    # 各カテゴリの根拠
    details = ""
    for key, label, weight, qual_key in categories:
        q = qual.get(qual_key, {})
        score = q.get("score", "—")
        rationale = _esc(q.get("rationale", "データなし"))
        color = "#02c491" if isinstance(score, (int, float)) and score >= 70 else "#8abfad" if isinstance(score, (int, float)) and score >= 50 else "#0f0f26"

        details += f"""\
<div style="margin-top:10px;">
    <strong>{key}. {label}</strong> — <span style="color:{color}; font-weight:bold;">{score} / 100</span>
    {_score_bar(score if isinstance(score, (int, float)) else 50)}
    <p class="rationale">{rationale}</p>
</div>"""

    return table + "\n<h2>評価根拠</h2>\n" + details


def _section_values(d: dict[str, Any]) -> str:
    qual = d.get("qualitative", {})
    vc = qual.get("value_comment", {})
    if not vc:
        return ""
    return f"""\
<h2>Values 観点</h2>
<table>
<tr><th style="width:20%;">Value</th><th>コメント</th></tr>
<tr><td><strong>Fairness</strong></td><td>{_esc(vc.get('fairness', '—'))}</td></tr>
<tr><td><strong>Independence</strong></td><td>{_esc(vc.get('independence', '—'))}</td></tr>
<tr><td><strong>Resilience</strong></td><td>{_esc(vc.get('resilience', '—'))}</td></tr>
</table>"""


def _section_not_requirements(d: dict[str, Any]) -> str:
    calendar = d.get("calendar_data", {})
    return f"""\
<div class="not-req">
    <strong>NOT 要件 (評価対象外):</strong>
    長時間労働・残業時間、MTG 参加数 ({calendar.get('total_events', '—')} 件) はスコアに含めていません。
</div>"""


def _section_actions(d: dict[str, Any]) -> str:
    qual = d.get("qualitative", {})
    strengths = qual.get("strengths", [])
    improvements = qual.get("improvements", [])
    actions = qual.get("recommended_actions_next_month", [])

    s_html = "".join(f"<li>{_esc(s)}</li>" for s in strengths)
    i_html = "".join(f"<li>{_esc(i)}</li>" for i in improvements)
    a_html = "".join(f"<li>{_esc(a)}</li>" for a in actions)

    return f"""\
<h2>総合所見</h2>
<table style="border:none;">
<tr><td style="border:none; vertical-align:top; width:50%;"><strong>強み</strong><ul>{s_html or '<li>—</li>'}</ul></td>
<td style="border:none; vertical-align:top;"><strong>改善点</strong><ul>{i_html or '<li>—</li>'}</ul></td></tr>
</table>

<h2>来月の推奨アクション</h2>
<ul>{a_html or '<li>—</li>'}</ul>"""


def _score_bar(score: float | int) -> str:
    s = max(0, min(100, float(score)))
    # VALANCE GREEN (#02c491) for high, muted for mid, VALANCE BLACK tint for low
    color = "#02c491" if s >= 70 else "#8abfad" if s >= 50 else "#0f0f26"
    return (
        f'<div class="score-bar-bg">'
        f'<div class="score-bar-fill" style="width:{s}%; background:{color};"></div>'
        f"</div>"
    )


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
