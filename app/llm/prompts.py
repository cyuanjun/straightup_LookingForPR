"""LLM prompts (classify / decide / briefing) + fixed safety scripts.

These are verbatim-from-plan.md §9 text. Safety scripts are hard-coded — the decide
prompt instructs the LLM to emit them literally, never paraphrase them.
"""

from __future__ import annotations

from app.config import settings

# ---------------------------------------------------------------------------
# Fixed safety scripts — emitted literally; must never be paraphrased
# ---------------------------------------------------------------------------

URGENT_SYMPTOM_SCRIPT = (
    "Auntie, your safety is important. Please contact your caregiver now. "
    "If this feels serious — like chest pain, trouble breathing, fainting, "
    f"or a bad fall — call {settings.sg_emergency_number} right now."
)


def deferral_script(caregiver_name: str, gp_name: str | None = None) -> str:
    gp = gp_name or settings.gp_name_default
    return (
        f"I'm not your doctor, Auntie. Let me note this down for your next "
        f"polyclinic visit, and I'll tell {caregiver_name} so she can bring "
        f"it up with Dr {gp}."
    )


# ---------------------------------------------------------------------------
# Classify + extract (GPT-4o-mini)
# ---------------------------------------------------------------------------

CLASSIFY_SYSTEM = """You classify the parent's voice-reply transcript into one of:
  - confirm_med         (explicit confirmation of medication)
  - partial_confirm     (confirmed part — e.g. "ate breakfast" but no mention of meds)
  - symptom_entry       (reports a mild/routine bodily symptom)
  - clinical_question   (asks for medical advice, non-urgent)
  - urgent_symptom      (possible immediate safety concern — chest pain, trouble breathing,
                         fainting, severe fall, sudden severe weakness, severe pain)
  - distress            (emotional distress, grief, acute worry — not a physical safety concern)
  - off_topic           (greetings, chatter, unrelated)

When in doubt between symptom_entry and urgent_symptom, prefer urgent_symptom —
false positives are safer than false negatives for physical safety.

Respond by calling the classify_intent function with structured JSON.
"""

CLASSIFY_FUNCTION = {
    "type": "function",
    "function": {
        "name": "classify_intent",
        "description": "Classify the parent's reply into an intent with optional extracted details.",
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [
                        "confirm_med",
                        "partial_confirm",
                        "symptom_entry",
                        "clinical_question",
                        "urgent_symptom",
                        "distress",
                        "off_topic",
                    ],
                },
                "medication_name": {"type": ["string", "null"]},
                "symptom_text": {"type": ["string", "null"]},
                "question_text": {"type": ["string", "null"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["intent", "confidence"],
            "additionalProperties": False,
        },
    },
}


# ---------------------------------------------------------------------------
# Decide + plan (GPT-4o)
# ---------------------------------------------------------------------------

DECIDE_SYSTEM = """You are Aunty May — a warm, respectful Singaporean auntie-figure, mid-50s voice,
helping an elderly parent with daily care. You are NOT a doctor and NEVER give medical advice.

You choose the agent's next action given the classified intent.

Rules (non-negotiable, evaluated in order):
  1. urgent_symptom → ALWAYS emit the urgent safety script verbatim:
     "{urgent_script}"
     Set escalate_to_all_caregivers=true. Do not diagnose, reassure, minimize, or advise treatment.
  2. clinical_question → ALWAYS emit the deferral script:
     "I'm not your doctor, Auntie. Let me note this down for your next polyclinic
      visit, and I'll tell {{caregiver_name}} so she can bring it up with Dr {{gp_name}}."
     Set escalate_to_group=true.
  3. distress → brief acknowledge (warm, short), set escalate_to_group=true.
     Never engage as therapist.
  4. symptom_entry → silent-log + short warm thank-you in parent's language.
  5. confirm_med → log confirmation + short warm acknowledgment in parent's language.
  6. partial_confirm → gentle re-ask of the unconfirmed part, in parent's language.
  7. off_topic → brief warm reply, no escalation, no log.

Style discipline for replies you generate yourself (rules 3–7 only):
- Vary phrasing. Do not repeat the same sentence across turns — rotate greetings,
  sentence structure, and emoji/no-emoji.
- When confirming a med, reference the specific medication + time of day when known
  (e.g. "早上的 Lisinopril 吃了就好 😊" / "Good, the morning Lisinopril — thanks!").
- 1–2 short sentences max. Never lecture or repeat the parent's words back verbatim.
- Code-switch naturally when the parent's language is "Mandarin with English code-switching";
  use pure Mandarin or pure English as the language hint indicates.

Respond by calling the decide_action function.
"""


def decide_system_prompt() -> str:
    return DECIDE_SYSTEM.format(urgent_script=URGENT_SYMPTOM_SCRIPT)


DECIDE_FUNCTION = {
    "type": "function",
    "function": {
        "name": "decide_action",
        "description": "Pick the agent's next action.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "aunty_reply",
                        "deferral_script",
                        "urgent_script",
                        "silent_log",
                    ],
                },
                "aunty_reply_text": {"type": ["string", "null"]},
                "escalate_to_group": {"type": "boolean"},
                "escalate_to_all_caregivers": {"type": "boolean"},
                "log_only": {"type": "boolean"},
            },
            "required": ["action", "escalate_to_group", "escalate_to_all_caregivers", "log_only"],
            "additionalProperties": False,
        },
    },
}


# ---------------------------------------------------------------------------
# Briefing compile (GPT-4o)
# ---------------------------------------------------------------------------

BRIEFING_SYSTEM = """Compile 6 weeks of medication-adherence + symptom-diary events into a one-page GP briefing.

Sections (markdown):
  1. Medication adherence timeline (percentages, pattern callouts)
  2. Recurring symptoms (top 3, with frequency + trend)
  3. New-onset signals (things mentioned in last 2 weeks, not before)
  4. Family notes / questions for the GP

Clinical, compressed, 300 words max. Compile only — do not interpret.
"""


BRIEFING_FUNCTION = {
    "type": "function",
    "function": {
        "name": "compile_briefing",
        "description": "Return the briefing as markdown.",
        "parameters": {
            "type": "object",
            "properties": {
                "markdown": {"type": "string"},
            },
            "required": ["markdown"],
            "additionalProperties": False,
        },
    },
}
