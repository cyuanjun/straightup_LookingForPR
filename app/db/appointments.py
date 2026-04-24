"""Appointments repo. Upserted on .ics ingest via (family_id, uid)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.db.client import get_client


async def upsert(
    family_id: UUID | str,
    uid: str,
    starts_at: datetime,
    title: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    client = await get_client()
    resp = (
        await client.table("appointments")
        .upsert(
            {
                "family_id": str(family_id),
                "uid": uid,
                "starts_at": starts_at.isoformat(),
                "title": title,
                "location": location,
            },
            on_conflict="family_id,uid",
        )
        .execute()
    )
    return resp.data[0]


async def list_upcoming(
    family_id: UUID | str, limit: int = 20
) -> list[dict[str, Any]]:
    client = await get_client()
    resp = (
        await client.table("appointments")
        .select("*")
        .eq("family_id", str(family_id))
        .gte("starts_at", datetime.now(timezone.utc).isoformat())
        .order("starts_at")
        .limit(limit)
        .execute()
    )
    return resp.data or []


async def by_id(appointment_id: UUID | str) -> dict[str, Any] | None:
    client = await get_client()
    resp = (
        await client.table("appointments")
        .select("*")
        .eq("id", str(appointment_id))
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None
