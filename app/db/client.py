"""Supabase async client singleton. Uses service-role key (bypasses RLS)."""

from __future__ import annotations

from supabase import AsyncClient, acreate_client

from app.config import settings

_client: AsyncClient | None = None


async def get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = await acreate_client(
            settings.supabase_url,
            settings.supabase_service_key,
        )
    return _client
