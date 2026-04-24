"""Compile 6 weeks of events into a GP briefing (markdown) via GPT-4o.

Plan §9 briefing prompt: sections = adherence timeline, recurring symptoms,
new-onset signals, family notes. Clinical, 300 words max. We compile; the GP interprets.
"""

from __future__ import annotations

import json
from typing import Any

from app.db import events as events_repo
from app.db import medications as medications_repo
from app.llm.client import get_client
from app.llm.prompts import BRIEFING_FUNCTION, BRIEFING_SYSTEM


def _format_events_for_llm(events: list[dict]) -> list[dict]:
    """Strip events to just what the briefing prompt needs — keeps token count down."""
    out = []
    for e in events:
        out.append(
            {
                "type": e["type"],
                "at": e["created_at"],
                "payload": e.get("payload") or {},
            }
        )
    return out


async def compile_briefing(family_id: str, window_days: int = 42) -> str:
    """Return markdown for the briefing body. Raises if the LLM call fails."""
    events = await events_repo.recent_for_briefing(family_id, window_days=window_days)
    meds = await medications_repo.list_active(family_id)

    events_compact = _format_events_for_llm(events)
    meds_compact = [
        {"id": m["id"], "name": m["name"], "dose": m["dose"], "times": [str(t) for t in (m.get("times") or [])]}
        for m in meds
    ]

    context_blob: dict[str, Any] = {
        "window_days": window_days,
        "active_medications": meds_compact,
        "events": events_compact,
    }

    client = get_client()
    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": BRIEFING_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Compile a one-page GP briefing from this family's data. "
                    f"Stay within 300 words. JSON context:\n{json.dumps(context_blob, default=str)}"
                ),
            },
        ],
        tools=[BRIEFING_FUNCTION],
        tool_choice={"type": "function", "function": {"name": "compile_briefing"}},
        temperature=0.2,
    )
    tool_call = resp.choices[0].message.tool_calls[0]
    result = json.loads(tool_call.function.arguments)
    return result["markdown"]
