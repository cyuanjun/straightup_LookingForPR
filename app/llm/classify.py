"""Intent classification via GPT-4o-mini + function calling."""

from __future__ import annotations

import json
from typing import Any

from app.llm.client import get_client
from app.llm.prompts import CLASSIFY_FUNCTION, CLASSIFY_SYSTEM


async def classify(transcript: str, context: str | None = None) -> dict[str, Any]:
    """Return {intent, medication_name?, symptom_text?, question_text?, confidence}."""
    client = get_client()
    user_msg = f"Context (what Aunty May just asked): {context or '(none)'}\nTranscript: {transcript}"
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": CLASSIFY_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        tools=[CLASSIFY_FUNCTION],
        tool_choice={"type": "function", "function": {"name": "classify_intent"}},
        temperature=0.2,
    )
    tool_call = resp.choices[0].message.tool_calls[0]
    return json.loads(tool_call.function.arguments)
