"""Conversations repo. Memory for Aunty May. Scoped by family_id + chat_id."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db.client import get_client


async def insert_turn(
    family_id: UUID | str,
    chat_id: int,
    speaker_role: str,  # 'parent' | 'aunty_may' | 'system'
    text: str,
    speaker_user_id: UUID | str | None = None,
    language_code: str | None = None,
) -> None:
    client = await get_client()
    row: dict[str, Any] = {
        "family_id": str(family_id),
        "chat_id": chat_id,
        "speaker_role": speaker_role,
        "text": text,
    }
    if speaker_user_id is not None:
        row["speaker_user_id"] = str(speaker_user_id)
    if language_code is not None:
        row["language_code"] = language_code
    await client.table("conversations").insert(row).execute()


async def last_n_turns(
    family_id: UUID | str, chat_id: int, n: int = 12
) -> list[dict[str, Any]]:
    """Return most recent N turns in chronological order (oldest first)."""
    client = await get_client()
    resp = (
        await client.table("conversations")
        .select("*")
        .eq("family_id", str(family_id))
        .eq("chat_id", chat_id)
        .order("created_at", desc=True)
        .limit(n)
        .execute()
    )
    rows = resp.data or []
    return list(reversed(rows))  # oldest → newest


async def list_for_family(
    family_id: UUID | str, limit: int = 200
) -> list[dict[str, Any]]:
    """All conversation turns for the family, newest first."""
    client = await get_client()
    resp = (
        await client.table("conversations")
        .select("*")
        .eq("family_id", str(family_id))
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data or []


async def count_for_family(family_id: UUID | str) -> int:
    """Total conversation turn count — for "showing N of M" labels."""
    client = await get_client()
    resp = (
        await client.table("conversations")
        .select("id", count="exact")
        .eq("family_id", str(family_id))
        .execute()
    )
    return resp.count or 0


async def delete_all_for_family(family_id: UUID | str) -> None:
    """Wipe every conversation turn for this family — used by Settings → Reset history."""
    client = await get_client()
    await client.table("conversations").delete().eq("family_id", str(family_id)).execute()
