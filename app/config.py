"""アプリ全体の設定。.env から読み込む。"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """環境変数ベースの設定。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Anthropic / Claude ---
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    claude_model: str = Field("claude-opus-4-6", alias="CLAUDE_MODEL")

    # --- Google Workspace ---
    google_service_account_file: Path = Field(
        ..., alias="GOOGLE_SERVICE_ACCOUNT_FILE"
    )
    google_delegated_user: str = Field(..., alias="GOOGLE_DELEGATED_USER")

    # --- Sheets ---
    grade_definition_sheet_id: str = Field(..., alias="GRADE_DEFINITION_SHEET_ID")
    grade_definition_sheet_gid: str | None = Field(
        None, alias="GRADE_DEFINITION_SHEET_GID"
    )
    kpi_sheet_id: str | None = Field(None, alias="KPI_SHEET_ID")
    action_items_sheet_id: str | None = Field(None, alias="ACTION_ITEMS_SHEET_ID")

    # --- Slack ---
    slack_bot_token: str = Field(..., alias="SLACK_BOT_TOKEN")
    slack_user_token: str | None = Field(None, alias="SLACK_USER_TOKEN")

    # --- 評価設定 ---
    evaluation_window_days: int = Field(90, alias="EVALUATION_WINDOW_DAYS")
    report_output_dir: Path = Field(Path("./reports"), alias="REPORT_OUTPUT_DIR")


_settings: Settings | None = None


def get_settings() -> Settings:
    """シングルトンとして Settings を返す。"""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
