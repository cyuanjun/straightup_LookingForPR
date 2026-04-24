"""Family repo. Every method is scoped by family_id."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db.client import get_client


async def get(family_id: UUID | str) -> dict[str, Any] | None:
    client = await get_client()
    resp = (
        await client.table("families")
        .select("*")
        .eq("id", str(family_id))
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


async def is_active(family_id: UUID | str) -> bool:
    """Per plan: active iff parent_user_id + primary_caregiver_user_id + group_chat_id all set."""
    fam = await get(family_id)
    if fam is None:
        return False
    return bool(fam.get("parent_user_id")) and bool(
        fam.get("primary_caregiver_user_id")
    ) and bool(fam.get("group_chat_id"))


async def is_paused(family_id: UUID | str) -> bool:
    fam = await get(family_id)
    return bool(fam and fam.get("paused"))


async def state(family_id: UUID | str) -> str:
    """Returns 'active' | 'inactive_missing_fields' | 'paused' | 'not_found'."""
    fam = await get(family_id)
    if fam is None:
        return "not_found"
    if fam.get("paused"):
        return "paused"
    if (
        fam.get("parent_user_id")
        and fam.get("primary_caregiver_user_id")
        and fam.get("group_chat_id")
    ):
        return "active"
    return "inactive_missing_fields"


async def missing_fields(family_id: UUID | str) -> list[str]:
    fam = await get(family_id)
    if fam is None:
        return ["family_not_found"]
    missing = []
    if not fam.get("parent_user_id"):
        missing.append("parent_handshake")
    if not fam.get("primary_caregiver_user_id"):
        missing.append("primary_caregiver")
    if not fam.get("group_chat_id"):
        missing.append("group_link")
    return missing


async def set_paused(family_id: UUID | str, paused: bool) -> None:
    client = await get_client()
    await client.table("families").update({"paused": paused}).eq(
        "id", str(family_id)
    ).execute()


async def set_group_chat_id(family_id: UUID | str, group_chat_id: int) -> None:
    client = await get_client()
    await client.table("families").update({"group_chat_id": group_chat_id}).eq(
        "id", str(family_id)
    ).execute()


async def set_parent_user_id(family_id: UUID | str, parent_user_id: UUID | str) -> None:
    client = await get_client()
    await client.table("families").update(
        {"parent_user_id": str(parent_user_id)}
    ).eq("id", str(family_id)).execute()


async def set_primary_caregiver(
    family_id: UUID | str, primary_caregiver_user_id: UUID | str
) -> None:
    client = await get_client()
    await client.table("families").update(
        {"primary_caregiver_user_id": str(primary_caregiver_user_id)}
    ).eq("id", str(family_id)).execute()
