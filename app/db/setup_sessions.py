"""Setup-sessions repo. Persists /setup wizard progress so it survives restarts."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db.client import get_client


async def get(
    family_id: UUID | str, caregiver_user_id: UUID | str
) -> dict[str, Any] | None:
    client = await get_client()
    resp = (
        await client.table("setup_sessions")
        .select("*")
        .eq("family_id", str(family_id))
        .eq("caregiver_user_id", str(caregiver_user_id))
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


async def upsert_state(
    family_id: UUID | str, caregiver_user_id: UUID | str, state: dict[str, Any]
) -> None:
    from datetime import datetime, timezone

    client = await get_client()
    await client.table("setup_sessions").upsert(
        {
            "family_id": str(family_id),
            "caregiver_user_id": str(caregiver_user_id),
            "state": state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="family_id,caregiver_user_id",
    ).execute()


async def clear(family_id: UUID | str, caregiver_user_id: UUID | str) -> None:
    client = await get_client()
    await client.table("setup_sessions").delete().eq(
        "family_id", str(family_id)
    ).eq("caregiver_user_id", str(caregiver_user_id)).execute()
