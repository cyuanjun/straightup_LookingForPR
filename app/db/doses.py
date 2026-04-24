"""Dose instances repo — canonical adherence source.

One row per scheduled medication slot. Lifecycle:
    pending → confirmed | missed_unresolved → missed_resolved

The events table remains append-only for audit/briefing; dose_instances is the
normalized state so adherence becomes `COUNT(*) GROUP BY status`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.db.client import get_client


async def create_pending(
    family_id: UUID | str,
    medication_id: UUID | str,
    *,
    scheduled_at: datetime,
    slot: str,
    reminder_event_id: UUID | str | None,
) -> dict[str, Any]:
    client = await get_client()
    row: dict[str, Any] = {
        "family_id": str(family_id),
        "medication_id": str(medication_id),
        "scheduled_at": scheduled_at.isoformat(),
        "slot": slot,
        "status": "pending",
    }
    if reminder_event_id is not None:
        row["reminder_event_id"] = str(reminder_event_id)
    resp = await client.table("dose_instances").insert(row).execute()
    return resp.data[0]


async def by_id(dose_id: UUID | str) -> dict[str, Any] | None:
    client = await get_client()
    resp = (
        await client.table("dose_instances")
        .select("*")
        .eq("id", str(dose_id))
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


async def find_pending_for_med(
    family_id: UUID | str,
    medication_id: UUID | str,
    *,
    since: datetime,
) -> dict[str, Any] | None:
    """Most recent `pending` dose for this med scheduled on/after `since`."""
    client = await get_client()
    resp = (
        await client.table("dose_instances")
        .select("*")
        .eq("family_id", str(family_id))
        .eq("medication_id", str(medication_id))
        .eq("status", "pending")
        .gte("scheduled_at", since.isoformat())
        .order("scheduled_at", desc=True)
        .limit(1)
        .execute()
    )
    return (resp.data or [None])[0]


async def find_missed_unresolved_for_med(
    family_id: UUID | str,
    medication_id: UUID | str,
    *,
    since: datetime,
) -> dict[str, Any] | None:
    """Most recent unresolved miss for this med, since `since` (resolution window)."""
    client = await get_client()
    resp = (
        await client.table("dose_instances")
        .select("*")
        .eq("family_id", str(family_id))
        .eq("medication_id", str(medication_id))
        .eq("status", "missed_unresolved")
        .gte("missed_at", since.isoformat())
        .order("missed_at", desc=True)
        .limit(1)
        .execute()
    )
    return (resp.data or [None])[0]


async def mark_confirmed(
    dose_id: UUID | str,
    *,
    timing: str,
    confirm_event_id: UUID | str,
    confirmed_at: datetime | None = None,
) -> dict[str, Any]:
    patch = {
        "status": "confirmed",
        "timing": timing,
        "confirm_event_id": str(confirm_event_id),
        "confirmed_at": (confirmed_at or datetime.now(timezone.utc)).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client = await get_client()
    resp = (
        await client.table("dose_instances").update(patch).eq("id", str(dose_id)).execute()
    )
    return resp.data[0]


async def mark_missed(
    dose_id: UUID | str,
    *,
    miss_event_id: UUID | str,
    missed_at: datetime | None = None,
) -> dict[str, Any]:
    patch = {
        "status": "missed_unresolved",
        "miss_event_id": str(miss_event_id),
        "missed_at": (missed_at or datetime.now(timezone.utc)).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client = await get_client()
    resp = (
        await client.table("dose_instances").update(patch).eq("id", str(dose_id)).execute()
    )
    return resp.data[0]


async def resolve_miss(
    dose_id: UUID | str,
    *,
    confirm_event_id: UUID | str,
    confirmed_at: datetime | None = None,
) -> dict[str, Any]:
    """Flip a missed_unresolved dose to missed_resolved (timing=late)."""
    patch = {
        "status": "missed_resolved",
        "timing": "late",
        "confirm_event_id": str(confirm_event_id),
        "confirmed_at": (confirmed_at or datetime.now(timezone.utc)).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    client = await get_client()
    resp = (
        await client.table("dose_instances").update(patch).eq("id", str(dose_id)).execute()
    )
    return resp.data[0]


async def create_standalone_confirmed(
    family_id: UUID | str,
    medication_id: UUID | str,
    *,
    scheduled_at: datetime,
    slot: str,
    timing: str,
    confirm_event_id: UUID | str,
    confirmed_at: datetime | None = None,
) -> dict[str, Any]:
    """Parent confirmed with no matching pending dose (e.g. took it before the reminder)."""
    now = confirmed_at or datetime.now(timezone.utc)
    row = {
        "family_id": str(family_id),
        "medication_id": str(medication_id),
        "scheduled_at": scheduled_at.isoformat(),
        "slot": slot,
        "status": "confirmed",
        "timing": timing,
        "confirm_event_id": str(confirm_event_id),
        "confirmed_at": now.isoformat(),
    }
    client = await get_client()
    resp = await client.table("dose_instances").insert(row).execute()
    return resp.data[0]


async def list_recent_for_family(
    family_id: UUID | str,
    *,
    days: int = 30,
) -> list[dict[str, Any]]:
    """All doses scheduled within the last N days (newest first)."""
    client = await get_client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    resp = (
        await client.table("dose_instances")
        .select("*")
        .eq("family_id", str(family_id))
        .gte("scheduled_at", cutoff.isoformat())
        .order("scheduled_at", desc=True)
        .execute()
    )
    return resp.data or []


async def delete_all_for_family(family_id: UUID | str) -> None:
    """Wipe every dose_instance for this family — used by Settings → Reset history."""
    client = await get_client()
    await client.table("dose_instances").delete().eq("family_id", str(family_id)).execute()
