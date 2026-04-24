# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

This repo is **design-only** at the moment — no code, no build system, no tests. The single substantive file is [second-shift.md](second-shift.md), a detailed product + architecture spec for a 5-day hackathon build (submission Fri 25 Apr 12:00, pitch 13:00). Before making non-trivial changes or starting implementation, read that document — it is the source of truth for scope, persona, and architecture decisions.

When the first code lands, extend this file with the actual build / test / lint commands for whatever stack gets wired up first. Do not invent commands before they exist.

## Product in one line

"Second Shift" — an agentic caregiver-ops product for the SG sandwich generation. **The user is the adult child and their siblings, not the elderly parent.** Every feature decision flows from that reframe. See [second-shift.md](second-shift.md#the-product).

## Architecture (planned)

Four user-facing surfaces, one agent backbone. Not four separate products — all share ingest → classify → pattern-reason → plan → act → log. See the pipeline diagram at [second-shift.md](second-shift.md#ai-architecture-the-57-step-pipeline).

- **Aunty May voice persona** — the parent-facing surface. Telegram voice messages only (not text, not phone calls). Mandarin + English for MVP; Hokkien/Malay/Tamil are phase-2.
- **Family group** — Telegram group chat with siblings + spouse. Agent posts events, @-mentions the on-duty person, drafts nudges in the sender's voice. No separate persona — plain-text ops.
- **GP briefing** — structured PDF generated from the last 6 weeks of adherence + symptom data; shared only at polyclinic visits.
- **Receipts feed** — signed (ed25519 or C2PA) ledger of every action the agent took. Siblings can audit.

### Planned tech stack

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI |
| Dialogue LLM | GPT-5 (primary), GPT-4o-mini (routing/classification) |
| STT | MERaLiON-AudioLLM (primary, SG-tuned), Whisper-large-v3 (fallback) |
| TTS | ElevenLabs Multilingual v2 |
| Messaging | Telegram Bot API (`sendVoice` + voice handler) — **not** WhatsApp (provisioning > 1 week) |
| DB | Supabase (Postgres + RLS) |
| Frontend | Next.js + Tailwind (family-group view only; parent view is inside Telegram) |
| Tool use | OpenAI function calling + MCP for external integrations |

Full rationale for each pick: [second-shift.md](second-shift.md#tech-stack-choices-for-a-5-day-build).

### Integration reality (important for scoping work)

Per the spec, only these are **actually wired** in the MVP:

- Telegram bot (both surfaces — parent voice exchange and family group)
- Signed receipts feed
- End-to-end Aunty May voice loop (Telegram voice in → MERaLiON → GPT-5 → ElevenLabs → Telegram voice out)

These are **mocked with real UI**: polyclinic appointment booking, bill ingestion from email/SMS, bill payment flow.

These are **slide-only**: deeper polyclinic integration, insurance, banking APIs, fleet management.

Don't build real integrations for the slide-only items. Don't mock the live demo moment (the voice loop).

## Non-obvious constraints that must shape any code

These come straight from the spec's guardrails section and will be probed by the judging panel. Any implementation that violates them is a bug, not a stylistic preference.

1. **Clinical line is hard.** The product tracks *confirmations*, never *compliance*. It surfaces patterns, never interprets them. Aunty May never gives medical advice — not even "drink more water." When medical topics arise, the scripted response is: *"I'm not your doctor, Auntie. Let me note this down for your next polyclinic visit, and I'll tell Sarah so she can bring it up with Dr Tan."* The agent logs + pings the on-duty sibling; it does **not** call the doctor.

2. **Disclosure on demand, no impersonation.** If anyone asks "Are you a real person?", the agent must say so immediately. Never accept requests to pretend otherwise. Never emulate a specific real person (e.g., a late spouse).

3. **Blast-radius-gated autonomy.** Low (routine log/reminder) → auto-act. Medium (message to parent, payment < S$200) → draft for family approval. High (large payment, medical decision) → no action without explicit group approval. Clinical → never acts, always routes. See the table at [second-shift.md](second-shift.md#escalation-thresholds).

4. **Surface visibility is not symmetric.** Mdm Lim sees only her private Aunty May thread; her voice replies stay private. The family group sees only outcomes/summaries, not Mdm Lim's actual voice content. The GP sees only the briefing PDF. Don't leak content across surfaces in any code path.

5. **Persona is for the parent only.** Aunty May (warm, named, voice). Family group = plain ops, first-name basis, no persona. GP briefing = clinical/compressed. Don't add a persona to surfaces that don't have one.

6. **MVP language scope is Mandarin + English only.** Don't scaffold Hokkien/Malay/Tamil in the 5-day window — they're phase-2 roadmap.

## Scope discipline

The spec is emphatic that the demo is **one 60-second scene** showing all four surfaces firing for one family (see [hero demo script](second-shift.md#hero-demo-script-60-seconds)). When asked to add a feature, check whether it serves that scene. If not, it belongs on the roadmap slide, not in the build.

Specifically **out of MVP scope** (removed deliberately, don't reintroduce): polypharmacy / drug-interaction logic, CPF / CareShield / MediSave integrations, multi-parent families, predictive clinical signals, hired-caregiver marketplace handoff.
