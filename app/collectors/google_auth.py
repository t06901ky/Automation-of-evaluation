"""Google API 認証ヘルパ。

サービスアカウント + Domain-Wide Delegation を前提とする。
評価業務では他ユーザのカレンダー・メールにアクセスする必要があるため、
管理者から委任を受ける必要がある。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import Resource, build

# 必要となる OAuth スコープ
SCOPES: list[str] = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/admin.directory.user.readonly",
]


def _credentials(
    service_account_file: Path, delegated_user: str
) -> service_account.Credentials:
    """委任済み Credentials を返す。"""
    credentials = service_account.Credentials.from_service_account_file(
        str(service_account_file), scopes=SCOPES
    )
    return credentials.with_subject(delegated_user)


@lru_cache(maxsize=8)
def _build_service(
    api_name: str,
    api_version: str,
    service_account_file_str: str,
    delegated_user: str,
) -> Resource:
    """指定 API の Service オブジェクトをキャッシュ付きで返す。"""
    creds = _credentials(Path(service_account_file_str), delegated_user)
    return build(api_name, api_version, credentials=creds, cache_discovery=False)


def calendar_service(service_account_file: Path, delegated_user: str) -> Resource:
    return _build_service(
        "calendar", "v3", str(service_account_file), delegated_user
    )


def sheets_service(service_account_file: Path, delegated_user: str) -> Resource:
    return _build_service(
        "sheets", "v4", str(service_account_file), delegated_user
    )


def drive_service(service_account_file: Path, delegated_user: str) -> Resource:
    return _build_service(
        "drive", "v3", str(service_account_file), delegated_user
    )
