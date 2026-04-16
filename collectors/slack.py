"""Slack API から対象ユーザの投稿内容・メッセージ数を取得する。

全チャンネル対象。レート制限 (Tier 2/3) を丁寧にハンドリング。
Bot Token に必要な scope: channels:history, channels:read,
  groups:history, groups:read, users:read, users:read.email
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timezone
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

# AI ツール使用のプロキシキーワード
AI_KEYWORDS = [
    "claude",
    "gemini",
    "notebooklm",
    "notebook lm",
    "chatgpt",
    "gpt",
    "copilot",
    "ai",
    "anthropic",
    "openai",
]

AI_KEYWORD_PATTERN = re.compile(
    "|".join(re.escape(k) for k in AI_KEYWORDS), re.IGNORECASE
)


def _to_ts(d: date) -> str:
    """date → Slack timestamp 文字列。"""
    dt = datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)
    return str(dt.timestamp())


def resolve_user_id(client: WebClient, email: str) -> str | None:
    try:
        resp = client.users_lookupByEmail(email=email)
        return resp.get("user", {}).get("id")
    except SlackApiError:
        return None


@retry(
    retry=retry_if_exception_type(SlackApiError),
    stop=stop_after_attempt(3),
    wait=wait_fixed(3),
)
def _safe_api_call(method, **kwargs):
    """レート制限 (429) のみリトライ。それ以外のエラーは即 raise。"""
    try:
        return method(**kwargs)
    except SlackApiError as e:
        if e.response.status_code == 429:
            retry_after = int(e.response.headers.get("Retry-After", "5"))
            time.sleep(retry_after)
            raise  # tenacity がリトライ
        raise  # not_in_channel 等はリトライせず即 raise


def fetch_all_channels(client: WebClient) -> list[dict[str, Any]]:
    """Bot がアクセス可能な全チャンネル (public + private) を取得。"""
    channels: list[dict[str, Any]] = []
    cursor = None
    while True:
        resp = _safe_api_call(
            client.conversations_list,
            types="public_channel,private_channel",
            limit=1000,
            cursor=cursor or "",
        )
        channels.extend(resp.get("channels", []))
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return channels


def fetch_user_messages(
    bot_token: str,
    target_email: str,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    """対象ユーザの期間内全メッセージを収集して集計結果を返す。

    Returns:
        {
            "user_id": str,
            "total_messages": int,
            "channel_count": int,
            "messages_by_channel": {channel_name: count},
            "sample_messages": [str, ...],  # LLM 評価用に最大 100 件
            "ai_keyword_mentions": int,
            "ai_keyword_examples": [str, ...],
        }
    """
    client = WebClient(token=bot_token)

    user_id = resolve_user_id(client, target_email)
    if not user_id:
        return {"error": f"ユーザが見つからない: {target_email}"}

    channels = fetch_all_channels(client)
    oldest = _to_ts(period_start)
    # period_end の翌日 00:00:00 まで
    latest = _to_ts(period_end + __import__("datetime").timedelta(days=1))

    total_messages = 0
    messages_by_channel: dict[str, int] = {}
    sample_messages: list[str] = []
    ai_mentions = 0
    ai_examples: list[str] = []

    # Bot が参加しているチャンネルのみ処理
    member_channels = [ch for ch in channels if ch.get("is_member", False)]
    skipped = len(channels) - len(member_channels)
    if skipped:
        print(f"       (Bot 未参加チャンネル {skipped} 件をスキップ)")

    for ch in member_channels:
        ch_id = ch["id"]
        ch_name = ch.get("name", ch_id)
        ch_messages = _fetch_channel_messages(client, ch_id, user_id, oldest, latest)

        if not ch_messages:
            continue

        count = len(ch_messages)
        total_messages += count
        messages_by_channel[ch_name] = count

        for msg in ch_messages:
            text = msg.get("text", "")

            # サンプルメッセージ (LLM 用、最大 100 件)
            if len(sample_messages) < 100 and len(text) > 10:
                sample_messages.append(f"[#{ch_name}] {text[:500]}")

            # AI キーワード検出
            if AI_KEYWORD_PATTERN.search(text):
                ai_mentions += 1
                if len(ai_examples) < 20:
                    ai_examples.append(f"[#{ch_name}] {text[:300]}")

    return {
        "user_id": user_id,
        "total_messages": total_messages,
        "channel_count": len(messages_by_channel),
        "messages_by_channel": messages_by_channel,
        "sample_messages": sample_messages,
        "ai_keyword_mentions": ai_mentions,
        "ai_keyword_examples": ai_examples,
    }


def _fetch_channel_messages(
    client: WebClient,
    channel_id: str,
    user_id: str,
    oldest: str,
    latest: str,
) -> list[dict[str, Any]]:
    """1 チャンネル内の対象ユーザメッセージを取得 (ページネーション対応)。"""
    messages: list[dict[str, Any]] = []
    cursor = None

    while True:
        try:
            resp = _safe_api_call(
                client.conversations_history,
                channel=channel_id,
                oldest=oldest,
                latest=latest,
                limit=200,
                cursor=cursor or "",
            )
        except SlackApiError:
            # Bot がチャンネルに参加していない等
            break

        for msg in resp.get("messages", []):
            if msg.get("user") == user_id and msg.get("type") == "message":
                messages.append(msg)

        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

        # レート制限を避けるためスリープ
        time.sleep(1.2)

    return messages
