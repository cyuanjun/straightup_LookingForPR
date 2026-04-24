"""Audio-cache repo. Keyed by sha256(text||voice_id); stores local file path."""

from __future__ import annotations

from typing import Any

from app.db.client import get_client


async def get(text_hash: str) -> dict[str, Any] | None:
    client = await get_client()
    resp = (
        await client.table("audio_cache")
        .select("*")
        .eq("text_hash", text_hash)
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


async def upsert(text_hash: str, voice_id: str, file_path: str) -> None:
    client = await get_client()
    await client.table("audio_cache").upsert(
        {
            "text_hash": text_hash,
            "voice_id": voice_id,
            "file_path": file_path,
        },
        on_conflict="text_hash",
    ).execute()


async def delete(text_hash: str) -> None:
    """Used when a cached file goes missing and we need to regenerate."""
    client = await get_client()
    await client.table("audio_cache").delete().eq("text_hash", text_hash).execute()
