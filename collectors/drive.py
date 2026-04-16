"""Google Drive API で対象ユーザのドキュメント作成数を集計する。

認証: サービスアカウント。
- DRIVE_FOLDER_ID が指定されていれば、そのフォルダ内を検索
- 指定がなければ SA がアクセス可能な全ファイルから検索

注意: SA にフォルダ / ファイルの閲覧権限が付与されていないとヒットしない。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive.metadata.readonly"]


def _service(sa_file: Path):
    creds = service_account.Credentials.from_service_account_file(
        str(sa_file), scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def count_documents_created(
    sa_file: Path,
    owner_email: str,
    period_start: date,
    period_end: date,
    folder_id: str = "",
) -> dict[str, Any]:
    """対象ユーザが期間内に作成したドキュメント数を返す。

    Returns:
        {
            "total": int,
            "by_type": {mime_type_label: count},
            "files": [{"name": ..., "mimeType": ..., "createdTime": ...}, ...]
        }
    """
    svc = _service(sa_file)

    # Drive API の query 構築
    q_parts = [
        f"'{owner_email}' in owners",
        f"createdTime >= '{period_start.isoformat()}T00:00:00'",
        f"createdTime <= '{period_end.isoformat()}T23:59:59'",
        "trashed = false",
    ]
    if folder_id:
        q_parts.append(f"'{folder_id}' in parents")

    query = " and ".join(q_parts)

    files: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        resp = (
            svc.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, createdTime)",
                pageSize=1000,
                pageToken=page_token or "",
                orderBy="createdTime desc",
            )
            .execute()
        )
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    # MIME タイプ別集計
    type_labels = {
        "application/vnd.google-apps.document": "Google Docs",
        "application/vnd.google-apps.spreadsheet": "Google Sheets",
        "application/vnd.google-apps.presentation": "Google Slides",
        "application/vnd.google-apps.form": "Google Forms",
        "application/pdf": "PDF",
    }
    by_type: dict[str, int] = {}
    for f in files:
        mime = f.get("mimeType", "")
        label = type_labels.get(mime, "その他")
        by_type[label] = by_type.get(label, 0) + 1

    return {
        "total": len(files),
        "by_type": by_type,
        "files": [
            {
                "name": f.get("name"),
                "mimeType": f.get("mimeType"),
                "createdTime": f.get("createdTime"),
            }
            for f in files[:50]  # レポート用に最大 50 件
        ],
    }
