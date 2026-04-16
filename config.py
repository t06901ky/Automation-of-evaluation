"""設定管理。.env + 固定のデータソース ID を保持する。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# データソース定義 (固定)
# ============================================================

# グレード定義スプレッドシート
GRADE_SHEET_ID = "16N2D1hCDlx2Vl-Ez19WrA_lK5YLueSnaDvivL7rhSfU"
GRADE_SHEET_GID = "979341057"

# 事業計画 KPI スプレッドシート (Tier1 / Tier2)
KPI_SHEET_ID = "1Lo_udJ5YeYlacpMOyJRHMNSl-Ph7tilL"
KPI_SHEET_GID = "707240166"

# 事業計画エグゼクティブサマリ (アクションアイテム目標)
ACTION_ITEMS_PRESENTATION_ID = "1eJ6BB14aYBnWXa1kCUS0BDXIe29cNbb8"
ACTION_ITEMS_SLIDE_ID = "p37"

# Claude モデル
CLAUDE_MODEL = "claude-sonnet-4-20250514"


# ============================================================
# 環境変数から読む動的設定
# ============================================================


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


@dataclass(frozen=True)
class Config:
    """アプリケーション設定。"""

    # API キー
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    google_sa_file: Path = field(
        default_factory=lambda: Path(_env("GOOGLE_SERVICE_ACCOUNT_FILE", "./credentials/service_account.json"))
    )
    slack_bot_token: str = field(default_factory=lambda: _env("SLACK_BOT_TOKEN"))

    # 評価対象者
    target_email: str = field(default_factory=lambda: _env("TARGET_USER_EMAIL"))
    target_name: str = field(default_factory=lambda: _env("TARGET_USER_NAME", ""))
    target_grade: str = field(default_factory=lambda: _env("TARGET_USER_GRADE", ""))
    target_calendar_id: str = field(
        default_factory=lambda: _env("TARGET_CALENDAR_ID", _env("TARGET_USER_EMAIL"))
    )

    # Drive
    drive_folder_id: str = field(default_factory=lambda: _env("DRIVE_FOLDER_ID", ""))

    # 出力先
    output_dir: Path = field(default_factory=lambda: Path("./output"))

    def validate(self) -> list[str]:
        """必須項目が埋まっているかチェック。エラーメッセージのリストを返す。"""
        errors: list[str] = []
        if not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY が未設定")
        if not self.google_sa_file.exists():
            errors.append(f"サービスアカウントファイルが存在しない: {self.google_sa_file}")
        if not self.slack_bot_token:
            errors.append("SLACK_BOT_TOKEN が未設定")
        if not self.target_email:
            errors.append("TARGET_USER_EMAIL が未設定")
        return errors


def get_evaluation_period(reference: date | None = None) -> tuple[date, date]:
    """前月 1 日〜末日を返す。reference が None なら今日基準。"""
    today = reference or date.today()
    first_of_this_month = today.replace(day=1)
    last_of_prev_month = first_of_this_month - relativedelta(days=1)
    first_of_prev_month = last_of_prev_month.replace(day=1)
    return first_of_prev_month, last_of_prev_month
