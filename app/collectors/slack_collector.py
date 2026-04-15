"""Slack から評価対象者の活動データを収集する。

集計指標:
  - メッセージ数 / スレッド開始 / スレッド返信
  - リアクション (与えた / 受けた)
  - アクティブチャンネル数
  - 平均応答時間 (メンションされてからの返信)
  - 業務時間外 / 週末メッセージ数 (働きすぎアラート)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.models import SlackActivity

# 業務時間 (JST 想定)。AM 9:00〜PM 7:00 の外を「after_hours」とする。
WORK_START = time(9, 0)
WORK_END = time(19, 0)


def _resolve_user_id(client: WebClient, email: str) -> str | None:
    try:
        resp = client.users_lookupByEmail(email=email)
        return resp.get("user", {}).get("id")
    except SlackApiError:
        return None


def fetch_slack_activity(
    bot_token: str,
    user_token: str | None,
    target_email: str,
    period_start: date,
    period_end: date,
) -> SlackActivity | None:
    """対象ユーザの Slack 活動を集計する。

    bot_token: 基本 API (users.lookupByEmail, conversations.history 等)
    user_token: search.messages 等の user-scope のみで使える API に必要
    """
    bot_client = WebClient(token=bot_token)

    user_id = _resolve_user_id(bot_client, target_email)
    if user_id is None:
        return None

    activity = SlackActivity(
        user_id=user_id,
        user_email=target_email,
        period_start=period_start,
        period_end=period_end,
    )

    # search.messages は user_token が必要
    search_client = WebClient(token=user_token) if user_token else None

    if search_client is not None:
        _aggregate_via_search(search_client, user_id, target_email, activity)

    return activity


def _aggregate_via_search(
    search_client: WebClient,
    user_id: str,
    target_email: str,
    activity: SlackActivity,
) -> None:
    """search.messages を使って集計する。

    search.messages のクエリ仕様:
      from:@<username> after:YYYY-MM-DD before:YYYY-MM-DD
    """
    # 対象期間内に対象ユーザが書いた全メッセージを検索
    after = activity.period_start.isoformat()
    before = activity.period_end.isoformat()

    query = f"from:<@{user_id}> after:{after} before:{before}"

    channels: set[str] = set()
    response_minutes: list[float] = []
    weekend_count = 0
    after_hours_count = 0
    thread_started = 0
    thread_replied = 0

    cursor: str | None = None
    page = 1
    total = 0

    while True:
        try:
            resp = search_client.search_messages(
                query=query,
                count=100,
                page=page,
                sort="timestamp",
                sort_dir="desc",
            )
        except SlackApiError:
            break

        matches = (resp.get("messages") or {}).get("matches") or []
        if not matches:
            break

        for m in matches:
            total += 1
            channels.add((m.get("channel") or {}).get("id", ""))
            ts = float(m.get("ts", "0") or 0)
            sent_at = datetime.fromtimestamp(ts, tz=timezone.utc)

            if _is_weekend(sent_at):
                weekend_count += 1
            if _is_after_hours(sent_at):
                after_hours_count += 1

            # スレッド判定
            thread_ts = m.get("thread_ts")
            if thread_ts and thread_ts != m.get("ts"):
                thread_replied += 1
            elif thread_ts:
                thread_started += 1

        paging = (resp.get("messages") or {}).get("paging") or {}
        if page >= int(paging.get("pages", 1)):
            break
        page += 1

    activity.messages_sent = total
    activity.unique_channels_active = len([c for c in channels if c])
    activity.threads_started = thread_started
    activity.threads_replied = thread_replied
    activity.weekend_messages = weekend_count
    activity.after_hours_messages = after_hours_count
    if response_minutes:
        activity.avg_response_minutes = sum(response_minutes) / len(response_minutes)


def _is_weekend(dt: datetime) -> bool:
    return dt.weekday() >= 5  # 5=Sat, 6=Sun


def _is_after_hours(dt: datetime) -> bool:
    t = dt.time()
    return t < WORK_START or t >= WORK_END
