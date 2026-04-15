"""Google Sheets からグレード定義 / KPI / アクションアイテムを取得する。

シートの構造は組織ごとに異なるため、汎用的に「セル範囲」「列マッピング」を
受け取れる作りにしている。実運用ではユーザーがシート構造を確認のうえ、
列名 → モデルのマッピングを調整する想定。
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.collectors.google_auth import sheets_service
from app.models import ActionItem, Employee, KpiResult, ManagerNote


# ============================================================
# 汎用ローダ
# ============================================================


def fetch_range(
    service_account_file: Path,
    delegated_user: str,
    spreadsheet_id: str,
    range_a1: str,
) -> list[list[Any]]:
    """指定範囲を 2 次元配列で取得。空の場合は []。"""
    service = sheets_service(service_account_file, delegated_user)
    response = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_a1)
        .execute()
    )
    return response.get("values", [])


def rows_as_dicts(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """1 行目をヘッダとして dict のリストに変換。"""
    if not rows:
        return []
    header = [str(h).strip() for h in rows[0]]
    out: list[dict[str, Any]] = []
    for row in rows[1:]:
        # 列数の不足を補う
        padded = list(row) + [""] * (len(header) - len(row))
        out.append(dict(zip(header, padded, strict=False)))
    return out


# ============================================================
# グレード定義
# ============================================================


def fetch_grade_definition(
    service_account_file: Path,
    delegated_user: str,
    spreadsheet_id: str,
    sheet_name: str = "grades",
) -> str:
    """グレード定義シートを 1 つの長い文字列として取得。

    LLM への入力にそのまま渡すので、シート全体をテキストとして連結する。
    """
    rows = fetch_range(
        service_account_file,
        delegated_user,
        spreadsheet_id,
        f"{sheet_name}!A1:Z1000",
    )
    if not rows:
        return ""
    # タブ区切り CSV 風に整形
    lines = ["\t".join(str(c) for c in row) for row in rows]
    return "\n".join(lines)


def extract_grade_section(full_text: str, grade: str) -> str:
    """グレード定義テキストから、特定グレード行のセクションを抽出。

    シンプルに `grade` 文字列を含む行とその前後を返す簡易実装。
    実際のシート構造に合わせて精度を上げる余地あり。
    """
    if not full_text:
        return ""
    lines = full_text.splitlines()
    matched: list[str] = []
    for i, line in enumerate(lines):
        if grade in line:
            start = max(0, i - 1)
            end = min(len(lines), i + 6)
            matched.extend(lines[start:end])
            matched.append("---")
    return "\n".join(matched) if matched else full_text  # 見つからなければ全体を返す


# ============================================================
# 従業員マスタ
# ============================================================


def fetch_employees(
    service_account_file: Path,
    delegated_user: str,
    spreadsheet_id: str,
    sheet_name: str = "employees",
) -> list[Employee]:
    """従業員マスタ。期待ヘッダ: email, name, grade, department, manager_email"""
    rows = fetch_range(
        service_account_file,
        delegated_user,
        spreadsheet_id,
        f"{sheet_name}!A1:Z10000",
    )
    out: list[Employee] = []
    for row in rows_as_dicts(rows):
        email = (row.get("email") or "").strip()
        if not email:
            continue
        out.append(
            Employee(
                email=email,
                name=(row.get("name") or "").strip(),
                grade=(row.get("grade") or "").strip(),
                department=(row.get("department") or "").strip() or None,
                manager_email=(row.get("manager_email") or "").strip() or None,
            )
        )
    return out


# ============================================================
# KPI シート
# ============================================================


def fetch_kpis(
    service_account_file: Path,
    delegated_user: str,
    spreadsheet_id: str,
    target_email: str,
    sheet_name: str = "kpis",
) -> list[KpiResult]:
    """KPI シート。期待ヘッダ: name, tier, target, actual, owner_email, notes"""
    rows = fetch_range(
        service_account_file,
        delegated_user,
        spreadsheet_id,
        f"{sheet_name}!A1:Z10000",
    )
    out: list[KpiResult] = []
    for row in rows_as_dicts(rows):
        owner = (row.get("owner_email") or "").strip()
        if owner and owner.lower() != target_email.lower():
            continue
        target = _to_float(row.get("target"))
        actual = _to_float(row.get("actual"))
        achievement = (
            actual / target if target and actual is not None and target != 0 else None
        )
        out.append(
            KpiResult(
                name=(row.get("name") or "").strip(),
                tier=int(row.get("tier") or 1),
                target=target,
                actual=actual,
                achievement_rate=achievement,
                owner_email=owner or None,
                notes=(row.get("notes") or "").strip() or None,
            )
        )
    return out


# ============================================================
# アクションアイテム
# ============================================================


def fetch_action_items(
    service_account_file: Path,
    delegated_user: str,
    spreadsheet_id: str,
    target_email: str,
    sheet_name: str = "action_items",
) -> list[ActionItem]:
    """期待ヘッダ: title, owner_email, status, due_date, completed_date, importance, description"""
    rows = fetch_range(
        service_account_file,
        delegated_user,
        spreadsheet_id,
        f"{sheet_name}!A1:Z10000",
    )
    out: list[ActionItem] = []
    for row in rows_as_dicts(rows):
        owner = (row.get("owner_email") or "").strip()
        if owner.lower() != target_email.lower():
            continue
        out.append(
            ActionItem(
                title=(row.get("title") or "").strip(),
                owner_email=owner,
                status=(row.get("status") or "not_started").strip(),
                due_date=_to_date(row.get("due_date")),
                completed_date=_to_date(row.get("completed_date")),
                importance=(row.get("importance") or "").strip() or None,
                description=(row.get("description") or "").strip() or None,
            )
        )
    return out


# ============================================================
# 上司コメント
# ============================================================


def fetch_manager_notes(
    service_account_file: Path,
    delegated_user: str,
    spreadsheet_id: str,
    target_email: str,
    sheet_name: str = "manager_notes",
) -> list[ManagerNote]:
    """期待ヘッダ: employee_email, manager_email, text, created_at"""
    rows = fetch_range(
        service_account_file,
        delegated_user,
        spreadsheet_id,
        f"{sheet_name}!A1:Z10000",
    )
    out: list[ManagerNote] = []
    for row in rows_as_dicts(rows):
        emp = (row.get("employee_email") or "").strip()
        if emp.lower() != target_email.lower():
            continue
        out.append(
            ManagerNote(
                employee_email=emp,
                manager_email=(row.get("manager_email") or "").strip(),
                text=(row.get("text") or "").strip(),
                created_at=_to_datetime(row.get("created_at")),
            )
        )
    return out


# ============================================================
# 変換ヘルパ
# ============================================================


def _to_float(v: Any) -> float | None:
    if v in (None, "", "—"):
        return None
    try:
        # "1,234,567" 等のカンマも除去
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _to_date(v: Any) -> date | None:
    if not v:
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _to_datetime(v: Any) -> datetime | None:
    if not v:
        return None
    s = str(v).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None
