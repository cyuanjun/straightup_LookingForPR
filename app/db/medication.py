"""Medication repo. Fixed daily times only for MVP."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db.client import get_client


async def list_active(family_id: UUID | str) -> list[dict[str, Any]]:
    client = await get_client()
    resp = (
        await client.table("medication")
        .select("*")
        .eq("family_id", str(family_id))
        .eq("active", True)
        .execute()
    )
    return resp.data or []


async def list_all_active_across_families() -> list[dict[str, Any]]:
    """Used at scheduler startup to register jobs for every active med."""
    client = await get_client()
    resp = (
        await client.table("medication")
        .select("*")
        .eq("active", True)
        .execute()
    )
    return resp.data or []


async def by_id(medication_id: UUID | str) -> dict[str, Any] | None:
    client = await get_client()
    resp = (
        await client.table("medication")
        .select("*")
        .eq("id", str(medication_id))
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


async def create(
    family_id: UUID | str, name: str, dose: str, times: list[str]
) -> dict[str, Any]:
    client = await get_client()
    resp = (
        await client.table("medication")
        .insert(
            {
                "family_id": str(family_id),
                "name": name,
                "dose": dose,
                "times": times,
                "active": True,
            }
        )
        .execute()
    )
    return resp.data[0]


async def update(
    medication_id: UUID | str,
    *,
    name: str | None = None,
    dose: str | None = None,
    times: list[str] | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if name is not None:
        patch["name"] = name
    if dose is not None:
        patch["dose"] = dose
    if times is not None:
        patch["times"] = times
    if active is not None:
        patch["active"] = active
    client = await get_client()
    resp = (
        await client.table("medication")
        .update(patch)
        .eq("id", str(medication_id))
        .execute()
    )
    return resp.data[0]


async def deactivate(medication_id: UUID | str) -> None:
    await update(medication_id, active=False)
