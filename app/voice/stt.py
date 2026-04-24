"""Speech-to-text via ElevenLabs Scribe. Handles Mandarin + English code-switch natively."""

from __future__ import annotations

from io import BytesIO

from elevenlabs.client import AsyncElevenLabs

from app.config import settings

_client: AsyncElevenLabs | None = None


def _get_client() -> AsyncElevenLabs:
    global _client
    if _client is None:
        _client = AsyncElevenLabs(api_key=settings.elevenlabs_api_key)
    return _client


async def transcribe(audio_bytes: bytes) -> dict[str, str | None]:
    """Returns {text, language_code}. Language auto-detected — don't force it."""
    client = _get_client()
    result = await client.speech_to_text.convert(
        file=BytesIO(audio_bytes),
        model_id="scribe_v1",
    )
    # Scribe returns: {"text": str, "language_code": str, ...}
    return {
        "text": getattr(result, "text", None) or result.get("text", "") if isinstance(result, dict) else result.text,
        "language_code": (
            getattr(result, "language_code", None)
            if not isinstance(result, dict)
            else result.get("language_code")
        ),
    }
