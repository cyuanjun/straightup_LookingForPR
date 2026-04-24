# Plan

## 1. The product

### AI care

**Wordplay:** `AI` ≈ 爱 (ài, love) in Mandarin. The name reads as both *"AI for care"* and *"love care"* in Mandarin, mirrorsing the code-switching between english and mother tongue that the product is built on.

**Pitch:** "AI care" redistributes the invisible caregiver work dual-income families do — across siblings, spouses, and the agent — so one person isn't carrying it alone. It keeps ageing parents safe at home and turns the 2-minute polyclinic consult into a data-rich briefing.

**Target user & stakeholders:**

- **Primary user:**
  - **Sandwich-generation adult child**
    - Age 35–55, married, both partners working full-time
    - One or two school-age kids at home
    - Ageing parent(s), at least one starting to decline — forgetting meds, missing bills, needing polyclinic visits, slowly becoming unsafe to leave alone
    - The load almost always defaults to one person, even when others could help
- **Secondary users:**
  - **Spouse and siblings sharing the load**
    - The work is often invisible to them until the product surfaces it
- **Other stakeholders:**
  - **Elderly parent**
    - Interacts via voice message
  - **Family GP / polyclinic**
    - Receives the briefing PDF at visits

**Core thesis:** Singapore is ageing into a crisis where adult children are fewer, more likely to be dual-income, more likely to have their own kids at home, and more likely to split caregiving unequally across the family. Existing eldercare tools monitor the parent's fall risk. We redistribute the caregiver work itself — across siblings, spouses, and the agent — so one person isn't carrying it alone on top of their job and their own family.

**Our stance — transparency, then fairness:**

The goal is to surface what actually goes on behind the scenes of caregiving: who's been on duty, what's been handled, who responded, who approved. Invisible labor can't be redistributed until it's seen.

The product is built gender-neutral. We acknowledge up front that the caregiving load in SG families falls disproportionately on women — usually a daughter — and we expect our own data to confirm it. That reality is the *reason* the transparency layer exists; it is not the product's front door.

We don't want to tell families "one of you is doing more." We want to show them, with data, so the conversation about fairness can actually happen.

## 2. What it covers

### Onboarding

- Family adds the bot to a shared Telegram group (bot privacy-mode off so it can read messages — no admin rights needed)
- Family configures via the bot:
  - Medication schedule (name, dose, times)
  - Daily symptom diary check-in time
  - On-duty rotation (days-of-week per family member)
  - Parent's Telegram handle + preferred language
- Aunty May sends the parent her introduction voice message (warm, brief, explicit AI disclosure)

### Medical workflow *(A4, D1, D3)*

Clinical *workflow*, not clinical *decision* — we surface signals; the GP interprets.

- **Medication reminders (voice):** Aunty May voice-messages the parent at each scheduled time. Parent voice-replies; agent transcribes via ElevenLabs Scribe. Unconfirmed → follow-up voice reminder; after N misses → escalate to family coordination. Delays logged for the GP briefing.
- **Daily symptom voice diary:** Aunty May checks in at the configured time (*"今天身体怎么样?"*). Parent voice-replies in Mandarin / English; Scribe transcribes + tags; logged daily.

### Family coordination *(C4, D4)*

Makes the invisible caregiver labor visible and routable.

- **On-duty rotation:** family picks the rotation at onboarding; when the parent misses a reminder, agent @-mentions today's on-duty person in the family group with a pre-drafted nudge. On-duty person copies it, sends to the parent privately, taps ✓ on the group post.
- **Nudge + response counter:** every @-mention, response, and ✓ attributed to a person. Weekly digest posts the counts to the family group — the C4/AIF wedge made concrete.

### Appointment manager *(A4, D3)*

- Family uploads HealthHub's `.ics` export directly to the bot in Telegram; bot parses and stores appointments locally
- Day-before reminders: voice to parent, text to family group
- Re-upload `.ics` when appointments change
- *(Phase 2: auto-sync via public Google Calendar `.ics` URL; transport coordination)*

### GP briefing *(D1, D3)*

- Before each polyclinic visit, agent generates a one-page PDF from the last 6 weeks: medication adherence timeline, symptom recurrences, new-onset signals, family notes
- QR code version the GP scans at the visit — no login, no continuous feed
- Designed for a 30-second read within the 2-minute consult

## 3. Persona design

### Core principle

The product is a **caretaker-ops persona**, not a companion-AI-for-lonely-elderly. Warmth serves operations, not emotional dependency — keeps us clear of Replika / Pi-for-elderly territory, where attachment becomes the revenue model.

### Personas per stakeholder

| Stakeholder | Persona | Tone | Language | Surface |
|---|---|---|---|---|
| Elderly parent | **"Aunty May"** — warm, named companion | Warm, respectful, patient; never clinical | Mandarin + English for MVP (Hokkien / Malay / Tamil phase 2) | Telegram voice messages |
| Family group | No persona — first-name basis, plain notifications | Tactical, concise | Their preference | Shared Telegram group with @-mentions |
| Family GP / polyclinic | No persona — structured briefing doc | Clinical, compressed | Standard medical English | PDF / QR at the visit |

### Guardrails (non-negotiable)

1. **Disclosure on demand.** If anyone asks *"Are you a real person?"*, the agent says so immediately. Never accepts requests to pretend otherwise.
2. **Never impersonate a licensed professional.** Aunty May is never a nurse. She never gives medical advice (even obvious ones like *"drink more water"*) or makes wellness claims.
3. **Asian-polite medical deferral script.** When medical topics arise, default response: *"I'm not your doctor, Auntie. Let me note this down for your next polyclinic visit, and I'll tell Sarah so she can bring it up with Dr Tan."* Redirects by action, names family + authority, preserves the helper role.
4. **Explicit disclosure at onboarding.** Parent consents to the AI relationship at setup; no deception by omission.
5. **No exploitation of attachment.** If the parent bonds with Aunty May, service obligation grows, not shrinks. Shutdown = graceful 30-day transition, never abrupt.
6. **Persona stability.** Same voice, personality, memory every time. Never emulates a specific real person (late spouse, estranged child), even if asked.
7. **Respect the user's exit.** Never persists when the parent wants to end a conversation. Never escalates urgency to manipulate compliance.
8. **Heavy topics route to humans.** Grief, end-of-life, deep distress — Aunty May acknowledges briefly and routes to a sibling or GP. Does not engage as a therapist.

### What Aunty May does

- Greet the parent by name, remember prior conversations
- Deliver medication reminders warmly; check adherence
- Conduct the daily symptom voice diary check-in
- Relay messages from family (e.g., *"Sarah says she'll come Saturday"*)
- Remind about upcoming polyclinic appointments (from the uploaded `.ics`)
- Notice distress tone and escalate to the on-duty sibling

### What Aunty May does NOT do

- Give medical advice or make wellness claims
- Attempt to contact the GP directly
- Execute payments or book appointments
- Impersonate any real person
- Keep the parent talking past her wish to end

### Disclosure UX — demo moment

A 5-second beat to include explicitly in the demo:

> **Mdm Lim:** *"Aunty May, you are a real person right?"*
>
> **Aunty May:** *"No, Mdm Lim, I'm an AI — I help keep you safe and in touch with Sarah. Real people still help you: Dr Tan, Sarah, your neighbour Mrs Koh. Is there anything you want me to clear up?"*

### Cultural casting (SG-specific)

- **Name:** "Aunty May" is a working placeholder. Match family background — Chinese-dialect: *Ah Yi* (阿姨); Malay: *Mak Cik* / *Kak*. Avoid names already in the family.
- **Voice:** warm alto, mid-50s register, SG-English with local-language fluency. Reassuring, not saccharine.
- **Age signal:** "Aunty" positions the persona as *slightly younger* than the parent — helper, not peer, not a child. Matters in Asian hierarchical norms.
- **Never use:** Western-sounding name, young voice, doctor/nurse title, male voice.
- **Voice ID:** pick a specific ElevenLabs `voice_id` from their library matching the above criteria; store as `AUNTY_MAY_VOICE_ID` config constant. Decide before Day 1 of the build.

## 4. How it works (day-to-day)

### One-time setup (10–15 min if parent has Telegram; 20–30 min if installing)

**Phase 1 — Manual pre-setup (primary caregiver, ~5 min)**

- Find the bot on Telegram (e.g., `@aicare_bot`), tap **Start** → bot welcomes in DM
- Create or pick an existing family Telegram group; add the bot as a member; ensure everyone sharing care is in it
- Ensure the parent has Telegram installed on their phone (often done during a home visit)

**Phase 2 — Parent handshake (deep-link + one-time token)**

⚠️ Two Telegram constraints combined: (a) a bot cannot DM a user who hasn't messaged it first, and (b) the bot needs to *link* the parent's DM to the correct family — otherwise "a DM with Parent X" has no family context.

Mechanism:

1. `/setup` generates a random one-time token (e.g., `fam_abc123xyz`) mapped server-side to this family's config
2. Bot returns a deep link: `t.me/aicare_bot?start=fam_abc123xyz`
3. Caregiver shares the link with the parent — tap it on the parent's phone during a home visit (~10s), or send via WhatsApp / SMS
4. Parent taps the link → Telegram opens the bot and sends `/start fam_abc123xyz`
5. Bot looks up the token, records `parent_telegram_id = X` against this family, consumes the token
6. Bot replies with a confirmation: *"Hi! Are you Mdm Lim? Your family added me to help you with daily care. Reply yes/no."* If no → unlink, reissue the token

Token discipline:

- Cryptographically random; single-use (consumed on first `/start`); 24-hour expiry
- Subsequent `/start` attempts with a consumed token are rejected
- Once linked, Aunty May can DM the parent at will

**Phase 3 — Configuration (bot-led `/setup`, ~5 min)**

In DM with the primary caregiver, the bot walks through:

- **Parent's info** — name, Telegram handle (confirmed from Phase 2), preferred language (Mandarin + English / English only)
- **Medications** — for each: name, dose, times (multiple supported)
- **Symptom-diary check-in time** — default 20:00
- **On-duty rotation** — bot auto-lists family group members; caregiver maps them to days of the week
- **HealthHub `.ics` upload** — caregiver exports from HealthHub, forwards the file to the bot in DM; bot parses and stores appointments locally
- **Group visibility** — defaults shared; individual opt-in for private surfaces

Caregiver reviews the config summary and `/confirm`.

**Phase 4 — Parent opt-in (AI disclosure moment)**

Aunty May sends the parent her intro voice message in their language — warm, brief, explicit AI disclosure. Three outcomes:

- **Accepts** → bot posts to family group: *"Setup complete. Parent acknowledged."*
- **Confused** → bot reiterates disclosure, invites questions
- **Declines** → bot stops; DMs caregiver with the parent's response; caregiver decides whether to retry or abort

**Phase 5 — Live**

Bot posts to family group: *"Setup complete. Today's on-duty: @Marcus. First medication reminder at 08:45 tomorrow."* Daily cycle (below) begins.

### Daily cycle

1. **Morning medication reminder.** At the scheduled time (e.g. 08:45), Aunty May voice-messages the parent: *"早安啊 Auntie Lim, 吃了早餐和早药吗?"*
2. **Parent voice-replies.** Agent transcribes via ElevenLabs Scribe and parses intent — confirmed / not confirmed / partial.
3. **Confirmation window closes (e.g. +15 min).** If confirmed: silent log. If not: next step.
4. **Agent posts to the family group**, @-mentions today's on-duty person, includes a pre-drafted nudge (*"Ma, 吃药了吗?"*).
5. **On-duty person acts.** Copies the nudge, sends to the parent privately, taps ✓ on the group post. Group then shows *"Marcus sent the nudge at 09:03."*
6. **Aunty May's check-back.** ~20 minutes later, Aunty May follows up with the parent. Resolution (confirmed / still missed) posts to the family group. The parent's actual voice content stays private.
7. **Evening symptom diary.** Aunty May checks in at the configured time (*"今天身体怎么样?"*); parent voice-replies; transcribed and logged.

### Weekly cycle

- **Friday evening digest** posted to the family group: nudge count per person, notable events, upcoming appointments.
- **Before each polyclinic visit:** agent generates the briefing PDF from the last 6 weeks of data, shared with whoever's accompanying the parent.

### Agent behaviour by action type

The agent only ever takes *information* actions — it does not act on external systems (no payments, no bookings).

| Kind of action | Behaviour |
|---|---|
| Routine (scheduled reminder, check-in, log entry, weekly digest) | Auto |
| Sensitive message to parent (grief-adjacent, clinical-adjacent) | Optional family review before Aunty May sends |
| Clinical / heavy topic raised by the parent | Never engages — uses the Asian-polite deferral script, logs for the GP briefing, routes to the on-duty sibling |

### What each surface sees

- **Parent:** only her private Aunty May voice thread. Her voice replies stay between her and Aunty May.
- **Family group:** events, confirmation status, on-duty @-mentions, nudge counter, weekly digest. Does not see the parent's voice content — only outcomes.
- **GP / polyclinic:** only the briefing PDF at the visit. No continuous feed.

## 5. AI architecture

The pipeline where AI is load-bearing at multiple decision points — not a thin LLM wrapper.

### Pipeline

1. **Multimodal ingest** — voice messages (Mandarin + English), text/files from Telegram, `.ics` upload
2. **STT / transcribe** — ElevenLabs Scribe (handles Mandarin + English code-switch natively; MERaLiON-AudioLLM is the phase-2 upgrade for stronger Singlish + local-language depth)
3. **Classify + extract** — LLM parses intent from the transcript: confirmation / symptom / question / clinical topic / distress
4. **Pattern detection** — rolling-window analysis: medication-miss patterns, symptom recurrences, new-onset signals
5. **Decide + plan** — LLM picks one: Aunty May reply (in persona) / deferral script (clinical) / escalate to family / silent log
6. **Act**, one of:
    - **6a. Voice reply** — ElevenLabs Multilingual v2, persona-stable Aunty May voice
    - **6b. Family-group post** — @-mention the on-duty person, canned nudge template attached
    - **6c. GP briefing compile** — LLM structures 6 weeks of data into a one-page PDF + QR

### Decision points (where AI does real work)

| Step | What the model decides |
|---|---|
| STT | Mandarin + English speech handled cleanly; indirect replies preserved for the classifier |
| Classify | Intent extraction from messy transcripts (e.g. *"吃了早餐"* without mentioning meds = partial confirmation) |
| Pattern | Recurrence detection over rolling windows (*"knee pain 5 days in a row"* is pattern, not threshold) |
| Decide | Auto-act vs route vs defer — the blast-radius gate |
| Voice gen | Persona-consistent output across every utterance (ElevenLabs) |
| Briefing | 6 weeks of timestamped data → clinician-scannable one-pager |

### Where human-in-the-loop lives

- Sensitive messages (clinical-adjacent, grief-adjacent) → optional family review before Aunty May sends
- Medical topics raised by the parent → never auto-advise; deferral script + log for GP briefing + @-ping on-duty sibling
- Heavy topics (grief, deep distress) → brief acknowledge, route to sibling or GP
- Agent never acts on external systems — no payments, no bookings

### Conversation memory (decide before build)

Guardrail #6 requires Aunty May to remember prior conversations. Two options:

- **Add a `conversations` table** to the data model — message history per parent-bot thread; retrieve the last N turns into the LLM prompt.
- **Use OpenAI's Assistants API with persistent threads** — built-in memory, less prompt engineering, but locks you into that API shape.

Either works. Pick based on build preference.

## 6. Tech stack

| Layer | Choice | Why |
|---|---|---|
| **Backend** | Python (FastAPI) | Fast to ship agentic workflows; rich LLM + audio ecosystem |
| **LLM — dialogue, classify, decide, briefing** | OpenAI GPT-4o (primary) + GPT-4o-mini (classify + fast paths) | Persona stability + memory for Aunty May; mini for cheap classification / routing |
| **STT + TTS** | ElevenLabs — Scribe (STT) + Multilingual v2 (TTS) | Single vendor for voice I/O; Scribe handles Mandarin + English code-switch; Multilingual v2 gives the warm Aunty May persona; free tier shares 10k credits across both |
| **Messaging + voice transport** | Telegram Bot API (`sendVoice` out, `voice` handler in) | Zero provisioning; async voice matches elderly UX; SEA-familiar |
| **Database** | Supabase (Postgres + RLS) | Family-scoped data with row-level security built in; fast setup |
| **Tool use / structured output** | OpenAI function calling | Forces schema-valid output for classify / decide / briefing generation |
| **Frontend** | *(none for MVP — all UX lives in Telegram)* | Saves a full day of build |
| **Auth** | Telegram user IDs + Supabase RLS by `family_id` | Telegram identity is the auth primitive; no separate login |

### TTS caching discipline

ElevenLabs credits are billed per generation, not per replay. **Cache generated audio** keyed by `(text, voice_id)` hash — the same med reminder *"早安啊 Auntie Lim, 吃了早餐和早药吗?"* costs credits once, not every morning. Pre-generate and cache the full phrase library the night before demo day so nothing hits the API live on stage.

### Attribution

Free tier requires *"Voice by ElevenLabs"* credit on public output. Include on the pitch deck's closing slide.

## 7. Hero demo script (~60 seconds)

One scene that fires every live surface. Sandwich-generation framing.

> **[0:00]** Voiceover: *"This is Mdm Lim, 78, in Toa Payoh. Her daughter Sarah is in Bukit Timah — full-time job in Raffles Place, two kids at primary school. Her brother Marcus works shifts at Changi."*
>
> **[0:08]** Tuesday 8:45 AM. Mdm Lim's Telegram pings — a voice message from Aunty May in Mandarin: *"早安啊 Auntie Lim, 吃了早餐和早药吗?"* Mdm Lim voice-replies: *"吃了早餐."* — but doesn't mention the meds. Aunty May gently: *"好, 记得吃药 hor, 我等下再 check."* Natural Mandarin-English code-switch, explicit medication check.
> → PERSONA + VOICE + DIGNITY + EXPLICIT CONFIRMATION CHECK
>
> **[0:20]** 9:02 AM. Confirmation window closes with meds still unconfirmed. Family Telegram group lights up. Agent posts: *"Aunty May's 8:45 check-in: breakfast confirmed, **morning meds unconfirmed**. **@Marcus** — you're on-duty Tuesdays. 3rd unconfirmed this week — logging for Saturday's GP visit. Draft below ⬇️"* Sarah sees it — she's in a stand-up. Marcus gets the @-mention.
> → GROUP VISIBILITY + ON-DUTY ROUTING + PATTERN LOGGING
>
> **[0:32]** Marcus opens the group chat. Below the agent's post, a pre-drafted nudge: *"妈, 吃药了吗?"* Marcus copies it, sends to Ma privately, taps **✓ Sent** on the agent's post. Group now shows *"Marcus sent the nudge at 09:03."* The mechanical part is seconds; the cognitive work is already done.
> → AGENT-DRAFTED NUDGE + HANDOFF CONFIRMATION
>
> **[0:42]** 9:14 AM. Aunty May's promised check-back: *"Auntie Lim, 吃了吗?"* Mdm Lim replies: *"哎哟, 刚才忘了. 现在吃了."* Agent posts to the group: *"✓ Morning meds confirmed 09:14. Logged for GP briefing."* Sarah glances at the notification as her stand-up ends. Mdm Lim's voice reply stays private; the family sees only the outcome.
> → AUNTY MAY CHECK-BACK + PRIVATE VOICE / PUBLIC OUTCOME + DIGNITY
>
> **[0:52]** Flash to the Friday weekly digest: *"Last 7 days — Sarah: 14 nudges. Marcus: 3. Spouse: 0. Marcus's turn to step up next week."* Invisible labor just became countable.
> → C4 AIF WEDGE MADE CONCRETE
>
> **[0:58]** Voiceover: *"This is AI care. The load the family didn't see — made visible, made fair."*

## 8. Data model

Minimum viable tables (Supabase / Postgres). Every user-scoped table carries `family_id` so RLS policies can enforce per-family isolation.

```
families
  id                  uuid (pk)
  group_chat_id       bigint          -- Telegram group id
  parent_user_id      uuid (fk users) -- the elderly parent
  timezone            text            -- default 'Asia/Singapore'
  languages           text            -- e.g. 'zh+en'
  symptom_diary_time  time            -- default '20:00'
  paused              boolean         -- /pause flag
  created_at          timestamptz

users
  id                  uuid (pk)
  family_id           uuid (fk families)
  telegram_user_id    bigint          -- unique
  handle              text
  display_name        text
  role                enum            -- 'parent' | 'caregiver'

medications
  id                  uuid (pk)
  family_id           uuid (fk)
  name                text
  dose                text
  times               time[]          -- e.g. {'08:45', '20:00'}
  active              boolean         -- default true

rotation
  family_id           uuid
  day_of_week         int             -- 0 (Sun) .. 6 (Sat)
  user_id             uuid (fk users) -- the caregiver on duty that day
  primary key (family_id, day_of_week)

events                -- append-only log; feeds nudge counter, briefing, patterns
  id                  uuid (pk)
  family_id           uuid (fk)
  type                enum            -- see list below
  payload             jsonb           -- event-specific details
  attributed_to       uuid (fk users, nullable)   -- for nudge-counter attribution
  medication_id       uuid (fk, nullable)
  created_at          timestamptz

pending_tokens        -- parent handshake tokens (Phase 2 of onboarding)
  token               text (pk)
  family_id           uuid (fk)
  expires_at          timestamptz
  consumed_at         timestamptz     -- null until claimed
  claimed_by          bigint          -- telegram_user_id, null until claimed

appointments          -- from .ics upload
  id                  uuid (pk)
  family_id           uuid (fk)
  starts_at           timestamptz
  title               text
  location            text

audio_cache           -- TTS output cache (keyed by text hash + voice id)
  text_hash           text (pk)       -- sha256(text || voice_id)
  voice_id            text
  audio_url           text            -- Supabase storage or local path
  created_at          timestamptz
```

**`events.type` values:** `med_reminder_sent`, `med_confirmed`, `med_missed`, `symptom_entry`, `nudge_posted`, `nudge_sent_by_caregiver`, `check_back_sent`, `briefing_generated`, `sensitive_defer`, `parent_optout`.

**RLS:** every query scoped by `family_id` ∈ (families where `auth.uid()` is a member).

**Medication scope (MVP):** only fixed daily times supported (`times time[]`). Complex regimens — alternating days, as-needed, meal-linked — are phase 2.

## 9. LLM prompts

Three load-bearing prompts. Use OpenAI function-calling for structured JSON output on all three.

### Classify + extract (GPT-4o-mini)

```
You classify the parent's voice-reply transcript into one of:
  - confirm_med         (explicit confirmation of medication)
  - partial_confirm     (confirmed part — e.g. "ate breakfast" but no mention of meds)
  - symptom_entry       (reports a bodily symptom)
  - clinical_question   (asks for medical advice)
  - distress            (emotional distress, grief, acute worry)
  - off_topic           (greetings, chatter, unrelated)

Context: what Aunty May just asked.
Transcript: <parent reply>

Return: { intent, medication_name?, symptom_text?, question_text?, confidence (0..1) }
```

### Decide + plan (GPT-4o)

```
You choose the agent's next action given the classified intent.

Rules (non-negotiable):
  1. clinical_question → ALWAYS use the deferral script:
     "I'm not your doctor, Auntie. Let me note this down for your next polyclinic
      visit, and I'll tell {caregiver_name} so she can bring it up with Dr {gp_name}."
  2. distress → brief acknowledge, route to on-duty caregiver. Never engage as therapist.
  3. symptom_entry → silent-log + warm thank-you.
  4. confirm_med → log confirmation + warm acknowledgment in the parent's language.
  5. partial_confirm → gentle re-ask of the unconfirmed part.

Return: { action, aunty_reply_text?, escalate_to_group (bool), log_only (bool) }
```

### Briefing compile (GPT-4o)

```
Compile 6 weeks of medication-adherence + symptom-diary events into a one-page GP briefing.

Sections (markdown):
  1. Medication adherence timeline (percentages, pattern callouts)
  2. Recurring symptoms (top 3, with frequency + trend)
  3. New-onset signals (things mentioned in last 2 weeks, not before)
  4. Family notes / questions for the GP

Clinical, compressed, 300 words max. Compile only — do not interpret.
Input: JSON array of events (timestamps + types + payloads) from the last 6 weeks.
```

## 10. Scheduling

**Requirements:**
- Fire at specific times per-family (e.g. 08:45 daily for Mdm Lim)
- Timezone-aware
- Survive process restarts
- Dynamic — add/remove jobs when family edits config via `/setup`, `/meds`, `/pause`

**Pick: APScheduler with SQLAlchemy job store (Postgres-backed).**

Jobs persist to the DB, survive restarts, and can be added/removed from a function call — which makes hooking into `/setup` straightforward.

**Job types:**

| Job | Trigger | Payload |
|---|---|---|
| `med_reminder_due` | cron per med × time slot | `(family_id, medication_id)` |
| `confirmation_window_close` | date (+15 min from reminder) | `(family_id, medication_id, reminder_id)` |
| `check_back_due` | date (+20 min from escalation) | `(family_id, medication_id)` |
| `symptom_diary_due` | cron daily at `symptom_diary_time` | `(family_id)` |
| `weekly_digest` | cron Friday 18:00 | `(family_id)` |
| `appointment_reminder_due` | date (day-before at 18:00) | `(family_id, appointment_id)` |

### Appointment ingest (`.ics` → scheduled reminders)

When a caregiver uploads a `.ics` file to the bot in DM:

1. **Parse** — use Python's `icalendar` (RFC 5545 compliant) or `ics` library
2. **Extract per event:**
   - `DTSTART` → `appointments.starts_at` (timezone-aware; HealthHub exports in `Asia/Singapore`)
   - `SUMMARY` → `appointments.title`
   - `LOCATION` → `appointments.location`
   - `UID` → store for de-dup on re-upload
3. **Filter** — ignore events with `starts_at` in the past
4. **De-dup** — match on `UID`: update existing rows if changed, insert new ones
5. **Schedule** — for each upcoming appointment, register an `appointment_reminder_due` job at `starts_at − 1 day − at 18:00 local`
6. **Confirm to caregiver** — bot replies: *"Found 3 upcoming appointments: 28 Apr (Dr Tan), 15 May (Dr Ng), 2 Jun. Day-before reminders added."*

**Error handling:**
- Malformed `.ics` → friendly error DM, don't crash
- Re-upload of same `.ics` → idempotent (no-op after de-dup)
- Timezone missing on an event → assume `Asia/Singapore`

**Fallback (simpler if APScheduler hits friction):** a one-minute tick from systemd timer or a cron job that queries the DB for all "due-now" events. Less elegant, zero job-state to manage.

## 11. Bot commands

### Primary caregiver (DM)

| Command | Purpose |
|---|---|
| `/start` | First-time hello; also captures `start` payload for the parent handshake token |
| `/setup` | Walk through onboarding (meds, rotation, parent handle, language, `.ics` upload) |
| `/confirm` | Confirm config after `/setup`; triggers Aunty May's intro to the parent |
| `/status` | Snapshot: today's on-duty, upcoming appointments, last med confirmation time |
| `/meds` | Show / edit the medication schedule |
| `/rotation` | Show / edit on-duty rotation |
| `/pause` | Pause all reminders (e.g., parent traveling) |
| `/resume` | Resume after `/pause` |

### Family group (any member)

| Command | Purpose |
|---|---|
| `/status` | Same snapshot as DM version |
| `/digest` | Force-show the weekly digest on demand |
| `/rotation` | View current rotation (edits require primary caregiver in DM) |

### Parent (DM with Aunty May)

| Command | Purpose |
|---|---|
| `/stop` | Parent wants to stop receiving messages. Respects the exit; DMs primary caregiver. |
| `/help` | Warm, simple explanation of what Aunty May does |

### `/meds` and `/rotation` edit flows

**Pattern:** inline buttons for discovery + short sequential messages for data entry. No free-text commands to memorize.

**`/meds` flow:**

1. Caregiver types `/meds`. Bot shows current meds with inline buttons:
   ```
   Current medications:
   • Lisinopril 10mg — 08:45, 20:00
   • Aspirin 100mg — 08:45
   
   [➕ Add]  [✏️ Edit]  [🗑️ Remove]
   ```
2. **Add** → sequential prompts: name → dose → times (e.g. `08:45, 20:00`) → confirm
3. **Edit** → button per medication → sub-buttons `[Change dose]` / `[Change times]` / `[Deactivate]` → edit flow
4. **Remove** → button per medication → confirm dialog

**`/rotation` flow:**

1. Caregiver types `/rotation`. Bot shows current week with buttons:
   - `Mon — @Sarah` `[Edit]`
   - `Tue — @Marcus` `[Edit]`
   - …
2. Tap **Edit** for a day → bot lists group members as buttons → tap to reassign

**Scheduler sync:** every add / edit / deactivate triggers APScheduler job re-registration (per §10 *"Dynamic — add/remove jobs when family edits config"*). No manual refresh.

**Other ongoing edits that don't need a flow:**

- **Re-upload `.ics`** — caregiver drops a new file in DM; auto-ingested and de-duped on `UID`
- **`/pause`, `/resume`** — instant state flip, no prompts
- **Family-member add / remove** — detected from Telegram group membership changes; caregiver uses `/rotation` to slot them in if needed

## 12. Challenges stacked

- **A4 — Ageing & independent living** *(primary)*
  - Voice check-ins + medication confirmation tracking
  - Symptom voice diary
  - Pattern detection: medication misses, symptom recurrences

- **D4 — Caregiver burnout** *(primary)*
  - On-duty rotation across siblings + spouses (configured at onboarding)
  - Agent-drafted nudges absorb emotional-labor cost
  - Weekly digest flags sustained imbalance

- **C4 — Invisible cognitive labor** *(primary, AIF)*
  - Weekly nudge counter attributes every @-mention, response, and ✓ to a family member
  - Agent-drafted nudges remove the compose-in-the-right-tone overhead

- **D1 — Preventive health inaccessible** *(primary)*
  - 6 weeks of medication confirmations + symptom voice-notes per consult
  - Structured one-page briefing PDF + QR the GP scans at the visit
  - Surfaces adherence rates, symptom recurrences, new-onset patterns

- **D3 — Asian-context health** *(secondary)*
  - Voice pipeline handles Mandarin + English via ElevenLabs Scribe (STT) + Multilingual v2 (TTS); SG-tuned MERaLiON-AudioLLM is the phase-2 STT upgrade for stronger Singlish + local-language depth
  - Persona calibrated to SEA hierarchical address norms (Aunty May / Ah Yi / Mak Cik — helper, slightly younger than the parent)
  - Briefing format tuned to SG polyclinic workflow (2-min consult, rotating GPs)
  - Family-group as the locus of healthcare decisions — matches Asian family-first dynamics

- **A3 — Unequal AI personalisation** *(secondary)*
  - Delivered via Telegram — no custom app, no hardware, no provisioning
  - Voice-first elderly UX — works even if they can't spell, type, or see well
  - Absorbs the coordination + monitoring gap that wealthier families fill with live-in help — no additional humans needed
  - Works with public polyclinic (no private GP required)

