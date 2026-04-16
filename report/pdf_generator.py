"""PDF レポート生成 — WeasyPrint で HTML → PDF 変換。

セクション構成:
  1. 表紙（評価対象者・評価期間・総合スコア）
  2. グレード定義の確認
  3. 定量 KPI 達成状況（Tier1・Tier2）
  4. アクションアイテム進捗
  5. 定性評価サマリ（Slack/Drive/AI 活用）
  6. NOT 要件の確認（適切に除外されたことの明示）
  7. 総合評価・AI コメント
  8. 来月の推奨アクション
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
    line-height: 1.6;
    color: #222;
}
h1 { font-size: 22px; color: #1a365d; border-bottom: 3px solid #1a365d; padding-bottom: 8px; }
h2 { font-size: 16px; color: #2c5282; margin-top: 24px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }
h3 { font-size: 13px; color: #2d3748; margin-top: 16px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th, td { border: 1px solid #cbd5e0; padding: 6px 10px; text-align: left; font-size: 10px; }
th { background: #edf2f7; font-weight: bold; }
.score-box {
    display: inline-block; background: #1a365d; color: #fff;
    font-size: 28px; font-weight: bold; padding: 12px 24px; border-radius: 8px;
    margin: 8px 0;
}
.score-bar {
    height: 18px; border-radius: 4px; margin: 4px 0;
}
.score-bar-bg { background: #e2e8f0; width: 100%; }
.score-bar-fill { background: #3182ce; }
.not-requirement { background: #fff5f5; border-left: 4px solid #fc8181; padding: 12px; margin: 12px 0; }
.cover-page { text-align: center; padding-top: 120px; }
.section { page-break-inside: avoid; }
ul { margin: 4px 0; padding-left: 20px; }
li { margin: 2px 0; }
.meta { color: #718096; font-size: 10px; }
"""


def generate_pdf(data: dict[str, Any], output_dir: Path) -> Path:
    """評価データから PDF を生成して保存パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    html_content = _build_html(data)
    filename = (
        f"{data['period_label'].replace(' ', '_')}_{data['target_name']}_evaluation.pdf"
    )
    pdf_path = output_dir / filename

    HTML(string=html_content).write_pdf(str(pdf_path))
    return pdf_path


def _build_html(d: dict[str, Any]) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="ja">
<head><meta charset="utf-8"><style>{CSS}</style></head>
<body>

{_section_cover(d)}
{_section_grade(d)}
{_section_kpi(d)}
{_section_action_items(d)}
{_section_qualitative(d)}
{_section_not_requirements(d)}
{_section_overall(d)}
{_section_next_actions(d)}

<p class="meta">生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</body></html>"""


def _section_cover(d: dict[str, Any]) -> str:
    return f"""\
<div class="cover-page">
    <h1>月次評価レポート</h1>
    <p style="font-size:18px; margin-top:24px;">{_esc(d['target_name'])} ({_esc(d.get('target_grade', ''))})</p>
    <p style="font-size:14px; color:#718096;">評価期間: {_esc(d['period_label'])}</p>
    <div class="score-box">{d['overall_score']:.1f} / 100</div>
    <p style="font-size:12px; color:#718096; margin-top:4px;">総合スコア</p>
</div>
<div style="page-break-after: always;"></div>"""


def _section_grade(d: dict[str, Any]) -> str:
    grade_text = _esc(d.get("grade_definition", "未取得")).replace("\n", "<br>")
    return f"""\
<div class="section">
    <h2>1. グレード定義の確認</h2>
    <p><strong>グレード:</strong> {_esc(d.get('target_grade', ''))}</p>
    <div style="background:#f7fafc; padding:12px; border-radius:4px; font-size:10px;">
        {grade_text}
    </div>
</div>"""


def _section_kpi(d: dict[str, Any]) -> str:
    kpi = d.get("kpi_scores", {})
    rows_html = ""
    for tier_key, tier_label in [("tier1", "Tier1"), ("tier2", "Tier2")]:
        tier = kpi.get(tier_key, {})
        for detail in tier.get("details", []):
            rate_pct = f"{detail.get('achievement_rate', 0) * 100:.1f}%"
            rows_html += (
                f"<tr><td>{tier_label}</td><td>{_esc(str(detail.get('name', '')))}</td>"
                f"<td style='text-align:right'>{detail.get('plan', '—')}</td>"
                f"<td style='text-align:right'>{detail.get('actual', '—')}</td>"
                f"<td style='text-align:right'>{rate_pct}</td>"
                f"<td style='text-align:right'>{detail.get('score', '—')}</td></tr>"
            )
    t1_score = kpi.get("tier1", {}).get("score", "—")
    t2_score = kpi.get("tier2", {}).get("score", "—")
    return f"""\
<div class="section">
    <h2>2. 定量 KPI 達成状況</h2>
    <p><strong>a. Tier1 KPI スコア:</strong> {t1_score} / 100 (重み 30%)</p>
    {_score_bar(t1_score if isinstance(t1_score, (int, float)) else 50)}
    <p><strong>b. Tier2 KPI スコア:</strong> {t2_score} / 100 (重み 25%)</p>
    {_score_bar(t2_score if isinstance(t2_score, (int, float)) else 50)}
    <table>
        <tr><th>Tier</th><th>指標</th><th>計画</th><th>実績</th><th>達成率</th><th>スコア</th></tr>
        {rows_html if rows_html else '<tr><td colspan="6">KPI データ未入力 or 実績未取得</td></tr>'}
    </table>
</div>"""


def _section_action_items(d: dict[str, Any]) -> str:
    qual = d.get("qualitative", {})
    c = qual.get("c_action_items", {})
    score = c.get("score", "—")
    rationale = _esc(c.get("rationale", "")).replace("\n", "<br>")
    action_text = _esc(d.get("action_items_text", "未取得")).replace("\n", "<br>")
    return f"""\
<div class="section">
    <h2>3. アクションアイテム進捗</h2>
    <p><strong>c. スコア:</strong> {score} / 100 (重み 20%)</p>
    {_score_bar(score if isinstance(score, (int, float)) else 50)}
    <h3>目標 (事業計画より)</h3>
    <div style="background:#f7fafc; padding:8px; font-size:10px;">{action_text}</div>
    <h3>評価根拠</h3>
    <p>{rationale}</p>
</div>"""


def _section_qualitative(d: dict[str, Any]) -> str:
    qual = d.get("qualitative", {})
    d_data = qual.get("d_business_qualitative", {})
    e_data = qual.get("e_ai_and_communication", {})
    slack = d.get("slack_data", {})
    drive = d.get("drive_data", {})
    return f"""\
<div class="section">
    <h2>4. 定性評価サマリ</h2>
    <h3>d. 業務定性 (Slack 貢献・Drive 成果物・MTG の質) — {d_data.get('score', '—')} / 100 (重み 15%)</h3>
    {_score_bar(d_data.get('score', 50) if isinstance(d_data.get('score'), (int, float)) else 50)}
    <p>{_esc(d_data.get('rationale', '')).replace(chr(10), '<br>')}</p>
    <ul>
        <li>Slack メッセージ数: {slack.get('total_messages', 0)}</li>
        <li>アクティブチャンネル: {slack.get('channel_count', 0)}</li>
        <li>Drive ドキュメント作成数: {drive.get('total', 0)}</li>
    </ul>

    <h3>e. AI ツール活用・コミュニケーション — {e_data.get('score', '—')} / 100 (重み 10%)</h3>
    {_score_bar(e_data.get('score', 50) if isinstance(e_data.get('score'), (int, float)) else 50)}
    <p>{_esc(e_data.get('rationale', '')).replace(chr(10), '<br>')}</p>
    <ul><li>AI キーワード言及数: {slack.get('ai_keyword_mentions', 0)}</li></ul>
</div>"""


def _section_not_requirements(d: dict[str, Any]) -> str:
    calendar = d.get("calendar_data", {})
    return f"""\
<div class="section">
    <h2>5. NOT 要件の確認</h2>
    <div class="not-requirement">
        <p><strong>以下の項目は評価から適切に除外されています:</strong></p>
        <ul>
            <li>長時間労働・残業時間 → 評価対象外</li>
            <li>MTG 参加数: {calendar.get('total_events', '—')} 件 → スコアに反映していません</li>
        </ul>
        <p style="font-size:10px; color:#718096;">
            ※ Slack メッセージ数はポジティブ指標として d カテゴリに含めています。
        </p>
    </div>
</div>"""


def _section_overall(d: dict[str, Any]) -> str:
    qual = d.get("qualitative", {})
    strengths = qual.get("strengths", [])
    improvements = qual.get("improvements", [])
    s_html = "".join(f"<li>{_esc(s)}</li>" for s in strengths)
    i_html = "".join(f"<li>{_esc(i)}</li>" for i in improvements)

    breakdown = d.get("score_breakdown", {})
    rows = ""
    for key, label, weight in [
        ("a", "Tier1 KPI", "30%"),
        ("b", "Tier2 KPI", "25%"),
        ("c", "アクションアイテム", "20%"),
        ("d", "業務定性", "15%"),
        ("e", "AI/コミュニケーション", "10%"),
    ]:
        score = breakdown.get(key, {}).get("score", "—")
        weighted = breakdown.get(key, {}).get("weighted", "—")
        rows += f"<tr><td>{label}</td><td>{weight}</td><td>{score}</td><td>{weighted}</td></tr>"

    return f"""\
<div class="section">
    <h2>6. 総合評価</h2>
    <table>
        <tr><th>カテゴリ</th><th>重み</th><th>スコア</th><th>加重</th></tr>
        {rows}
        <tr style="font-weight:bold; background:#edf2f7;">
            <td>総合</td><td>100%</td><td colspan="2">{d['overall_score']:.1f}</td>
        </tr>
    </table>

    <h3>強み</h3>
    <ul>{s_html if s_html else '<li>—</li>'}</ul>
    <h3>改善点</h3>
    <ul>{i_html if i_html else '<li>—</li>'}</ul>
</div>"""


def _section_next_actions(d: dict[str, Any]) -> str:
    qual = d.get("qualitative", {})
    actions = qual.get("recommended_actions_next_month", [])
    a_html = "".join(f"<li>{_esc(a)}</li>" for a in actions)
    return f"""\
<div class="section">
    <h2>7. 来月の推奨アクション</h2>
    <ul>{a_html if a_html else '<li>—</li>'}</ul>
</div>"""


def _score_bar(score: float | int) -> str:
    s = max(0, min(100, float(score)))
    color = "#38a169" if s >= 80 else "#d69e2e" if s >= 60 else "#e53e3e"
    return (
        f'<div class="score-bar score-bar-bg">'
        f'<div class="score-bar-fill" style="width:{s}%; background:{color};"></div>'
        f"</div>"
    )


def _esc(text: str) -> str:
    """HTML エスケープ。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
