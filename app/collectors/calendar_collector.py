"""Google カレンダーから対象者の予定を収集する。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.collectors.google_auth import calendar_service
from app.models import CalendarEvent


def fetch_events(
    service_account_file: Path,
    delegated_user: str,
    target_email: str,
    period_start: datetime,
    period_end: datetime,
) -> list[CalendarEvent]:
    """target_email の主カレンダーから期間内のイベントを取得。

    Domain-Wide Delegation を使い、対象者本人として API を叩く。
    """
    # 委任ユーザーを target_email に切り替えて呼び出す
    service = calendar_service(service_account_file, target_email)

    events: list[CalendarEvent] = []
    page_token: str | None = None

    while True:
        response = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=_iso_utc(period_start),
                timeMax=_iso_utc(period_end),
                singleEvents=True,
                orderBy="startTime",
                maxResults=2500,
                pageToken=page_token,
            )
            .execute()
        )

        for item in response.get("items", []):
            event = _to_calendar_event(item)
            if event is not None:
                events.append(event)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return events


def _to_calendar_event(item: dict) -> CalendarEvent | None:
    """Calendar API のレスポンス 1 件を CalendarEvent に変換。"""
    start_dict = item.get("start") or {}
    end_dict = item.get("end") or {}

    start_str = start_dict.get("dateTime") or start_dict.get("date")
    end_str = end_dict.get("dateTime") or end_dict.get("date")
    if not start_str or not end_str:
        return None

    is_all_day = "date" in start_dict and "dateTime" not in start_dict

    return CalendarEvent(
        id=item["id"],
        summary=item.get("summary", "(no title)"),
        start=_parse_dt(start_str),
        end=_parse_dt(end_str),
        organizer_email=(item.get("organizer") or {}).get("email"),
        attendee_emails=[
            a.get("email", "")
            for a in (item.get("attendees") or [])
            if a.get("email")
        ],
        is_recurring=bool(item.get("recurringEventId")),
        is_all_day=is_all_day,
    )


def _iso_utc(dt: datetime) -> str:
    """UTC ISO8601 (RFC3339) 形式に変換。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_dt(s: str) -> datetime:
    """date / dateTime 文字列を datetime に変換。"""
    # 末尾 Z を +00:00 に
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # all-day "YYYY-MM-DD" のケース
        return datetime.fromisoformat(s + "T00:00:00+00:00")
