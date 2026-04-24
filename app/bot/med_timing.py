"""Medication timing helpers — find closest scheduled slot, classify on-time vs early/late."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

ON_TIME_WINDOW_MIN = 60  # ±60 min from a scheduled slot = "on time"


def _parse_slot(slot: Any) -> time:
    """medication.times entries may be 'HH:MM', 'HH:MM:SS', or datetime.time."""
    if isinstance(slot, time):
        return slot
    parts = str(slot).split(":")
    return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


def closest_slot(med_times: list, now: datetime) -> tuple[time, int]:
    """Return (slot_time, signed_delta_minutes) for the slot closest to `now`.

    Negative delta = now is BEFORE the slot (early).
    Positive delta = now is AFTER the slot (late).
    """
    best_slot: time | None = None
    best_delta: int | None = None
    for raw in med_times or []:
        slot_t = _parse_slot(raw)
        slot_dt = now.replace(
            hour=slot_t.hour, minute=slot_t.minute, second=0, microsecond=0
        )
        delta_min = int((now - slot_dt).total_seconds() / 60)
        if best_delta is None or abs(delta_min) < abs(best_delta):
            best_slot, best_delta = slot_t, delta_min
    assert best_slot is not None and best_delta is not None  # callers guard empty times[]
    return best_slot, best_delta


def classify_timing(delta_min: int, window_min: int = ON_TIME_WINDOW_MIN) -> str:
    """Bucket a signed delta (minutes) into on_time | early | late."""
    if -window_min <= delta_min <= window_min:
        return "on_time"
    if delta_min < -window_min:
        return "early"
    return "late"
