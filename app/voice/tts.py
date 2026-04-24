"""Text-to-speech (ElevenLabs Multilingual v2) with local audio_cache.

Cache policy:
  - Key = sha256(text || voice_id); stored in audio_cache table + ./cache/audio/<hash>.ogg
  - On hit: verify file exists on disk before returning (handle DB/file desync)
  - On miss: call ElevenLabs, write .ogg, upsert cache row
  - Output format: opus_48000_32 so Telegram sendVoice renders a voice waveform
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from elevenlabs.client import AsyncElevenLabs

from app.config import settings
from app.db import audio_cache as audio_cache_repo

_client: AsyncElevenLabs | None = None


def _get_client() -> AsyncElevenLabs:
    global _client
    if _client is None:
        _client = AsyncElevenLabs(api_key=settings.elevenlabs_api_key)
    return _client


def _hash_key(text: str, voice_id: str) -> str:
    return hashlib.sha256(f"{text}|{voice_id}".encode("utf-8")).hexdigest()


def _cache_path(text_hash: str) -> Path:
    return settings.audio_cache_dir / f"{text_hash}.ogg"


async def synthesize(text: str, voice_id: str | None = None) -> bytes:
    """Returns OGG/Opus audio bytes suitable for Telegram sendVoice. Cache-first."""
    vid = voice_id or settings.aunty_may_voice_id
    text_hash = _hash_key(text, vid)
    local_path = _cache_path(text_hash)

    # Cache hit path: DB row exists AND file still on disk
    row = await audio_cache_repo.get(text_hash)
    if row and local_path.exists():
        return local_path.read_bytes()

    # Stale row: file missing on disk; drop it and regenerate
    if row and not local_path.exists():
        await audio_cache_repo.delete(text_hash)

    # Regenerate via ElevenLabs
    client = _get_client()
    audio_bytes = b""
    async for chunk in client.text_to_speech.convert(
        text=text,
        voice_id=vid,
        model_id="eleven_multilingual_v2",
        output_format="opus_48000_32",
    ):
        audio_bytes += chunk

    # Write to disk + upsert cache row
    settings.audio_cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = local_path.with_suffix(".ogg.tmp")
    tmp_path.write_bytes(audio_bytes)
    tmp_path.rename(local_path)
    await audio_cache_repo.upsert(text_hash, vid, str(local_path))

    return audio_bytes


async def synthesize_to_file(text: str, voice_id: str | None = None) -> Path:
    """Same as synthesize() but returns the cached file path (for Telegram file-id uploads)."""
    await synthesize(text, voice_id)
    vid = voice_id or settings.aunty_may_voice_id
    return _cache_path(_hash_key(text, vid))
