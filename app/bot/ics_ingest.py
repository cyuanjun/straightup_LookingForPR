"""Parse .ics files into appointment dicts.

Tolerates:
  - All-day events (DTSTART is a date, not a datetime — treated as midnight local)
  - Naive datetimes (assumed local TZ)
  - Missing UID — falls back to sha256(title|starts_at|location)
  - UTF-8 then Windows-1252 encoding
  - Past events (skipped)

Does NOT yet expand RRULE. The vast majority of polyclinic / specialist
appointments aren't recurring, so this is fine for MVP.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from icalendar import Calendar

from app.config import settings

log = logging.getLogger(__name__)


def _decode(raw: bytes) -> str:
    """UTF-8 → Windows-1252 fallback (Outlook exports often use the latter)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("windows-1252", errors="replace")


def parse_ics(raw: bytes) -> list[dict[str, Any]]:
    """Return [{uid, starts_at, title, location}, ...]. Skips past events."""
    text = _decode(raw)
    cal = Calendar.from_ical(text)
    tz = ZoneInfo(settings.tz)
    now = datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []

    for component in cal.walk("VEVENT"):
        dtstart_field = component.get("DTSTART")
        if dtstart_field is None:
            continue
        starts_at = dtstart_field.dt

        # Normalize to a tz-aware datetime
        if isinstance(starts_at, datetime):
            if starts_at.tzinfo is None:
                starts_at = starts_at.replace(tzinfo=tz)
        elif isinstance(starts_at, date):
            # All-day event — anchor at midnight local
            starts_at = datetime.combine(starts_at, time(0, 0), tzinfo=tz)
        else:
            continue  # unknown DTSTART type

        # Skip past events
        if starts_at < now:
            continue

        title = (
            str(component.get("SUMMARY"))
            if component.get("SUMMARY")
            else "Appointment"
        )
        location_raw = component.get("LOCATION")
        location = str(location_raw) if location_raw else None

        # UID — use the .ics one if present; otherwise hash the content
        uid_raw = component.get("UID")
        uid = str(uid_raw) if uid_raw else None
        if not uid:
            digest_input = f"{title}|{starts_at.isoformat()}|{location or ''}"
            uid = hashlib.sha256(digest_input.encode()).hexdigest()

        out.append(
            {
                "uid": uid,
                "starts_at": starts_at,
                "title": title,
                "location": location,
            }
        )

    log.info("parse_ics: extracted %d future events", len(out))
    return out
