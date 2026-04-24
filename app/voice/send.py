"""Send Aunty May's reply to the parent — voice or text depending on VOICE_DISABLED."""

from __future__ import annotations

from app.config import settings
from app.voice import tts as tts_mod


async def send_to_parent(bot, chat_id: int, text: str) -> None:
    """If voice_disabled: send text. Otherwise TTS → sendVoice (with audio_cache discipline)."""
    if settings.voice_disabled:
        await bot.send_message(chat_id=chat_id, text=text)
        return
    audio = await tts_mod.synthesize(text)
    await bot.send_voice(chat_id=chat_id, voice=audio)
