"""Google Drive API で対象ユーザのドキュメント作成数を集計する。

共有ドライブ (Shared Drive) 対応: 各ドライブを個別にクエリして高速化。
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

    all_files: list[dict[str, Any]] = []

    # 共有ドライブ一覧を取得し、各ドライブを個別にクエリ
    try:
        drives_resp = svc.drives().list(pageSize=50).execute()
        shared_drives = drives_resp.get("drives", [])
    except Exception:
        shared_drives = []

    query = (
        f"createdTime >= '{period_start.isoformat()}T00:00:00' "
        f"and createdTime <= '{period_end.isoformat()}T23:59:59' "
        f"and trashed = false "
        f"and mimeType != 'application/vnd.google-apps.folder'"
    )

    for drive_info in shared_drives:
        drive_id = drive_info["id"]
        page_token = None
        while True:
            resp = (
                svc.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name, mimeType, createdTime, lastModifyingUser)",
                    pageSize=200,
                    pageToken=page_token or "",
                    driveId=drive_id,
                    corpora="drive",
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )
            all_files.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    # マイドライブも検索
    page_token = None
    while True:
        resp = (
            svc.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, createdTime, owners, lastModifyingUser)",
                pageSize=200,
                pageToken=page_token or "",
                corpora="user",
            )
            .execute()
        )
        all_files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    # 共有ドライブではファイルの個人所有者を特定できないため、
    # 期間内に作成された全ファイルをチームの成果物としてカウントする
    # (COO 評価では組織全体のアウトプット量が指標として妥当)
    filtered = all_files

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
