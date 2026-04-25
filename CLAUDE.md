# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

MVP is **built and running**. The product spec lives in [plan.md](plan.md) (12 sections — product, data model, prompts, scheduler, scope). For setup + run instructions, see [README.md](README.md).

[archive/second-shift.md](archive/second-shift.md) is the *original* spec. Pitch-strategy content (judge alignment, risks, market context) only — **stale on feature-level content**, do not treat as authoritative.

## Commands

```bash
# Run the bot + admin dashboard locally (requires .env + cloudflared tunnel running)
uvicorn main:app --reload --port 8000

# Spine smoke test — fires reminder + miss + escalation + check-back without the wall clock
python scripts/fire_demo.py --fast --missed

# Pre-warm TTS cache (run before demo day; cached files survive in cache/audio/)
python scripts/prewarm_audio.py
```

No tests, no linter wired. Demo readiness is verified by running fire_demo + visual check of the admin dashboard at `/admin/<family_id>`.

## Data-model gotchas

- **`dose_instances` is canonical for adherence** ([app/db/doses.py](app/db/doses.py)). Events are the audit log; doses are the lifecycle state (`pending → confirmed | missed_unresolved → missed_resolved`). Never compute adherence by pairing `med_reminder_sent` / `med_missed` / `med_confirmed` events — the dose row already knows the outcome.
- **Table is `medication` (singular)**. Renamed from `medications` post-MVP. The Python module is [app/db/medication.py](app/db/medication.py) and the alias is `medication_repo`.
- **Service-role key bypasses RLS**. Every repo method MUST scope by `family_id` in code. RLS is defense-in-depth, not the actual access control.
- **Scheduler DSN is port 5432 (Session), NOT 6543 (PgBouncer)**. APScheduler's SQLAlchemy job store needs prepared statements, which the pooler doesn't support.

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

- **Actually wired:** Telegram bot (parent DM + family group), end-to-end Aunty May voice/text loop with timing-aware confirmation, on-duty rotation, weekly Friday digest with coverage stats, dose lifecycle tracking, weekly Monday-morning group update (week ahead + adherence + appointments), daily 20:00 parent check-in, GP briefing PDF (one-page, QR), `.ics` upload via the admin dashboard → appointments table → surfaced in the weekly Monday update, web admin dashboard at `/admin/<family_id>` with Home / Medications / Logs / Settings (Settings has the .ics upload + appointment list).
- **Designed but not yet wired:** standalone day-before `appointment_reminder_due` jobs (plan §10) — currently appointments only surface in the Monday weekly update, no per-appointment cron yet. RRULE expansion in `.ics` (single events only).
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
