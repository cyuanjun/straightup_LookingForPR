"""Conversation memory: last-N turn retrieval scoped by family_id + chat_id."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.db import conversations as convo_repo


async def fetch_recent(
    family_id: UUID | str, chat_id: int, n: int = 12
) -> list[dict[str, Any]]:
    return await convo_repo.last_n_turns(family_id, chat_id, n=n)


async def record_turn(
    family_id: UUID | str,
    chat_id: int,
    speaker_role: str,
    text: str,
    speaker_user_id: UUID | str | None = None,
    language_code: str | None = None,
) -> None:
    await convo_repo.insert_turn(
        family_id,
        chat_id,
        speaker_role,
        text,
        speaker_user_id=speaker_user_id,
        language_code=language_code,
    )
