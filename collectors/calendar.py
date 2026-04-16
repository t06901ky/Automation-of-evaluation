"""Google Calendar API から MTG 情報を取得する。

認証: サービスアカウント。対象者のカレンダーに SA メールの閲覧権限が必要。

注意: MTG「参加数」は NOT 要件 (評価に含めない) だが、
  MTG の質 (テーマ・参加者の構成) は定性評価 (d) の参考データとして使う。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from collectors.auth import build_service

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _service(sa_file: Path):
    return build_service("calendar", "v3", sa_file, SCOPES)


def fetch_meetings(
    sa_file: Path,
    calendar_id: str,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    """対象期間内のカレンダーイベントを取得して集計。

    Returns:
        {
            "total_events": int,
            "organized_count": int,  # 自分主催
            "events": [
                {
                    "summary": str,
                    "start": str,
                    "duration_minutes": int,
                    "organizer": str,
                    "attendee_count": int,
                },
                ...
            ],
        }
    """
    svc = _service(sa_file)

    time_min = datetime.combine(period_start, datetime.min.time(), tzinfo=timezone.utc)
    time_max = datetime.combine(period_end, datetime.max.time(), tzinfo=timezone.utc)

    events: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        resp = (
            svc.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=2500,
                pageToken=page_token or "",
            )
            .execute()
        )
        events.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    parsed: list[dict[str, Any]] = []
    organized_count = 0

    for item in events:
        start_dict = item.get("start", {})
        end_dict = item.get("end", {})

        start_str = start_dict.get("dateTime") or start_dict.get("date", "")
        end_str = end_dict.get("dateTime") or end_dict.get("date", "")

        # 終日イベントはスキップ (MTG ではない)
        if "dateTime" not in start_dict:
            continue

        duration_minutes = _duration_minutes(start_str, end_str)
        organizer_email = (item.get("organizer") or {}).get("email", "")
        is_organized = organizer_email.lower() == calendar_id.lower()
        if is_organized:
            organized_count += 1

        parsed.append(
            {
                "summary": item.get("summary", "(no title)"),
                "start": start_str,
                "duration_minutes": duration_minutes,
                "organizer": organizer_email,
                "attendee_count": len(item.get("attendees", [])),
            }
        )

    return {
        "total_events": len(parsed),
        "organized_count": organized_count,
        "events": parsed[:100],  # LLM 用に最大 100 件
    }


def _duration_minutes(start_str: str, end_str: str) -> int:
    try:
        s = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        return max(0, int((e - s).total_seconds() / 60))
    except (ValueError, TypeError):
        return 0
