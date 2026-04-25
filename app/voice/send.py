"""Send Aunty May's reply to the parent — voice or text depending on VOICE_DISABLED.

After the message lands, the turn is logged to `conversations` so the briefing,
Logs page, and last-N memory retrieval all see agent-initiated messages too —
not just interactive replies. Pass family_id to enable that side-effect (jobs +
handlers do; pre-onboarding flows can omit it).
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.config import settings
from app.voice import tts as tts_mod

log = logging.getLogger(__name__)


async def send_to_parent(
    bot,
    chat_id: int,
    text: str,
    *,
    family_id: UUID | str | None = None,
    language_code: str | None = None,
) -> None:
    """Voice mode: TTS → sendVoice. On any TTS error, fall back to plain text so the
    parent still gets the message (degraded gracefully — quota / 5xx / library-voice
    permission errors don't kill the whole reminder flow).

    If `family_id` is passed, the outgoing turn is recorded as `aunty_may` in the
    conversations table for memory retrieval + log timeline + briefing context.
    """
    if settings.voice_disabled:
        await bot.send_message(chat_id=chat_id, text=text)
    else:
        try:
            audio = await tts_mod.synthesize(text)
            await bot.send_voice(chat_id=chat_id, voice=audio)
        except Exception as exc:
            log.warning("TTS failed (%s) — falling back to text", type(exc).__name__)
            await bot.send_message(chat_id=chat_id, text=text)

    if family_id is not None:
        # Lazy import to avoid a circular dependency at module load time.
        from app.llm import memory as memory_mod

        try:
            await memory_mod.record_turn(
                family_id,
                chat_id,
                "aunty_may",
                text,
                language_code=language_code,
            )
        except Exception:
            log.exception("record_turn failed — message sent but not logged")
