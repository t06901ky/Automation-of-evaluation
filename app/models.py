"""評価ドメインのデータモデル。"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


# ============================================================
# 評価対象者
# ============================================================


class Employee(BaseModel):
    """評価対象者。"""

    email: str
    name: str
    grade: str  # 例: "G3", "M2" 等。grade_definition シートの行と一致させる
    department: str | None = None
    manager_email: str | None = None


# ============================================================
# 評価項目 (a〜g) — README の優先順位
# ============================================================


class EvaluationCategory(str, Enum):
    """評価項目カテゴリ。a が最優先、g が最低優先。"""

    A_TIER1_KPI = "a_tier1_kpi"  # 売上、ARR、OTR、HC
    B_TIER2_KPI = "b_tier2_kpi"  # churn, MQL, SQL, コスト
    C_ACTION_ITEM = "c_action_item"  # 重要 countable アクション
    D_BUSINESS_QUAL = "d_business_qual"  # 業務系定性 (mtg/ops 貢献等)
    E_OTHER_QUAL = "e_other_qual"  # AI 活用、社内コミュ
    F_NOT_REQUIREMENT = "f_not_requirement"  # 「私頑張った」系の無力化
    G_MANAGER_NOTE = "g_manager_note"  # 上司補足コメント


# 既定の重みづけ。a が最も高く、優先順位順に減衰する。
DEFAULT_WEIGHTS: dict[EvaluationCategory, float] = {
    EvaluationCategory.A_TIER1_KPI: 0.30,
    EvaluationCategory.B_TIER2_KPI: 0.20,
    EvaluationCategory.C_ACTION_ITEM: 0.18,
    EvaluationCategory.D_BUSINESS_QUAL: 0.13,
    EvaluationCategory.E_OTHER_QUAL: 0.09,
    EvaluationCategory.F_NOT_REQUIREMENT: 0.05,  # 減点側で機能
    EvaluationCategory.G_MANAGER_NOTE: 0.05,
}


# ============================================================
# 収集データ
# ============================================================


class CalendarEvent(BaseModel):
    """Google カレンダーから取得する 1 件のイベント。"""

    id: str
    summary: str
    start: datetime
    end: datetime
    organizer_email: str | None = None
    attendee_emails: list[str] = Field(default_factory=list)
    is_recurring: bool = False
    is_all_day: bool = False


class SlackActivity(BaseModel):
    """Slack の活動サマリ (期間集計)。"""

    user_id: str
    user_email: str
    period_start: date
    period_end: date

    messages_sent: int = 0
    threads_started: int = 0
    threads_replied: int = 0
    reactions_given: int = 0
    reactions_received: int = 0
    unique_channels_active: int = 0
    avg_response_minutes: float | None = None  # メンション後の平均応答時間
    weekend_messages: int = 0
    after_hours_messages: int = 0


class KpiResult(BaseModel):
    """KPI 1 行 (シートから取得)。"""

    name: str  # "ARR", "売上" 等
    tier: int  # 1 or 2
    target: float | None = None
    actual: float | None = None
    achievement_rate: float | None = None  # 達成率 (1.0 = 100%)
    owner_email: str | None = None
    notes: str | None = None


class ActionItem(BaseModel):
    """アクションアイテム (c 項目)。"""

    title: str
    owner_email: str
    status: str  # "completed" / "in_progress" / "blocked" / "not_started"
    due_date: date | None = None
    completed_date: date | None = None
    importance: str | None = None  # "high" / "medium" / "low"
    description: str | None = None


class ManagerNote(BaseModel):
    """上司からの補足コメント (g 項目)。"""

    employee_email: str
    manager_email: str
    text: str
    created_at: datetime | None = None


# ============================================================
# 評価結果
# ============================================================


class CategoryScore(BaseModel):
    """1 カテゴリ分の評価結果。"""

    category: EvaluationCategory
    score: float = Field(..., ge=0.0, le=5.0)  # 0〜5 の連続値
    weight: float
    weighted_score: float
    rationale: str  # スコア根拠 (LLM が生成)
    evidence: list[str] = Field(default_factory=list)  # 根拠データ
    flags: list[str] = Field(default_factory=list)  # 注意フラグ


class EvaluationReport(BaseModel):
    """1 名分の評価レポート。"""

    employee: Employee
    period_start: date
    period_end: date
    grade_definition_summary: str  # 適用されたグレード定義 (要約)
    overall_score: float = Field(..., ge=0.0, le=5.0)
    overall_rating: str  # "Exceeds" / "Meets" / "Below" 等
    category_scores: list[CategoryScore]
    summary: str  # 上司向け要約
    recommended_actions: list[str] = Field(default_factory=list)
    fairness_notes: list[str] = Field(default_factory=list)  # 公平性の検証メモ
    generated_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# 評価コンテキスト (Engine に渡すデータ集約)
# ============================================================


class EvaluationContext(BaseModel):
    """1 名の評価に必要な収集済みデータ全部。"""

    employee: Employee
    period_start: date
    period_end: date
    grade_definition_text: str  # シートからそのまま取得した定義テキスト

    calendar_events: list[CalendarEvent] = Field(default_factory=list)
    slack_activity: SlackActivity | None = None
    kpi_results: list[KpiResult] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    manager_notes: list[ManagerNote] = Field(default_factory=list)
