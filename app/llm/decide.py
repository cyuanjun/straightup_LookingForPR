"""Decision step — pick the agent's next action + (maybe) compose Aunty May's reply."""

from __future__ import annotations

import json
from typing import Any

from app.llm.client import get_client
from app.llm.prompts import (
    DECIDE_FUNCTION,
    URGENT_SYMPTOM_SCRIPT,
    decide_system_prompt,
    deferral_script,
)


async def decide(
    intent: dict[str, Any],
    memory_turns: list[dict[str, Any]] | None = None,
    caregiver_name: str = "Sarah",
    gp_name: str | None = None,
    parent_language_hint: str | None = None,
    matched_medication_name: str | None = None,
) -> dict[str, Any]:
    """Return {action, aunty_reply_text?, escalate_to_group, escalate_to_all_caregivers, log_only}.

    Safety-critical rule enforced *after* the LLM call: if intent is urgent_symptom or
    clinical_question, we override the LLM's output with the canonical script text —
    never trust paraphrase on safety-critical paths.
    """
    client = get_client()

    # Assemble memory into chat messages (oldest → newest)
    memory_messages: list[dict[str, str]] = []
    for turn in memory_turns or []:
        role_map = {"parent": "user", "aunty_may": "assistant", "system": "system"}
        memory_messages.append(
            {"role": role_map.get(turn["speaker_role"], "user"), "content": turn["text"]}
        )

    # Translate language code to an explicit description so GPT-4o doesn't guess.
    _lang_map = {
        "zh+en": "Mandarin with English code-switching (Singapore context)",
        "zh": "Mandarin",
        "zh-CN": "Mandarin",
        "zh-TW": "Mandarin",
        "en": "English",
        "en-SG": "Singapore English",
    }
    lang_desc = (
        _lang_map.get(parent_language_hint or "", parent_language_hint)
        or "Mandarin with English code-switching (Singapore context)"
    )

    med_line = (
        f"Matched medication: {matched_medication_name}\n"
        if matched_medication_name
        else ""
    )

    user_msg = (
        f"Classified intent: {json.dumps(intent)}\n"
        f"{med_line}"
        f"Parent's language: {lang_desc}. Reply in this language; never switch to Malay, Tamil, or any other language.\n"
        f"On-duty caregiver name: {caregiver_name}\n"
        f"GP name: {gp_name or 'unknown'}\n"
        "Pick the next action. Vary phrasing from recent turns in memory."
    )

    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": decide_system_prompt()},
            *memory_messages,
            {"role": "user", "content": user_msg},
        ],
        tools=[DECIDE_FUNCTION],
        tool_choice={"type": "function", "function": {"name": "decide_action"}},
        temperature=0.8,  # warm-conversational variance; safety scripts are hard-coded anyway
    )
    tool_call = resp.choices[0].message.tool_calls[0]
    result: dict[str, Any] = json.loads(tool_call.function.arguments)

    # Safety override: force canonical scripts on the two non-negotiable paths
    if intent.get("intent") == "urgent_symptom":
        result["action"] = "urgent_script"
        result["aunty_reply_text"] = URGENT_SYMPTOM_SCRIPT
        result["escalate_to_all_caregivers"] = True
        result["log_only"] = False
    elif intent.get("intent") == "clinical_question":
        result["action"] = "deferral_script"
        result["aunty_reply_text"] = deferral_script(caregiver_name, gp_name)
        result["escalate_to_group"] = True

    return result
