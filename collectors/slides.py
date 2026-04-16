"""Google Slides からアクションアイテム目標を取得する。

事業計画エグゼクティブサマリの特定スライドからテキストを抽出。
認証: サービスアカウント。プレゼンテーションに SA メールの閲覧権限が必要。
"""

from __future__ import annotations

from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/presentations.readonly"]


def _service(sa_file: Path):
    creds = service_account.Credentials.from_service_account_file(
        str(sa_file), scopes=SCOPES
    )
    return build("slides", "v1", credentials=creds, cache_discovery=False)


def fetch_slide_text(
    sa_file: Path,
    presentation_id: str,
    target_slide_id: str,
) -> str:
    """指定スライドページ内の全テキストを結合して返す。"""
    svc = _service(sa_file)
    presentation = svc.presentations().get(presentationId=presentation_id).execute()

    for slide in presentation.get("slides", []):
        if slide.get("objectId") == target_slide_id:
            return _extract_text_from_slide(slide)

    # slide_id が見つからなかった場合、全スライドのテキストを返す
    all_text: list[str] = []
    for slide in presentation.get("slides", []):
        text = _extract_text_from_slide(slide)
        if text.strip():
            slide_id = slide.get("objectId", "?")
            all_text.append(f"[Slide {slide_id}]\n{text}")
    return "\n\n".join(all_text)


def _extract_text_from_slide(slide: dict) -> str:
    """1 スライド内の全 PageElement からテキストを抽出。"""
    texts: list[str] = []
    for element in slide.get("pageElements", []):
        shape = element.get("shape")
        if not shape:
            # テーブル等も対応
            table = element.get("table")
            if table:
                texts.append(_extract_text_from_table(table))
            continue
        text_content = shape.get("text")
        if not text_content:
            continue
        for text_element in text_content.get("textElements", []):
            text_run = text_element.get("textRun")
            if text_run:
                texts.append(text_run.get("content", ""))
    return "".join(texts)


def _extract_text_from_table(table: dict) -> str:
    """テーブル要素からテキストを抽出。"""
    rows: list[str] = []
    for table_row in table.get("tableRows", []):
        cells: list[str] = []
        for cell in table_row.get("tableCells", []):
            cell_text_parts: list[str] = []
            text_content = cell.get("text")
            if text_content:
                for te in text_content.get("textElements", []):
                    tr = te.get("textRun")
                    if tr:
                        cell_text_parts.append(tr.get("content", "").strip())
            cells.append(" ".join(cell_text_parts))
        rows.append("\t".join(cells))
    return "\n".join(rows)
