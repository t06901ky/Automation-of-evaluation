"""Google API 共通認証ヘルパ。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httplib2
from google.oauth2 import service_account
from googleapiclient.discovery import build


def _find_ca_certs() -> str | None:
    """OS に応じた CA バンドルパスを返す。見つからなければ None。"""
    candidates = [
        os.environ.get("SSL_CERT_FILE", ""),
        os.environ.get("REQUESTS_CA_BUNDLE", ""),
        "/etc/ssl/certs/ca-certificates.crt",  # Linux (Debian/Ubuntu)
        "/etc/ssl/cert.pem",                    # macOS
        "/etc/pki/tls/certs/ca-bundle.crt",     # RHEL/CentOS
    ]
    # certifi があればそれも候補に
    try:
        import certifi
        candidates.append(certifi.where())
    except ImportError:
        pass
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def build_service(api_name: str, api_version: str, sa_file: Path, scopes: list[str]):
    """認証済みの Google API service を返す。"""
    creds = service_account.Credentials.from_service_account_file(
        str(sa_file), scopes=scopes
    )
    ca_certs = _find_ca_certs()
    if ca_certs:
        http = httplib2.Http(ca_certs=ca_certs)
    else:
        http = httplib2.Http()
    http = google_auth_httplib2_authorize(creds, http)
    return build(api_name, api_version, http=http, cache_discovery=False)


def google_auth_httplib2_authorize(credentials, http):
    """google-auth の credentials で httplib2.Http を認証する。"""
    from google_auth_httplib2 import AuthorizedHttp
    return AuthorizedHttp(credentials, http=http)
