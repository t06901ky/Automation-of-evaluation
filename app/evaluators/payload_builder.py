"""EvaluationContext から LLM に渡す Markdown payload を構築する。"""

from __future__ import annotations

from datetime import datetime

from app.models import EvaluationContext


def build_employee_summary(ctx: EvaluationContext) -> str:
    e = ctx.employee
    return (
        f"- 氏名: {e.name}\n"
        f"- email: {e.email}\n"
        f"- 部門: {e.department or '不明'}\n"
        f"- グレード: {e.grade}\n"
        f"- 上司: {e.manager_email or '不明'}\n"
        f"- 評価期間: {ctx.period_start} 〜 {ctx.period_end}"
    )


def build_evidence_payload(ctx: EvaluationContext) -> str:
    """全データを Markdown セクションに整形。"""
    sections: list[str] = []

    # ---- a / b: KPI ----
    sections.append(_kpi_section(ctx))

    # ---- c: アクションアイテム ----
    sections.append(_action_section(ctx))

    # ---- d / e / f: 行動データ (カレンダ + Slack) ----
    sections.append(_calendar_section(ctx))
    sections.append(_slack_section(ctx))

    # ---- g: 上司コメント ----
    sections.append(_manager_section(ctx))

    return "\n\n".join(s for s in sections if s)


def _kpi_section(ctx: EvaluationContext) -> str:
    if not ctx.kpi_results:
        return "## KPI (a / b)\nデータなし"
    lines = ["## KPI (a / b)"]
    lines.append("| name | tier | target | actual | 達成率 | notes |")
    lines.append("|---|---|---|---|---|---|")
    for k in ctx.kpi_results:
        ach = f"{k.achievement_rate:.1%}" if k.achievement_rate is not None else "—"
        lines.append(
            f"| {k.name} | {k.tier} | {k.target if k.target is not None else '—'} "
            f"| {k.actual if k.actual is not None else '—'} | {ach} | {k.notes or ''} |"
        )
    return "\n".join(lines)


def _action_section(ctx: EvaluationContext) -> str:
    if not ctx.action_items:
        return "## アクションアイテム (c)\nデータなし"
    lines = ["## アクションアイテム (c)"]
    for a in ctx.action_items:
        lines.append(
            f"- [{a.status}] {a.title} "
            f"(importance={a.importance or '—'}, "
            f"due={a.due_date or '—'}, completed={a.completed_date or '—'})"
        )
        if a.description:
            lines.append(f"    - {a.description}")
    return "\n".join(lines)


def _calendar_section(ctx: EvaluationContext) -> str:
    events = ctx.calendar_events
    if not events:
        return "## カレンダー集計 (d/e/f 用)\nデータなし"

    total = len(events)
    organizer_count = sum(
        1 for e in events if e.organizer_email == ctx.employee.email
    )
    avg_attendees = (
        sum(len(e.attendee_emails) for e in events) / total if total else 0.0
    )
    long_meetings = sum(
        1 for e in events if (e.end - e.start).total_seconds() >= 3600 * 2
    )

    lines = [
        "## カレンダー集計 (d/e/f 用)",
        f"- 期間内会議数: {total}",
        f"- 自分主催: {organizer_count}",
        f"- 平均出席者数: {avg_attendees:.1f}",
        f"- 2 時間以上の長時間会議: {long_meetings}",
        "",
        "### 主要な会議 (上位 20 件)",
    ]
    for e in events[:20]:
        lines.append(
            f"- {e.start.strftime('%Y-%m-%d %H:%M')} "
            f"({(e.end - e.start).total_seconds() / 60:.0f}min) {e.summary}"
        )
    return "\n".join(lines)


def _slack_section(ctx: EvaluationContext) -> str:
    s = ctx.slack_activity
    if s is None:
        return "## Slack 活動 (e/f 用)\nデータなし"
    lines = [
        "## Slack 活動 (e/f 用)",
        f"- メッセージ数: {s.messages_sent}",
        f"- スレッド開始: {s.threads_started} / 返信: {s.threads_replied}",
        f"- アクティブチャンネル数: {s.unique_channels_active}",
        f"- 業務時間外メッセージ: {s.after_hours_messages}",
        f"- 週末メッセージ: {s.weekend_messages}",
    ]
    if s.avg_response_minutes is not None:
        lines.append(f"- 平均応答時間 (分): {s.avg_response_minutes:.1f}")
    return "\n".join(lines)


def _manager_section(ctx: EvaluationContext) -> str:
    if not ctx.manager_notes:
        return "## 上司コメント (g)\nデータなし"
    lines = ["## 上司コメント (g)"]
    for n in ctx.manager_notes:
        when = (
            n.created_at.strftime("%Y-%m-%d") if isinstance(n.created_at, datetime) else "—"
        )
        lines.append(f"- ({when}) by {n.manager_email}: {n.text}")
    return "\n".join(lines)
