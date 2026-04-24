"""Pre-warm the TTS audio cache before demo day so stage has zero live ElevenLabs calls.

Usage: python scripts/prewarm_audio.py
"""

from __future__ import annotations

import asyncio

from app.voice import tts as tts_mod

DEMO_PHRASES = [
    # Morning reminder (Mandarin + English mix)
    "早安啊 Auntie, 吃了早餐和Lisinopril吗?",
    # Gentle follow-up when parent confirms breakfast but not meds
    "好, 记得吃药 hor, 我等下再 check.",
    # Check-back
    "Auntie, Lisinopril 吃了吗?",
    # Parent-acknowledgement ack
    "好的, 记录下了. 谢谢 Auntie.",
    # English variants
    "Good morning Auntie, have you had your breakfast and Lisinopril?",
    "Auntie, have you taken your Lisinopril?",
    # Intro voice message
    "Hello Auntie — I'm Aunty May, an AI. I'll gently remind you about your medicine and check how you're feeling.",
    # Safety script (urgent)
    (
        "Auntie, your safety is important. Please contact your caregiver now. "
        "If this feels serious — like chest pain, trouble breathing, fainting, "
        "or a bad fall — call 995 right now."
    ),
]


async def main() -> None:
    print(f"Pre-warming {len(DEMO_PHRASES)} phrases…")
    for i, phrase in enumerate(DEMO_PHRASES, 1):
        print(f"  [{i}/{len(DEMO_PHRASES)}] {phrase[:50]}…")
        await tts_mod.synthesize(phrase)
    print("Done. All cached in ./cache/audio/ and audio_cache table.")


if __name__ == "__main__":
    asyncio.run(main())
