# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

The repo is **design-only** — no code, no build system, no tests. The source of truth is [plan.md](plan.md), a 12-section build plan for a 5-day hackathon. Before making non-trivial changes or starting implementation, read `plan.md` end-to-end — it has the product, architecture, data model, prompts, scheduler, bot commands, and scope decisions.

[archive/second-shift.md](archive/second-shift.md) is the *original* spec we iterated from. It has pitch-strategy content (judge alignment, risks, market context, roadmap, pitch deck outline) that didn't port to `plan.md` but remains useful for pitch prep. It is **stale on feature-level content** — do not treat it as authoritative for the build.

When the first code lands, extend this file with the actual build / test / lint commands. Do not invent commands before they exist.

## Product in one line

**"AI care"** — an agentic caregiver-ops product for the SG sandwich generation. **The user is the adult child and their siblings, not the elderly parent.** Every feature decision flows from that reframe.

The name plays on the Mandarin homophone `AI` ≈ 爱 (ài, love) — reads as both *"AI for care"* and *"love care"* to a Mandarin ear; mirrors the code-switching the product is built on.

## Architecture

Three surfaces, one agent backbone:

- **Parent surface — Aunty May** (voice persona). Telegram voice messages only. Mandarin + English for MVP.
- **Family group surface** — shared Telegram group with siblings + spouse. Agent auto-posts events, @-mentions the on-duty person, attaches canned nudge templates + inline buttons. No persona — plain ops.
- **GP output** — one-page briefing PDF + QR, generated before each polyclinic visit. An artifact, not a feed.

### Pipeline (see [plan.md §5](plan.md))

Multimodal ingest → STT → Classify + extract → Pattern detection → Decide + plan → Act (voice reply / group post / briefing compile).

All reasoning happens on **text**. Voice is the user-facing I/O boundary — ElevenLabs wraps around the OpenAI text LLM at both ends. The LLM never sees or generates audio directly.

### Tech stack (see [plan.md §6](plan.md))

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI |
| LLM | OpenAI GPT-4o (dialogue / decide / briefing) + GPT-4o-mini (classify / fast paths) |
| STT + TTS | ElevenLabs — Scribe (STT) + Multilingual v2 (TTS), single vendor |
| Messaging | Telegram Bot API (`sendVoice` out, `voice` handler in) |
| DB | Supabase (Postgres + RLS) |
| Scheduling | APScheduler with SQLAlchemy job store (Postgres-backed) |
| Frontend | None — all UX lives in Telegram |
| Auth | Telegram user IDs + Supabase RLS scoped by `family_id` |

### Integration reality

- **Actually wired in MVP:** Telegram bot (both surfaces), end-to-end Aunty May voice loop, on-duty rotation, nudge counter + weekly digest, GP briefing PDF generation, `.ics` upload + appointment reminders
- **Explicitly out of MVP scope (don't reintroduce):** bill payment execution, appointment booking via API, signed receipts feed (E2), MERaLiON STT, Next.js frontend, MCP servers, separate auth layer (Clerk/Supabase Auth)

Out-of-scope items were cut after scope + API-constraint analysis — not oversights.

## Non-obvious constraints that must shape any code

These are the guardrails in [plan.md §3](plan.md). Violating them is a bug, not a style preference.

1. **Clinical line is hard.** Track *confirmations*, never *compliance*. Surface patterns, never interpret them. Aunty May never gives medical advice — not even *"drink more water"* or wellness claims. When medical topics arise, default response is the Asian-polite deferral script: *"I'm not your doctor, Auntie. Let me note this down for your next polyclinic visit, and I'll tell {caregiver_name} so she can bring it up with Dr {gp_name}."* Agent logs + pings on-duty sibling; never calls the doctor.

2. **Disclosure on demand, no impersonation.** If anyone asks *"Are you a real person?"*, agent says so immediately. Never pretend otherwise. Never emulate a specific real person (late spouse, estranged child).

3. **Agent behaviour by action type** (see [plan.md §4](plan.md)):
   - Routine (reminders, logs, digests) → auto-act
   - Sensitive messages (clinical- or grief-adjacent) → optional family review before send
   - Clinical / heavy topics raised by parent → never engage; deferral script + log + @-ping on-duty sibling
   - Agent **never** acts on external systems (no payments, no bookings) — only information actions

4. **Surface visibility is asymmetric.** Parent sees only her private Aunty May voice thread; her voice replies stay private. Family group sees events + outcomes, not parent's voice content. GP sees only the briefing PDF at the visit. Never leak content across surfaces.

5. **Persona is for the parent only.** Aunty May (warm, named, voice) in the parent DM. Family group = first-name basis, no persona, templated posts. GP briefing = clinical/compressed. Don't add a persona to surfaces that don't have one.

6. **MVP language scope is Mandarin + English only.** Don't scaffold Hokkien / Malay / Tamil — phase-2 roadmap.

7. **Transparency over advocacy.** The product is built gender-neutral. The "caregiver load disproportionately falls on women" reality is named by the *data the product generates*, not by the product's branding or copy. Don't bake gendered language into UI or prompts.

## Scope discipline

The demo is **one 60-second scene** (see [plan.md §7](plan.md)): morning-med voice reminder → confirmation miss → on-duty @-mention with drafted nudge → handoff via ✓ Sent tap → Aunty May check-back → resolution → flash to Friday weekly digest showing the nudge-counter disparity. When asked to add a feature, check whether it serves that scene. If not, it belongs on the roadmap slide.
