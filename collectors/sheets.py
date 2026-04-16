"""Google Sheets からグレード定義と KPI データを取得する。

認証: サービスアカウント。対象シートに SA メールの閲覧権限が必要。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from collectors.auth import build_service

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _service(sa_file: Path):
    return build_service("sheets", "v4", sa_file, SCOPES)


def _fetch_range(sa_file: Path, spreadsheet_id: str, range_a1: str) -> list[list[Any]]:
    svc = _service(sa_file)
    resp = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_a1)
        .execute()
    )
    return resp.get("values", [])


# ============================================================
# グレード定義
# ============================================================


def fetch_grade_definition(
    sa_file: Path,
    spreadsheet_id: str,
    sheet_name: str = "グレード定義",
) -> str:
    """グレード定義シート全体をテキストとして返す。

    LLM に渡すので TSV 風に整形。
    """
    rows = _fetch_range(sa_file, spreadsheet_id, f"'{sheet_name}'!A1:Z500")
    if not rows:
        # シート名が不明な場合はデフォルト (Sheet1) でリトライ
        rows = _fetch_range(sa_file, spreadsheet_id, "A1:Z500")
    lines = ["\t".join(str(c) for c in row) for row in rows]
    return "\n".join(lines)


def extract_grade_section(full_text: str, grade: str) -> str:
    """特定グレード (例: '役員') に関連する行を抽出。

    見つからなければ全体を返す (LLM が自分で探す)。
    """
    if not full_text:
        return ""
    lines = full_text.splitlines()
    matched: list[str] = []
    for i, line in enumerate(lines):
        if grade in line:
            start = max(0, i - 2)
            end = min(len(lines), i + 8)
            matched.extend(lines[start:end])
            matched.append("---")
    return "\n".join(matched) if matched else full_text


# ============================================================
# KPI
# ============================================================


def fetch_kpi_data(
    sa_file: Path,
    spreadsheet_id: str,
    sheet_name: str = "KPI",
) -> list[dict[str, Any]]:
    """KPI シートを dict のリストで返す。

    期待ヘッダ (柔軟に対応):
      指標名 | tier | 計画 | 実績 | ...

    構造がわからない場合は全行を返し、LLM に読ませる。
    """
    rows = _fetch_range(sa_file, spreadsheet_id, f"'{sheet_name}'!A1:Z500")
    if not rows:
        rows = _fetch_range(sa_file, spreadsheet_id, "A1:Z500")
    return _rows_to_dicts(rows)


def fetch_kpi_raw_text(
    sa_file: Path,
    spreadsheet_id: str,
    sheet_name: str = "KPI",
) -> str:
    """KPI シートをテキストとして返す (LLM に直接渡す用)。"""
    rows = _fetch_range(sa_file, spreadsheet_id, f"'{sheet_name}'!A1:Z500")
    if not rows:
        rows = _fetch_range(sa_file, spreadsheet_id, "A1:Z500")
    lines = ["\t".join(str(c) for c in row) for row in rows]
    return "\n".join(lines)


# ============================================================
# ユーティリティ
# ============================================================


def _rows_to_dicts(rows: list[list[Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    header = [str(h).strip() for h in rows[0]]
    out: list[dict[str, Any]] = []
    for row in rows[1:]:
        padded = list(row) + [""] * (len(header) - len(row))
        out.append(dict(zip(header, padded, strict=False)))
    return out
