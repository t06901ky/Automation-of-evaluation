"""Google API 共通認証ヘルパ。

この環境では SSL 証明書の問題を回避するために
httplib2 に明示的に CA バンドルを渡す。
"""

from __future__ import annotations

from pathlib import Path

import httplib2
from google.oauth2 import service_account
from googleapiclient.discovery import build

CA_CERTS = "/etc/ssl/certs/ca-certificates.crt"


def build_service(api_name: str, api_version: str, sa_file: Path, scopes: list[str]):
    """認証済みの Google API service を返す。"""
    creds = service_account.Credentials.from_service_account_file(
        str(sa_file), scopes=scopes
    )
    http = httplib2.Http(ca_certs=CA_CERTS)
    http = google_auth_httplib2_authorize(creds, http)
    return build(api_name, api_version, http=http, cache_discovery=False)


def google_auth_httplib2_authorize(credentials, http):
    """google-auth の credentials で httplib2.Http を認証する。"""
    from google_auth_httplib2 import AuthorizedHttp
    return AuthorizedHttp(credentials, http=http)
