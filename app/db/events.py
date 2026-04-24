"""Events repo. Append-only audit/analytics log. Every row is family-scoped."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.db.client import get_client


async def insert(
    family_id: UUID | str,
    type: str,
    payload: dict[str, Any] | None = None,
    attributed_to: UUID | str | None = None,
    medication_id: UUID | str | None = None,
) -> dict[str, Any]:
    client = await get_client()
    row: dict[str, Any] = {
        "family_id": str(family_id),
        "type": type,
        "payload": payload or {},
    }
    if attributed_to is not None:
        row["attributed_to"] = str(attributed_to)
    if medication_id is not None:
        row["medication_id"] = str(medication_id)
    resp = await client.table("events").insert(row).execute()
    return resp.data[0]


async def had_confirmation_within_window(
    family_id: UUID | str,
    medication_id: UUID | str,
    since: datetime,
) -> bool:
    """Check if a `med_confirmed` event exists for this (family, medication) since `since`."""
    client = await get_client()
    resp = (
        await client.table("events")
        .select("id")
        .eq("family_id", str(family_id))
        .eq("medication_id", str(medication_id))
        .eq("type", "med_confirmed")
        .gte("created_at", since.isoformat())
        .limit(1)
        .execute()
    )
    return bool(resp.data)


async def count_misses_this_week(
    family_id: UUID | str, medication_id: UUID | str
) -> int:
    """Count med_missed events for this medication in the last 7 days (for pattern count)."""
    client = await get_client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    resp = (
        await client.table("events")
        .select("id", count="exact")
        .eq("family_id", str(family_id))
        .eq("medication_id", str(medication_id))
        .eq("type", "med_missed")
        .gte("created_at", cutoff.isoformat())
        .execute()
    )
    return resp.count or 0


async def nudge_counts_last_n_days(
    family_id: UUID | str, days: int = 7
) -> dict[str, int]:
    """Return { user_id -> count } of nudge_sent_by_caregiver events in the last N days."""
    client = await get_client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    resp = (
        await client.table("events")
        .select("attributed_to")
        .eq("family_id", str(family_id))
        .eq("type", "nudge_sent_by_caregiver")
        .gte("created_at", cutoff.isoformat())
        .execute()
    )
    counts: dict[str, int] = {}
    for row in resp.data or []:
        uid = row.get("attributed_to")
        if uid:
            counts[uid] = counts.get(uid, 0) + 1
    return counts


async def recent_for_briefing(
    family_id: UUID | str, window_days: int = 42
) -> list[dict[str, Any]]:
    """Last N days of events for GP briefing compile."""
    client = await get_client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    resp = (
        await client.table("events")
        .select("*")
        .eq("family_id", str(family_id))
        .gte("created_at", cutoff.isoformat())
        .order("created_at")
        .execute()
    )
    return resp.data or []


async def by_id(event_id: UUID | str) -> dict[str, Any] | None:
    client = await get_client()
    resp = (
        await client.table("events")
        .select("*")
        .eq("id", str(event_id))
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


async def most_recent_confirmation(
    family_id: UUID | str, medication_id: UUID | str
) -> dict[str, Any] | None:
    """Latest `med_confirmed` event for this (family, medication) — or None."""
    client = await get_client()
    resp = (
        await client.table("events")
        .select("*")
        .eq("family_id", str(family_id))
        .eq("medication_id", str(medication_id))
        .eq("type", "med_confirmed")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


async def confirmations_today(
    family_id: UUID | str, medication_id: UUID | str
) -> list[dict[str, Any]]:
    """All `med_confirmed` events for this medication since local midnight today."""
    now_local = datetime.now()
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = today_start_local.astimezone(timezone.utc)

    client = await get_client()
    resp = (
        await client.table("events")
        .select("*")
        .eq("family_id", str(family_id))
        .eq("medication_id", str(medication_id))
        .eq("type", "med_confirmed")
        .gte("created_at", today_start.isoformat())
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data or []


async def delete_all_for_family(family_id: UUID | str) -> None:
    """Wipe every event for this family — used by Settings → Reset history."""
    client = await get_client()
    await client.table("events").delete().eq("family_id", str(family_id)).execute()


async def briefing_tokens_for_family(family_id: UUID | str) -> list[str]:
    """Return all briefing tokens recorded in events.payload for this family."""
    client = await get_client()
    resp = (
        await client.table("events")
        .select("payload")
        .eq("family_id", str(family_id))
        .eq("type", "briefing_generated")
        .execute()
    )
    out: list[str] = []
    for row in resp.data or []:
        token = (row.get("payload") or {}).get("token")
        if token:
            out.append(token)
    return out
