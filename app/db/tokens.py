"""Pending-tokens repo. Serves both parent_handshake and group_linking flows.

Atomic claim for parent_handshake prevents race conditions: two users tapping
the same link concurrently cannot both succeed.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.db.client import get_client


def _expires_at(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


async def create_parent_handshake(
    family_id: UUID | str,
    created_by_user_id: UUID | str,
    ttl_hours: int = 24,
) -> str:
    """Generate a URL-safe token for the parent's deep link. Returns the token string."""
    token = secrets.token_urlsafe(16)  # 22+ chars, satisfies check constraint
    client = await get_client()
    await client.table("pending_tokens").insert(
        {
            "token": token,
            "family_id": str(family_id),
            "purpose": "parent_handshake",
            "created_by_user_id": str(created_by_user_id),
            "status": "pending_confirm",
            "expires_at": _expires_at(ttl_hours),
        }
    ).execute()
    return token


async def create_group_linking(
    family_id: UUID | str,
    created_by_user_id: UUID | str,
    ttl_hours: int = 24,
) -> tuple[str, str]:
    """Generate a 6-digit setup_code for /linkfamily. Retries on collision.

    Returns (token, setup_code). The token is the primary key (random UUID-style);
    setup_code is the human-typable 6-digit value.
    """
    client = await get_client()
    for _ in range(8):
        setup_code = f"{secrets.randbelow(1_000_000):06d}"
        token = secrets.token_urlsafe(16)
        try:
            await client.table("pending_tokens").insert(
                {
                    "token": token,
                    "family_id": str(family_id),
                    "purpose": "group_linking",
                    "setup_code": setup_code,
                    "created_by_user_id": str(created_by_user_id),
                    "status": "pending_confirm",
                    "expires_at": _expires_at(ttl_hours),
                }
            ).execute()
            return token, setup_code
        except Exception:  # noqa: BLE001 — partial unique index collision, retry
            continue
    raise RuntimeError("Could not allocate a unique setup_code after 8 attempts")


async def atomic_claim_parent(
    token: str, telegram_user_id: int
) -> dict[str, Any] | None:
    """Soft-claim a parent_handshake token. Returns the row (with family_id) if claim succeeded.

    Uses a single-row UPDATE predicate so two concurrent taps can't both claim.
    Returns None if token not found, already claimed, wrong purpose, expired, or not pending.
    """
    client = await get_client()
    resp = (
        await client.table("pending_tokens")
        .update({"claimed_by": telegram_user_id})
        .eq("token", token)
        .eq("purpose", "parent_handshake")
        .eq("status", "pending_confirm")
        .is_("claimed_by", "null")
        .gte("expires_at", datetime.now(timezone.utc).isoformat())
        .execute()
    )
    return resp.data[0] if resp.data else None


async def confirm_parent(token: str) -> None:
    """Finalize a parent_handshake token after the parent replies 'yes'."""
    client = await get_client()
    await client.table("pending_tokens").update(
        {
            "status": "confirmed",
            "consumed_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("token", token).execute()


async def release_parent(token: str) -> None:
    """Clear the soft-claim if the parent declined; leaves the token reusable."""
    client = await get_client()
    await client.table("pending_tokens").update({"claimed_by": None}).eq(
        "token", token
    ).execute()


async def find_active_group_linking(
    setup_code: str,
) -> dict[str, Any] | None:
    """Look up an unclaimed group_linking row for /linkfamily validation."""
    client = await get_client()
    resp = (
        await client.table("pending_tokens")
        .select("*")
        .eq("setup_code", setup_code)
        .eq("purpose", "group_linking")
        .eq("status", "pending_confirm")
        .gte("expires_at", datetime.now(timezone.utc).isoformat())
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


async def confirm_group_linking(setup_code: str) -> None:
    client = await get_client()
    await client.table("pending_tokens").update(
        {
            "status": "confirmed",
            "consumed_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("setup_code", setup_code).eq("purpose", "group_linking").execute()
