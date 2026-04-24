"""Users repo. Family-scoped; supports unlinked caregivers (nullable telegram_user_id)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db.client import get_client


async def by_id(user_id: UUID | str) -> dict[str, Any] | None:
    client = await get_client()
    resp = (
        await client.table("users")
        .select("*")
        .eq("id", str(user_id))
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


async def by_telegram_id(family_id: UUID | str, telegram_user_id: int) -> dict[str, Any] | None:
    client = await get_client()
    resp = (
        await client.table("users")
        .select("*")
        .eq("family_id", str(family_id))
        .eq("telegram_user_id", telegram_user_id)
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


async def find_parent_by_telegram_id(telegram_user_id: int) -> dict[str, Any] | None:
    """Look up the parent user across all families for a given Telegram ID (voice-handler guard)."""
    client = await get_client()
    resp = (
        await client.table("users")
        .select("*")
        .eq("telegram_user_id", telegram_user_id)
        .eq("role", "parent")
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


async def list_caregivers(family_id: UUID | str) -> list[dict[str, Any]]:
    client = await get_client()
    resp = (
        await client.table("users")
        .select("*")
        .eq("family_id", str(family_id))
        .eq("role", "caregiver")
        .execute()
    )
    return resp.data or []


async def list_all(family_id: UUID | str) -> list[dict[str, Any]]:
    client = await get_client()
    resp = (
        await client.table("users")
        .select("*")
        .eq("family_id", str(family_id))
        .execute()
    )
    return resp.data or []


async def create_unlinked_caregiver(
    family_id: UUID | str, display_name: str
) -> dict[str, Any]:
    """Create a caregiver row with nullable Telegram fields (used during /setup rotation entry)."""
    client = await get_client()
    resp = (
        await client.table("users")
        .insert(
            {
                "family_id": str(family_id),
                "display_name": display_name,
                "role": "caregiver",
            }
        )
        .execute()
    )
    return resp.data[0]


async def link_telegram(
    user_id: UUID | str,
    telegram_user_id: int,
    telegram_chat_id: int,
    telegram_username: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    """Populate Telegram identity on an existing user row."""
    client = await get_client()
    patch: dict[str, Any] = {
        "telegram_user_id": telegram_user_id,
        "telegram_chat_id": telegram_chat_id,
    }
    if telegram_username is not None:
        patch["telegram_username"] = telegram_username
    if display_name is not None:
        patch["display_name"] = display_name
    resp = (
        await client.table("users")
        .update(patch)
        .eq("id", str(user_id))
        .execute()
    )
    return resp.data[0]


async def upsert_caregiver_from_telegram(
    family_id: UUID | str,
    telegram_user_id: int,
    telegram_chat_id: int,
    telegram_username: str | None,
    display_name: str,
) -> dict[str, Any]:
    """Used by ✓ Sent JIT linking: if tapper has no users row, create one as caregiver."""
    existing = await by_telegram_id(family_id, telegram_user_id)
    if existing:
        return existing
    client = await get_client()
    resp = (
        await client.table("users")
        .insert(
            {
                "family_id": str(family_id),
                "telegram_user_id": telegram_user_id,
                "telegram_chat_id": telegram_chat_id,
                "telegram_username": telegram_username,
                "display_name": display_name,
                "role": "caregiver",
            }
        )
        .execute()
    )
    return resp.data[0]


async def upsert_parent_from_handshake(
    family_id: UUID | str,
    existing_user_id: UUID | str | None,
    telegram_user_id: int,
    telegram_chat_id: int,
    telegram_username: str | None,
    display_name: str,
) -> dict[str, Any]:
    """Called on parent handshake YES. If a parent row was pre-seeded, update it; else create."""
    if existing_user_id:
        return await link_telegram(
            existing_user_id,
            telegram_user_id,
            telegram_chat_id,
            telegram_username,
            display_name,
        )
    client = await get_client()
    resp = (
        await client.table("users")
        .insert(
            {
                "family_id": str(family_id),
                "telegram_user_id": telegram_user_id,
                "telegram_chat_id": telegram_chat_id,
                "telegram_username": telegram_username,
                "display_name": display_name,
                "role": "parent",
            }
        )
        .execute()
    )
    return resp.data[0]
