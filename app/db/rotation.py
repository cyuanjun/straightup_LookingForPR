"""Rotation repo. One caregiver assigned per family per day-of-week."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db.client import get_client


async def list_for_family(family_id: UUID | str) -> list[dict[str, Any]]:
    client = await get_client()
    resp = (
        await client.table("rotation")
        .select("*")
        .eq("family_id", str(family_id))
        .order("day_of_week")
        .execute()
    )
    return resp.data or []


async def on_duty(family_id: UUID | str, day_of_week: int) -> UUID | None:
    """Return the user_id on duty for the given day (0=Sun..6=Sat), or None if unset."""
    client = await get_client()
    resp = (
        await client.table("rotation")
        .select("user_id")
        .eq("family_id", str(family_id))
        .eq("day_of_week", day_of_week)
        .maybe_single()
        .execute()
    )
    if not resp or not resp.data:
        return None
    return resp.data["user_id"]


async def assign(
    family_id: UUID | str, day_of_week: int, user_id: UUID | str
) -> None:
    """Upsert: assign or reassign a caregiver to a given day."""
    client = await get_client()
    await client.table("rotation").upsert(
        {
            "family_id": str(family_id),
            "day_of_week": day_of_week,
            "user_id": str(user_id),
        },
        on_conflict="family_id,day_of_week",
    ).execute()
