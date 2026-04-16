"""Google Drive API で対象ユーザのドキュメント作成数を集計する。

共有ドライブ (Shared Drive) にも対応。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from collectors.auth import build_service

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _service(sa_file: Path):
    return build_service("drive", "v3", sa_file, SCOPES)


def count_documents_created(
    sa_file: Path,
    owner_email: str,
    period_start: date,
    period_end: date,
    folder_id: str = "",
) -> dict[str, Any]:
    svc = _service(sa_file)

    q_parts = [
        f"createdTime >= '{period_start.isoformat()}T00:00:00'",
        f"createdTime <= '{period_end.isoformat()}T23:59:59'",
        "trashed = false",
    ]

    # 共有ドライブでは owners フィルタが使えないので、
    # lastModifyingUser で後からフィルタする
    query = " and ".join(q_parts)

    files: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        resp = (
            svc.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, createdTime, owners, lastModifyingUser)",
                pageSize=1000,
                pageToken=page_token or "",
                orderBy="createdTime desc",
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                corpora="allDrives",
            )
            .execute()
        )
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    # 対象ユーザでフィルタ (owners or lastModifyingUser)
    owner_lower = owner_email.lower()
    filtered = []
    for f in files:
        owners = [o.get("emailAddress", "").lower() for o in f.get("owners", [])]
        last_mod = (f.get("lastModifyingUser") or {}).get("emailAddress", "").lower()
        if owner_lower in owners or owner_lower == last_mod:
            filtered.append(f)

    # MIME タイプ別集計
    type_labels = {
        "application/vnd.google-apps.document": "Google Docs",
        "application/vnd.google-apps.spreadsheet": "Google Sheets",
        "application/vnd.google-apps.presentation": "Google Slides",
        "application/vnd.google-apps.form": "Google Forms",
        "application/pdf": "PDF",
    }
    by_type: dict[str, int] = {}
    for f in filtered:
        mime = f.get("mimeType", "")
        label = type_labels.get(mime, "その他")
        by_type[label] = by_type.get(label, 0) + 1

    return {
        "total": len(filtered),
        "by_type": by_type,
        "files": [
            {
                "name": f.get("name"),
                "mimeType": f.get("mimeType"),
                "createdTime": f.get("createdTime"),
            }
            for f in filtered[:50]
        ],
    }
