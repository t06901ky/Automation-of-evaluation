"""CLI エントリーポイント.

使い方:
  # 1 名のみ評価
  python -m app.cli evaluate --email alice@example.com

  # 従業員シートの全員を評価
  python -m app.cli evaluate-all --employees-sheet-id <SHEET_ID>
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from app.collectors import calendar_collector, sheets_collector, slack_collector
from app.config import get_settings
from app.evaluators.engine import run_evaluation
from app.evaluators.report_writer import write_report
from app.llm.claude_client import ClaudeEvaluator
from app.models import Employee, EvaluationContext

app = typer.Typer(help="HR 評価自動化 CLI")
console = Console()


def _build_context(employee: Employee, period_days: int) -> EvaluationContext:
    """1 名分のデータを各 collector から集めて EvaluationContext を返す."""
    settings = get_settings()
    period_end_d = date.today()
    period_start_d = period_end_d - timedelta(days=period_days)
    period_start_dt = datetime.combine(period_start_d, datetime.min.time(), tzinfo=timezone.utc)
    period_end_dt = datetime.combine(period_end_d, datetime.max.time(), tzinfo=timezone.utc)

    console.log(f"[blue]Calendar[/]: {employee.email} の予定を取得中…")
    events = calendar_collector.fetch_events(
        settings.google_service_account_file,
        settings.google_delegated_user,
        employee.email,
        period_start_dt,
        period_end_dt,
    )
    console.log(f"  → {len(events)} 件取得")

    console.log(f"[blue]Slack[/]: {employee.email} の活動を取得中…")
    slack_activity = slack_collector.fetch_slack_activity(
        settings.slack_bot_token,
        settings.slack_user_token,
        employee.email,
        period_start_d,
        period_end_d,
    )

    console.log("[blue]Sheets[/]: グレード定義を取得中…")
    grade_full = sheets_collector.fetch_grade_definition(
        settings.google_service_account_file,
        settings.google_delegated_user,
        settings.grade_definition_sheet_id,
    )
    grade_section = sheets_collector.extract_grade_section(grade_full, employee.grade)

    kpi_results = []
    if settings.kpi_sheet_id:
        console.log("[blue]Sheets[/]: KPI を取得中…")
        kpi_results = sheets_collector.fetch_kpis(
            settings.google_service_account_file,
            settings.google_delegated_user,
            settings.kpi_sheet_id,
            employee.email,
        )

    action_items = []
    manager_notes = []
    if settings.action_items_sheet_id:
        console.log("[blue]Sheets[/]: アクションアイテム / 上司コメントを取得中…")
        action_items = sheets_collector.fetch_action_items(
            settings.google_service_account_file,
            settings.google_delegated_user,
            settings.action_items_sheet_id,
            employee.email,
        )
        manager_notes = sheets_collector.fetch_manager_notes(
            settings.google_service_account_file,
            settings.google_delegated_user,
            settings.action_items_sheet_id,
            employee.email,
        )

    return EvaluationContext(
        employee=employee,
        period_start=period_start_d,
        period_end=period_end_d,
        grade_definition_text=grade_section,
        calendar_events=events,
        slack_activity=slack_activity,
        kpi_results=kpi_results,
        action_items=action_items,
        manager_notes=manager_notes,
    )


@app.command()
def evaluate(
    email: str = typer.Option(..., help="評価対象者の Email"),
    name: str = typer.Option("", help="氏名 (省略時は email から推定)"),
    grade: str = typer.Option(..., help="グレード (例: G3)"),
    department: str = typer.Option("", help="部門"),
    manager_email: str = typer.Option("", help="上司の Email"),
    period_days: int = typer.Option(0, help="評価期間 (日数). 0 で .env の既定値を使用"),
) -> None:
    """1 名分の評価を実行."""
    settings = get_settings()
    days = period_days or settings.evaluation_window_days

    employee = Employee(
        email=email,
        name=name or email.split("@")[0],
        grade=grade,
        department=department or None,
        manager_email=manager_email or None,
    )

    ctx = _build_context(employee, days)

    console.log("[green]Claude による評価実行中…[/]")
    evaluator = ClaudeEvaluator(settings.anthropic_api_key, model=settings.claude_model)
    report = run_evaluation(ctx, evaluator)

    md_path, json_path = write_report(report, settings.report_output_dir)

    _print_summary(report)
    console.print(f"\n[green]Markdown:[/] {md_path}")
    console.print(f"[green]JSON:    [/] {json_path}")


@app.command("evaluate-all")
def evaluate_all(
    employees_sheet_id: str = typer.Option(
        ..., help="従業員マスタシートの ID (列: email/name/grade/department/manager_email)"
    ),
    period_days: int = typer.Option(0, help="評価期間 (日数)"),
) -> None:
    """従業員マスタの全員を順に評価."""
    settings = get_settings()
    days = period_days or settings.evaluation_window_days

    employees = sheets_collector.fetch_employees(
        settings.google_service_account_file,
        settings.google_delegated_user,
        employees_sheet_id,
    )
    console.log(f"対象者 {len(employees)} 名を評価します")

    evaluator = ClaudeEvaluator(settings.anthropic_api_key, model=settings.claude_model)

    for i, emp in enumerate(employees, 1):
        console.rule(f"[{i}/{len(employees)}] {emp.name} ({emp.email})")
        try:
            ctx = _build_context(emp, days)
            report = run_evaluation(ctx, evaluator)
            md_path, _ = write_report(report, settings.report_output_dir)
            console.print(f"  → {md_path} ({report.overall_score:.2f} / 5.00)")
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [red]ERROR:[/] {exc}")


def _print_summary(report) -> None:
    table = Table(title=f"評価サマリ: {report.employee.name}")
    table.add_column("カテゴリ")
    table.add_column("スコア", justify="right")
    table.add_column("重み", justify="right")
    table.add_column("加重", justify="right")
    table.add_column("フラグ")
    for cs in report.category_scores:
        table.add_row(
            cs.category.value,
            f"{cs.score:.2f}",
            f"{cs.weight:.2f}",
            f"{cs.weighted_score:.2f}",
            ", ".join(cs.flags) if cs.flags else "—",
        )
    table.add_row(
        "[bold]TOTAL[/]",
        f"[bold]{report.overall_score:.2f}[/]",
        "",
        "",
        f"[bold]{report.overall_rating}[/]",
    )
    console.print(table)


if __name__ == "__main__":
    app()
