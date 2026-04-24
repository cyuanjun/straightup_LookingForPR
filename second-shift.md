# Second Shift — Deep Dive

---

## The product

**One-line pitch:** *We automate the second shift — the invisible caregiver work dual-income families do between full-time jobs, own kids, and ageing parents.*

**Target user:** the **sandwich-generation adult child** (primary) + their spouse + their siblings (secondary). **Not** the elderly parent directly. This is the core framing win — every existing eldercare product talks to the wrong user.

**Who the sandwich generation is (SG / SEA-specific):**
- Age 35–55, married, both partners working full-time
- One or two school-age kids at home
- Ageing parent(s), at least one starting to decline — forgetting meds, missing bills, needing polyclinic visits, slowly becoming unsafe to leave alone
- Hired help (if any) is 3 hours a day; the other 21 hours fall on the family
- The load almost always defaults to one person — even when other family members could help, they often don't see the work happening
- That work is invisible to HR, invisible to spouse (often), invisible to the rest of the family

**Core thesis:** Singapore is ageing into a crisis where adult children are fewer, more likely to be dual-income, more likely to have their own kids at home, and more likely to split caregiving unequally across the family. Existing eldercare tools monitor the parent's fall risk. We **redistribute the caregiver work itself** — across siblings, spouses, and the agent — so one person isn't carrying it alone on top of their job and their own family.

**Why the name.** "Second shift" (Arlie Hochschild, 1989) is the foundational term for the unpaid labor that happens after paid work — originally about dual-income women, now broadly applied to anyone whose after-hours load is treated as invisible. The name signals we've read the scholarship; the product stays gender-neutral and lets the data speak for itself.

**Stacks:** ideas 1 (Filial Proxy, scoped down) + 3 (Fair Share Agent) + 5 (Next-Visit Briefing, workflow only) + 18 (MigrantMate) from `ideas.md`.

---

## What it covers

The product has **four user-facing surfaces**, each mapped to a challenge theme.

### 1. Medical workflow (D1 + D3 + D4)

Scope note: this is clinical *workflow*, not clinical *decision*. The product does not flag drug interactions, recommend dosages, or evaluate medication choices. That's for the GP. We just surface what happened.

- **Medication confirmation tracking** — at scheduled times Aunty May asks Mdm Lim to confirm intake; unconfirmed doses (within a window) flag to the family. Not clinical adherence monitoring — we track *confirmations*, not compliance. The GP interprets patterns; we just surface the signal.
- **Daily symptom diary** — she voice-notes ("今天脚痛" / "my leg hurts today"), agent transcribes + tags
- **Appointment manager** — schedule, reminders, transport coordination
- **Next-visit briefing** — structured PDF / QR for her polyclinic GP summarising the last 6 weeks of adherence + symptoms + anomalies → turns 2-minute consults into data-rich conversations
- **Pattern detection** — surfaces recurring signals across both **medication adherence** (e.g., *"morning meds unconfirmed 4 times in 2 weeks"*) and **symptom-diary content** (e.g., *"knee pain mentioned 5 days in a row"* / *"trouble sleeping mentioned 3 times this week"* / *"stopped mentioning X"*). All flagged to the family group + included in next-visit briefing. We do not interpret clinically — the GP decides what any pattern means.

### 2. Coordination (C4 + C3 + D4)

- **Load dashboard** — who's been on duty, who's handled reminders, who's responded to alerts, who's approved actions. Shared across the family by default — making the invisible load visible *is* the product.
- **Rotation scheduling** — agent assigns "who's on call" for any given day/week based on stated preferences + historical load balancing
- **Agent-drafted nudges** — when the on-duty person's turn comes, the agent drafts the "hey Mum's medication is due, can you remind her" message in the voice of whoever usually follows up. The default-follower-up stops having to be the chaser.
- **Family thread digest** — pulls from the family Telegram group, surfaces what actually needs action vs what's social

### 3. Financial (A3 + C3 + E2)

- **Recurring bill management** — auto-detect from SMS/email, schedule payments, flag anomalies (electricity up 40% → fan left on all night)
- **Weekly financial digest** — what went in, what went out, anything unusual, posted to the family group
- **Spending anomaly alerts** — unusual withdrawals, new merchants, subscription creep flagged in near-real-time

### 4. Admin (A4 + E2)

- **Receipts feed** — signed ledger of every action the agent took on the parent's behalf; every sibling can audit
- **Escalation ladder** — high-stakes actions (large payment, scheduling a visit, anything the parent flags as "ask my daughter") require sibling approval before the agent executes
- **Handoff to human professionals** — for anything medical, legal, or financial beyond routine bill-paying, agent drafts a handoff brief + suggests the next human to call

---

## Persona design

The agent presents as **different personas per stakeholder** — same underlying system, different surface. Parent interacts with a warm named companion; siblings interact with plain operational infrastructure. This is a product-layer decision on top of the architecture.

### Core principle

The product is a **caretaker-ops persona**, not a companion-AI-for-lonely-elderly. Warmth serves operations. This line keeps us clear of Replika / Pi-for-elderly territory — where emotional dependency becomes the revenue model, which is ethically fraught and regulatorily risky.

### Personas per stakeholder

| Stakeholder | Persona | Tone | Language | Primary surface |
|---|---|---|---|---|
| Elderly parent | **"Aunty May"** (working name — warm, named companion who messages, reminds, relays) | Warm, respectful, patient; never clinical | Mandarin + English for MVP / demo; Hokkien, Malay, Tamil in phase 2 | Telegram voice messages (async) |
| Family group (siblings, spouse, anyone sharing the load) | No persona — first-name basis, plain notifications | Tactical, concise, respects each person's time | Their preference | Shared Telegram group; agent uses @-mentions for on-duty routing |
| Family GP / polyclinic | No persona — structured briefing document | Clinical, compressed | Standard medical English | PDF / QR at visit |

**Why a persona for the parent:** Mdm Lim builds a relationship with a named voice over time. "Aunty May messaged" is meaningful in a way "app notification" is not. SEA cultural fit: hired help in SEA families is *named* (Aunty Rose, Kak Mei, Cikgu), and becomes part of the family fabric. Aunty May slots into that cognitive slot.

**Why voice messages over text for the parent:** elderly users (especially 65+) strongly prefer voice over text — typing on small screens is hard, Chinese input methods are tedious, small-text reading degrades with age. Voice is asynchronous (no pressure to respond immediately, no dropped call if she takes 30 seconds to find the right word), intimate (hearing a warm voice vs. reading a notification), and matches how SG elderly already use WhatsApp — leaving voice notes for family is the dominant mode. Voice also lets Mdm Lim speak in her natural language-mix (Mandarin + dialect + English) without typing any of it.

**Why one shared group for the family (not two separate roles):** real families don't split neatly into "default caregiver" and "helps-less sibling." The load redistributes over time and across roles. A unified group surface lets the agent route on-duty tasks to whoever's available, regardless of who *usually* carries more — and it doesn't bake an essentialist label into the product. The statistical reality (women carry more) is named in the *pitch*, not encoded in the product. That's a stronger AIF story: gender-neutral infrastructure that fixes a gendered outcome.

### Guardrails (non-negotiable)

1. **Disclosure on demand.** If Mdm Lim (or anyone) asks *"Are you a real person?"*, the agent says so immediately. No euphemisms. Never accepts requests to pretend to be human. Sandy will probe this in Q&A.
2. **Never impersonate a licensed professional.** Aunty May is a companion, never a nurse. Script when medical arises: *"I'm not your doctor, Auntie. Let me note this down for your next polyclinic visit, and I'll tell Sarah so she can bring it up with Dr Tan."* The agent logs the question in the next-visit briefing and pings the on-duty sibling — it does **not** attempt to call the doctor itself. Never gives medical advice (even obvious ones like "drink more water"), never makes health or wellness claims ("this is good for your joints"). Wanting will be merciless about any whiff of clinical agency.
3. **Disclosure at onboarding.** Family — especially the parent — consents explicitly. No deception by omission.
4. **No exploitation of attachment.** If Mdm Lim bonds with Aunty May, service obligation grows, not shrinks. Shutdown policy: graceful handoff + 30-day transition, never abrupt.
5. **Persona stability.** Same Aunty May every voice message. Same voice, personality, memory. No accidental persona drift. Never emulates a specific real person (e.g., a late spouse, an estranged child) — even if asked.
6. **Respect the user's exit.** Never persists conversation when the parent wants to hang up. Never escalates urgency to manipulate compliance.
7. **Heavy topics route to humans.** Death, grief, end-of-life, deep distress — if the parent raises these, Aunty May acknowledges briefly and routes to a human (sibling, counsellor, GP). She does not engage as a therapist.

### What Aunty May does

- Greet Mdm Lim by name, remember their prior conversations
- Deliver medication reminders warmly, check adherence
- Chat briefly with Mdm Lim when she wants to — not pushed
- Relay messages from family ("Sarah says dinner's at 6")
- Notice distress tone and escalate to the on-duty sibling

### Disclosure UX in the demo

Include a 5-second moment explicitly — this line will score disproportionately with Sandy and Hester:

> **Mdm Lim:** "Aunty May, you are a real person right?"
> **Aunty May:** "No, Mdm Lim, I'm an AI — I help keep you safe and in touch with Sarah. Real people still help you: Dr Tan, Sarah, your neighbour Mrs Koh. Is there anything you want me to clear up?"

### Cultural casting notes (SG-specific)

- **Name:** "Aunty May" is a working placeholder. Match family background. Chinese-dialect families: "Ah Yi" (阿姨) is a common address. Malay families: "Mak Cik" / "Kak." Avoid names already in the family.
- **Voice:** warm alto, mid-50s register, SG-English with local-language fluency. Not too young, not too old. Reassuring, not saccharine.
- **Age signal:** "Aunty" positions the persona as slightly younger than the parent — she's a helper, not a peer, not a child. Matters in Asian hierarchical norms.
- **Never use:** a Western-sounding name, a young voice, a doctor/nurse title, a male voice (male caretakers in SEA eldercare are rare; incongruous).

### Panel scoring implications

The persona decision lifts the AIF case from *"redistribution of labor"* to *"redistribution of labor + dignity preservation for the elderly woman."* Two-layer AIF story.

| Judge | Reaction | Why |
|---|---|---|
| **Janet + Hester** | 🟢 | Dignity-preserving companion hits the AIF dignity axis; gender-neutral product framing with data-surfacing is a softer but still legible AIF story |
| **Sandy** | 🟢 | Firm disclosure + no-impersonation = responsible-deployment exemplar |
| **Wanting** | 🟢 | Supportive after scope trim — cleaner lens (no polypharmacy, no AI-doctor risk); still depends on clinical-line discipline being visible in the demo |
| **Bing Wen** | 🟢 | Dignity-preservation fits CPF ageing-in-place thesis |
| **Nishith** | ⚪ | Neutral — product-layer choice, not infra |

---

## How it works (day-to-day)

The hero demo below is a high-drama 60-second scene. Here's the ordinary reality the product produces every day.

### One-time setup (~10 minutes)

- Add the bot to a family Telegram group (everyone sharing the caregiver load)
- Enter Mdm Lim's medication schedule, polyclinic appointments, recurring bill accounts
- Set on-duty rotation — days of the week, custom pattern, or round-robin
- Aunty May introduces herself to Mdm Lim in her first voice message — warm, brief, explicit AI disclosure
- Family agrees on what's visible in the group thread (defaults are shared; individual privacy is opt-in)

### Daily cycle

1. **Morning check-in (~8:45 or family-configured time)** — Aunty May voice-messages Mdm Lim asking about breakfast + morning meds
2. **Mdm Lim voice-replies** — agent parses which items she explicitly confirmed
3. **Confirmation window closes (~15 min)** — if all confirmed, silent log; if anything unconfirmed, agent posts to family group with @-tag for on-duty person + a pre-drafted nudge
4. **On-duty person acts** — copies the draft, sends to Mdm Lim privately (agent isn't in that private channel), then taps *"✓ Sent"* on the group post so the family sees the handoff happened
5. **Aunty May's check-back (~20 min later)** — she follows up with Mdm Lim as promised; if Mdm Lim confirms, resolution line posts to family group; if still unconfirmed, agent escalates

Throughout the day, **ad-hoc signals** land in the group with the same pattern (post + @-tag + optional draft): bill anomaly detected, appointment approaching, symptom voice-note from Mdm Lim, unusual spend, etc.

### Weekly cycle

- **Friday evening** — weekly digest posted to family group: load distribution (who handled what), notable events, upcoming appointments and admin for next week
- **Before each polyclinic visit** — next-visit briefing PDF generated from the last 6 weeks; shared with whoever's accompanying Mdm Lim

### Escalation thresholds

The agent decides its autonomy based on blast-radius:

| Blast radius | Agent behaviour |
|---|---|
| Low (routine reminders, log entries) | Auto-acts |
| Medium (message to parent, bill payment < S$200) | Drafts for family group, tags on-duty, waits for human send |
| High (large payment, medical decision, legal matter) | No action without explicit family-group approval |
| Clinical (symptom, medication question, diagnosis mention) | Never acts — logs for GP briefing, routes to human |

### What each surface sees

- **Mdm Lim:** only her private voice thread with Aunty May. Knows Aunty May is an AI (onboarding disclosure). Doesn't see the family group. Her voice replies stay between her and Aunty May.
- **Family group:** events, confirmations / misses, resolutions, load dashboard, weekly digest, ad-hoc signals. Doesn't see Mdm Lim's actual voice replies — only outcomes and summaries.
- **GP / polyclinic:** only the next-visit briefing PDF. No continuous feed.

---

## Hero demo script (60 seconds)

The one scene that fires all four surfaces. Sandwich-generation framing.

> **[0:00]** Voiceover: *"This is Mdm Lim, 78, in Toa Payoh. Her daughter Sarah is in Bukit Timah — full-time job in Raffles Place, two kids at primary school. Her brother Marcus works shifts at Changi."*
>
> **[0:08]** Tuesday 8:45 AM. Mdm Lim's Telegram pings — **a voice message from Aunty May** in Mandarin: *"早安啊 Auntie Lim, 吃了早餐和早药吗?"* (Good morning Auntie Lim, have you had breakfast and your morning pills?). Mdm Lim voice-replies: *"吃了早餐."* (I had breakfast.) — but doesn't mention the meds. Aunty May gently: *"好, 记得吃药 hor, 我等下再 check."* (Good — remember your pills, I'll check back.) Natural Mandarin-English code-switching, and a clear explicit check. (PERSONA + VOICE + DIGNITY + EXPLICIT CONFIRMATION CHECK)
>
> **[0:20]** 9:02 AM. Confirmation window closes with meds still unconfirmed. The **family Telegram group** lights up on everyone's phone. Agent posts: *"Aunty May's 8:45 check-in: breakfast confirmed, **morning meds unconfirmed**. **@Marcus** — you're on-duty Tuesdays. Pattern: 3rd unconfirmed this week, logged for Saturday's GP visit. Draft reply below ⬇️"* Sarah sees the message (she's in a stand-up — stays in her meeting). Marcus gets the @-mention ping. (GROUP VISIBILITY + ON-DUTY ROUTING + PATTERN LOG)
>
> **[0:32]** Marcus opens the group chat. Below the agent's post, a pre-drafted message: *"妈, 吃药了吗?"* (Ma, have you taken your medication?). Marcus copies it and sends it to Ma privately. Back in the group, he taps **✓ "Sent"** on the agent's post — the family group now shows *"Marcus sent the nudge at 09:03"* while Aunty May's check-back is still pending. The mechanical part is seconds — the cognitive work (what to say, in what tone) is already done. The agent learned the tone from the family's past messages. (AGENT-DRAFTED NUDGE + HANDOFF CONFIRMATION — emotional labor absorbed)
>
> **[0:42]** Around 9:14, Aunty May's promised check-back arrives for Mdm Lim: *"Auntie Lim, 吃了吗?"* (Auntie Lim, have you taken them?). Mdm Lim voice-replies: *"哎哟, 刚才忘了. 现在吃了."* (Aiyo, forgot earlier. Just taken them now.) The agent now has confirmation. It posts resolution to the family group: *"✓ Morning meds confirmed 09:14. Logged for GP briefing."* Everyone sees it — Sarah glances at the notification as her stand-up ends. Mdm Lim's voice reply stays private; the family sees the outcome. (AUNTY MAY CHECK-BACK + SIGNED RECEIPT + DIGNITY)
>
> **[0:52]** 12:30 PM. Family group pings again: *"Ma's electricity bill is 40% higher than last month. Fan left on overnight three times last week. **@Sarah** — you're free at lunch. Draft gentle message below ⬇️"* Sarah taps "send." (FINANCIAL ANOMALY + ON-DUTY ROUTING)
>
> **[0:58]** Voiceover: *"This is the second shift. Automated. Redistributed. One family, no one drowning."*

That's the pitch moment. Everything else is architecture + evidence + ask.

**Why this scene works for this panel:**

- **Aunty May's voice message** opens with the persona in action — warm, in-language, dignified; no phone-call friction for the elderly user
- **Everything after happens in the family group chat** — full transparency. Sarah sees Marcus's task; Marcus sees Sarah's later. Nobody is siloed; nobody has to forward or CC.
- Sarah is in a meeting — relatable for every working professional in the room
- **The @-mention** routes the work without DMing or shaming — the whole family sees the load *and* who's on today
- Mdm Lim keeps her dignity (voice reply in her own language stays private; only resolution status posts to the group, not the content)
- The emotional-labor absorption (agent drafts the nudge in Sarah's voice; Marcus just copies, sends, and taps ✓) is the C4 AIF wedge explicit
- The pattern detection ("3rd unconfirmed this week, logged for GP") hits Wanting's clinical-workflow lens *without* touching clinical decision-making
- The financial anomaly is universal adulting but done with care, not surveillance

---

## Challenges stacked

| Challenge | Primary / secondary | How it's addressed |
|---|---|---|
| **A4** Ageing & independent living | **Primary** | Parent stays at home; agent reduces risk without surveillance-feel |
| **D4** Caregiver burnout | **Primary** | Load absorbed + redistributed; burnout signals flagged |
| **C4** Invisible cognitive labor *(AIF)* | **Primary** | Family load dashboard + agent-drafted nudges = invisible labor made visible and redistributable |
| **D1** Preventive health inaccessible | **Primary** | Between-visit adherence + next-visit briefing bridges 2-min polyclinic consults |
| **E2** Governance & auditability | **Primary** | Signed receipts feed; sibling-visible audit; approval ladder for high-stakes |
| **D3** Asian-context health | Secondary | Mandarin voice ingest in MVP (other SEA languages phase 2); polyclinic workflow hand-off |
| **A3** Unequal AI personalisation | Secondary | Lower-income households benefit most (fewer private caregivers, more reliance on public polyclinic visits) |
| **C3** Fragmented communication | Secondary | Consolidates Telegram family threads + SMS reminders + polyclinic portal emails |

**5 primary + 3 secondary = 8 challenges touched, with ONE shared root cause** (adult children managing an ageing parent).

This satisfies the `challenge-statements.md` stacking rule: *"Multiple challenge statements can be combined, but they must all be addressed through one general solution — not separate features stapled together. The bundled challenges should share a root cause that a single product can credibly tackle."*

**Notable coverage of the AIF-tagged challenges:** C4 is the AIF-tagged challenge that the "siblings redistributing invisible labor" primitive hits cleanly — this gives the project an AIF scoring tailwind (Janet + Hester pre-disposed) that standalone Filial Proxy didn't have.

---

## Judging-criteria fit

The rubric is 3+3+1+1+1 = 9 points. Here's a dimension-by-dimension projection with justification.

### Challenge-Solution Fit ⭐️⭐️⭐️ (3 pts) — target: **3/3**

*"Does the project meaningfully solve the challenge statement? Is the target audience or use case well-defined?"*

- Stacks 5 primary challenges around one root cause — exactly what the stacking rule rewards.
- Named archetype (Mdm Lim in Toa Payoh + daughter Sarah in Bukit Timah + son Marcus working shifts at Changi) grounds every feature in a concrete user story.
- Each feature maps to a specific HMW in the challenge doc, not a retrofit.
- **Risk to this score:** if the demo feels like a feature list instead of one user's story arc, judges will downgrade to 2/3. Mitigation: the hero demo is a single 60-second scene (see below) that shows all four surfaces firing for one family.

### Technological Execution ⭐️⭐️⭐️ (3 pts) — target: **2.5–3/3**

*"Are APIs integrated in a way that adds real value? Custom logic, workflows, system design? Beyond a simple wrapper?"*

Satisfies the AI-is-load-bearing bar from the challenge doc via **four distinct AI primitives doing real work**:

1. **Multi-step agentic pipeline** — ingest → classify → plan → execute → log → alert → brief → escalate (8 steps, exceeds Nishith's 5–7 minimum)
2. **Multimodal ingest** — voice in Mandarin + English (other SEA languages phase 2) + photos (bills, documents) + text from SMS/email
3. **Pattern detection + anomaly reasoning** — medication-adherence patterns, symptom-diary recurrences, bill anomaly detection, sibling-load graph analysis; LLM-augmented classical stats, not heuristics
4. **Tool-use with state + persona-consistent voice generation** — the agent exchanges voice messages with Mdm Lim via Telegram using a consistent voice persona, remembers prior conversations, and executes actions (send messages, pay bills, log events) with signed receipts

**Risk to this score:** Nishith will look for "any 'Claude does it' step" as a red flag. Mitigation: in the architecture slide, show explicit decision points where the LLM chooses a tool vs asks for human approval vs refuses.

### Product Thinking & UI/UX ⭐️ (1 pt) — target: **0.8–1/1**

*"Is the user flow clear? Does it reduce friction?"*

- **Two distinct views** — parent view (Telegram voice-message thread, minimal + warm), family group view (shared Telegram group for siblings + spouse + anyone on the load; agent uses @-mentions to route on-duty work). Clear separation between "whose turn is it" and "what's Mdm Lim saying."
- Voice-first for the parent's surface (elderly-accessible); text-first for the family group (async, fits around work).
- **Risk:** even two surfaces is scope. Mitigation: the parent view is effectively a Telegram thread (almost no build), so polish concentrates on the family group view — the part that shows rotation logic, load dashboard, and the hero demo's "agent drafted a nudge" beat.

### Originality & Insight ⭐️ (1 pt) — target: **1/1**

*"Is the approach differentiated? Does it reframe the problem?"*

**Three reframes stacked:**

1. **"Talk to the caregiver, not the patient."** Every eldercare product on the market (fall-detectors, medication reminders, video-call apps) puts the elderly person at the centre. This one centres the caregiver network and treats the elderly parent as one node.

2. **"The second shift is the product."** Most productivity tools for working families optimize paid work. This one automates the unpaid work that happens around it — and it names that work using Hochschild's 1989 term. The name is legible to those who know the scholarship (Janet, Hester) without the product needing to be branded "for women."

3. **"The enemy isn't distance, it's default."** Overseas-diaspora eldercare startups frame the problem as "my parent is far away." The reframe: the problem is that even when family is 20 minutes away by MRT, the load still defaults to one person. Redistribution is the product, not proximity. *(The data our product surfaces tends to show that one person is usually a daughter — but we let the data say that, not the pitch deck.)*

All three should be said out loud in the pitch.

### Evidence of Real Demand ⭐️ (1 pt) — target: **0.5–1/1**

*"Interviews, surveys conducted during the remote week."*

- Interview plan targets four archetypes: the sandwich-generation default caregiver (primary), spouse / sibling who helps less, the overseas adult child (secondary case), and one family GP — see [evidence-of-demand plan](#evidence-of-demand-plan) below.
- Realistic target: 6+ interviews by demo day given the 5-day window.
- **Risk to this score:** if no interviews happen this week, this dimension collapses to 0. Non-optional.

### Projected total

**7.0–8.5 / 9** if execution holds. For context, hackathons at this panel level usually see winners in the 7.5–8.5 range, so the top of this range is contender-tier. The scope trim (no polypharmacy, no CPF/CareShield/MediSave) and the de-gender positioning shift both lowered the ceiling in exchange for higher floors and more defensible pitch framing — see [Net assessment](#net-assessment).

---

## Panel alignment (judge-by-judge)

| Judge | Probable reaction | Why |
|---|---|---|
| **Janet Neo** (AIF) | 🟢 Strong | The "Second Shift" name + data-driven surfacing of the gendered load disparity still hits AIF relevance — just via transparency rather than product targeting. Softer than a women-branded pitch, but defensible under scrutiny and more honest about the data. |
| **Hester** (Epic Angels) | 🟢 Strong | Product isn't gender-targeted, but the data the product generates is the evidence of the gendered load. Still maps to her thesis; won't be a 🟢🟢 without a women-first product brand. |
| **Sandy** (OpenAI policy) | 🟢 Strong | Signed receipts feed + approval ladder = governance built in by default, not bolted on. Direct E2 story. |
| **Dr Wanting Zhao** (NHG) | 🟢 Supportive | Cleaner lens now — with polypharmacy removed, there's no "AI doctor" risk. Next-visit briefing is pure clinical workflow (logs adherence + symptoms, hands off to GP) which she will recognise as respectful of clinician authority. Frame as "we compress the 2-minute consult input; you decide." |
| **Nishith** (Stripe) | 🟢 Strong | Multi-step agentic pipeline + real tool use + multimodal + RAG = substantive tech. Avoid any "Claude does it" shortcut in the architecture slide. |
| **Bing Wen Tan** (CPF) | 🟡 Supportive | Still aligned on ageing-in-place thesis (keeping elderly safe at home vs institutional care). Weaker now that we've removed CareShield/MediSave integrations — his strongest lens was on financial programs. Can still speak to CPF-dependent households relying on public polyclinic. |
| **Desmond** (ACE.SG) | 🟡 Supportive | Likes SG fit; will push on monetisation. Have a clear BM answer (see below). |
| **Gabrielle** (SMU) | 🟡 Neutral-positive | Not her student lens, but will score commercially and on the C4 AIF angle. |
| **James Xu** (Ant) | 🟢 Strong | SEA ageing is a scale play — every SEA country is ageing. ESG angle if framed as "keeping elderly out of institutional care." |
| **Cheryl / Daryl / Malavika** (SEA VCs) | 🟡 Supportive | SEA-first GTM ✓. Will press on defensibility — have an answer on data flywheel + family network effect. |
| **Theresa** (Antler) | 🟡 Neutral | Not solo-founder-obvious; her lens is "who is the founder and why them?" — prepare the founder-market-fit story. |
| **Joshua** (January) | 🟡 Neutral | Will score on BM clarity. Subscription + family-pack answer should land. |
| **Heng Xuan** (ex-B Capital) | 🟡 Supportive | Moat question is real for this space — lead with data flywheel + integration depth. |

**Summary:** 6 strong votes, 7 supportive — no "very strong" locks after the de-gendering (Janet + Hester downgraded from 🟢🟢 to 🟢 but stay on the ledger via data-surfacing). AIF axis is still part of the scoring story but no longer the dominant engine; Wanting moved from conditional to supportive after scope trim; Bing Wen weakened slightly (lost his CPF-specific angle).

---

## AI architecture (the 5–7 step pipeline)

For Nishith's technical-execution slide, the architecture needs to show load-bearing AI at multiple decision points.

```
                             ┌─────────────────────┐
                             │  Multimodal Ingest  │  voice (Mandarin + English
                             │                     │  MVP; other SEA phase 2),
                             │                     │  photo, SMS/email/Telegram
                             └──────────┬──────────┘
                                        │
                             ┌──────────▼──────────┐
                             │  Classify + Extract │  LLM → {medical event,
                             │                     │  financial event, social,
                             │                     │  admin task, escalation}
                             └──────────┬──────────┘
                                        │
                             ┌──────────▼──────────┐
                             │  Pattern + Anomaly  │  med-adherence patterns,
                             │  Reasoning          │  symptom-diary recurrences,
                             │                     │  bill anomalies, load graph
                             └──────────┬──────────┘
                                        │
                             ┌──────────▼──────────┐
                             │   Decide + Plan     │  LLM chooses: auto-act /
                             │                     │  draft-for-approval /
                             │                     │  escalate / hold
                             └──────────┬──────────┘
                                        │
                ┌───────────────────────┼────────────────────────┐
                │                       │                        │
      ┌─────────▼─────────┐  ┌──────────▼──────────┐  ┌──────────▼──────────┐
      │   Tool Execution  │  │  Sibling Nudge Gen  │  │ Next-Visit Briefing │
      │   ───────────     │  │  ───────────        │  │  ───────────        │
      │ • polyclinic      │  │ drafts message in   │  │ longitudinal record │
      │   appointment     │  │ sender's voice;     │  │ → structured PDF    │
      │ • Aunty May voice │  │ fair-share logic    │  │ for GP              │
      │   msg via Telegram│  │ picks recipient     │  │                     │
      │ • bill payment    │  │                     │  │                     │
      └─────────┬─────────┘  └──────────┬──────────┘  └──────────┬──────────┘
                │                       │                        │
                └───────────────────────┼────────────────────────┘
                                        │
                             ┌──────────▼──────────┐
                             │   Signed Receipts   │  C2PA-style signature:
                             │      Feed           │  agent ID, action, time,
                             │                     │  blast radius, rollback
                             └──────────┬──────────┘
                                        │
                             ┌──────────▼──────────┐
                             │  Weekly Digest /    │  per-sibling view;
                             │  Anomaly Alerts     │  per-parent view; per-GP
                             │                     │  briefing
                             └─────────────────────┘
```

**Decision points for Nishith's slide:**

1. **Classify** — LLM routes to correct downstream path (medical workflow / financial / coordination / admin)
2. **Plan** — LLM chooses auto-act vs draft-for-approval vs escalate (per blast radius)
3. **Pattern + anomaly reasoning** — medication-adherence patterns, symptom-diary recurrences, bill anomalies, sibling-load graph
4. **Sibling rotation logic** — fair-share graph picks recipient by recent load
5. **Persona-consistent voice generation** — Aunty May sends Mdm Lim voice messages with stable voice + memory of prior conversations
6. **Receipt signing** — every action signed + rollback-linked

**Where human-in-the-loop lives** (for Sandy):

- All medical observations → surfaced to sibling + GP, never interpreted
- All financial payments > S$200 → approval required
- All medical appointment changes → approval required
- All escalations → routed, not resolved
- Anything clinical → "I'm not your doctor — I'll note this for your polyclinic visit and tell Sarah." Logs to next-visit briefing + pings on-duty sibling. No outbound call to the GP.

---

## Tech stack choices (for a 5-day build)

| Layer | Choice | Why |
|---|---|---|
| **Backend** | Python (FastAPI) | Fastest for agentic workflows; rich LLM + audio ecosystem |
| **Dialogue / reasoning LLM** | GPT-5 (primary) + GPT-4o-mini (fast routing/classification) | OpenAI chosen for persona + memory + tone; gpt-4o-mini for cheap fast paths |
| **STT (primary)** | **MERaLiON-AudioLLM** (A*STAR, open weights) | Purpose-built for Singlish + English/Mandarin code-switching; SG-first training data |
| **STT (fallback)** | Whisper-large-v3 | Used when MERaLiON language-confidence is low; also the phase-2 fallback for Hokkien/Tamil |
| **TTS** | ElevenLabs Multilingual v2 (Mandarin + English voices) | Natural, fastest to ship for the MVP demo |
| **Phase 2 voice expansion** | Fish Speech or OpenVoice (myShell) for Hokkien; dialect-specific fine-tunes later | Out of scope for hackathon week — document in roadmap slide only |
| **Database** | Supabase (Postgres + RLS) | Multi-user access controls built-in; fast setup |
| **Frontend** | Next.js + Tailwind (family-group view only) | Parent view lives inside Telegram; only the family group view needs a web UI |
| **Messaging** | Telegram Bot API (not WhatsApp) | WhatsApp Business API provisioning takes > 1 week; Telegram is instant and SEA-familiar |
| **Voice transport** | Telegram Bot API — `sendVoice` for outbound, `voice` message handler for inbound | Async voice messages match elderly UX preference (voice over text — see persona-design rationale); no phone/carrier dependency; zero-provisioning |
| **Tool use** | OpenAI function calling + MCP servers for external integrations | Shows Nishith explicit tool schemas |
| **Auth** | Clerk or Supabase Auth | Multi-user family structure |
| **Signing** | ed25519 signed payloads (simple) or C2PA (ambitious) | Receipts feed credibility |

### Voice agent pipeline (Aunty May)

```
Mdm Lim records voice reply in Telegram
         │
         ▼
  Telegram Bot API — receives voice message (opus file)
         │
         ▼
  MERaLiON-AudioLLM — STT (Mandarin + English code-switch for MVP)
         │   ↓ if language-confidence < threshold
         ├── Whisper-large-v3 fallback
         ▼
  GPT-5 dialogue layer — persona, memory, tone, script rails
         │
         ▼
  ElevenLabs Multilingual v2 — TTS response (Mandarin + English)
         │
         ▼
  Telegram Bot API — sends voice message back (sendVoice)
         │
         ▼
  Mdm Lim taps play; hears Aunty May
```

Why this stack: MERaLiON handles Singlish/Mandarin STT (what it's best at). OpenAI handles dialogue + tool use with persistent persona + memory. ElevenLabs ships a natural voice fast. Telegram transport = zero infra (no Twilio / carrier / phone-number provisioning), works instantly in any country, free. Each layer is swappable as phase-2 language support matures.

**MVP language scope:** Mandarin + English only. This covers the majority of the target SG sandwich-generation archetype (Mdm Lim, 78, Mandarin-educated Chinese Singaporean — the largest slice of the elderly population in mature estates like Toa Payoh). Hokkien / Malay / Tamil support is a **phase-2 priority** — documented in the roadmap slide. Rationale: every tool in the stack (MERaLiON, Whisper, GPT-5, ElevenLabs) has its strongest support for Mandarin; attempting all four languages in 5 days blows the build.

**Integrations to make real (not all):**

- **Must be real:** Telegram bot for both sibling messages AND Aunty May voice-message exchange with Mdm Lim (same transport — one integration, two surfaces); signed receipts feed
- **Mocked with real UI:** polyclinic appointment booking (HealthHub sandbox if accessible, else mocked); bill ingestion from email/SMS; bill payment flow
- **Slide only:** deeper polyclinic integration, insurance, banking APIs, multi-family fleet management

The rule: **the live demo moment is the Aunty May voice-message exchange.** Bot sends her morning voice message, you (playing Mdm Lim) reply with an actual voice recording in Mandarin, bot processes it via MERaLiON → GPT-5 → ElevenLabs, bot responds with a new voice message. All visible on a single Telegram thread on stage.

---

## Week plan (Apr 20 Mon → Apr 25 Sat)

Submission is **Fri 25 Apr by 12:00 PM**, pitches **1:00 PM**. Effectively 5 days.

### Mon 20 (today)
- **AM:** Lock scope (this doc → decisions). Stop ideating, start building.
- **AM:** Set up repo, Supabase, Telegram bot, LLM auth, basic scaffolding.
- **PM:** Wire the multimodal ingest pipeline (voice → classify → log).
- **PM:** Start interviews (3 target: 2 sandwich-generation default caregivers + 1 helps-less spouse/sibling). Book Tue / Wed slots.

### Tue 21
- **AM:** Build the sibling rotation / load graph + "who's on call" logic. Data model.
- **AM:** Wire Aunty May voice loop — Telegram `voice` handler → MERaLiON STT → GPT-5 dialogue → ElevenLabs TTS → Telegram `sendVoice`. Test end-to-end with a team member playing Mdm Lim.
- **PM:** Build the next-visit briefing pipeline — ingest → structure → PDF.
- **PM:** Conduct 2 of 3 first interviews. Document verbatim quotes.

### Wed 22
- **AM:** Build the bills anomaly detection + weekly digest.
- **AM:** Build the signed receipts feed (ed25519 if C2PA is too much).
- **PM:** Wire the tool-use layer — polyclinic booking mock + bill-payment mock.
- **PM:** Remaining interviews. Target 6 total by end of Wednesday.

### Thu 23
- **AM:** End-to-end demo run-through. The 60-second hero scene should work front-to-back.
- **AM:** Fix the three worst bugs.
- **PM:** Build the UI for the three user views. Adult-child view gets pixel polish; the other two just need to be legible.
- **PM:** Rehearse pitch with a stopwatch. Hit 3 min flat.

### Fri 24
- **AM:** Buffer day. Final polish, final rehearsals, final data loading.
- **AM:** Record demo video for Devpost (backup if live demo breaks).
- **PM:** Deck polish. Cut ruthlessly. No slide should feel "filler."
- **Evening:** Sleep. Do not over-tweak.

### Sat 25 — Demo day
- **Before noon:** Submit Devpost.
- **12:45:** Arrive. Test audio / video from the org's laptop.
- **1:00–2:45:** Thematic pitches. Best in Theme announced.
- **3:00–4:30:** Top 5 pitch. Crowd Favourite + AIF Top 2 announced.

---

## Risks specific to this stack

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Persona slippage into clinical territory | Medium | High (kills Wanting) | Hard script when medical topics arise: *"I'm not your doctor — I'll note this for your next polyclinic visit and tell Sarah."* Logs to briefing + pings sibling; does NOT attempt to call GP. Rehearse the line. Demo must show this in flight. |
| Scope creep — 4 surfaces too many | High | Medium | Hero demo pre-decided; MVP scope locked Monday AM; anything off-path gets roadmap-slide'd |
| Privacy/consent of elderly parent | Medium | High (ethical + optics) | Opt-in flow visible in demo; parent has veto on what siblings see; show this explicitly |
| Sibling coordination UX hard to demo | Medium | Medium | Use the 60-second hero script; don't try to show live multi-user in the demo — use staged states |
| No real interviews by demo day | Medium | High (kills Evidence score) | Book Tue/Wed slots on Monday; protect them from build time |
| Integration dependency breaks on stage | Medium | High | Pre-record demo video as backup; live demo is aspiration, video is insurance |
| Voice-agent latency / failure during live demo | Low-medium | Medium | Telegram voice-message loop is async + well-tested; much lower risk than a phone call. Still record backup video of the voice exchange in case network fails at venue. |
| BM question from VC bloc | High | Low-medium | Pre-prepared: subscription S$15/mo per family + family-pack S$25/mo for 3+ siblings; roadmap includes premium voice-agent tier + hired-help marketplace integration |

---

## Market context & edge

### Incumbents

- **Hired-help marketplaces:** Homage (Singapore; caregiver-by-the-hour), CareConnect, Active Global Caregivers — these sell human-caregiver time. Useful if you can afford it, and the caregiver only comes 3 hours/day. Who handles the other 21?
- **Medication reminders:** Medisafe, Round Health — single-user consumer apps; no sibling coordination, no clinical briefing, no family context.
- **Family coordination (general):** Cozi, Life360 — family-logistics apps (school pickups, shared calendars); no eldercare depth, no SG integration, no caregiver-labor framing.
- **Government infrastructure:** HealthHub (SG) has comprehensive records but zero agency — it's a read-only portal, not a product that does things.
- **Senior hardware:** GrandPad and similar — centres the elderly person, usually invasive, doesn't solve the caregiver load at all.

### What incumbents won't do

- **Homage** is a human-caregiver marketplace. Adding agentic coordination threatens their unit economics (they sell caregiver hours; we reduce the hours needed).
- **HealthHub** is SG government infrastructure; it won't sell a subscription product or build sibling-visible workflows.
- **Medisafe / Round Health** are single-user by architecture — sibling coordination would require rebuilding from scratch.
- **Cozi / Life360** optimize for child-centric family logistics; they won't pivot to ageing-parent care because it's a different emotional market.
- None of them frame **the caregiver as the user**. None of them name **the second shift**. That's the wedge.

### The edge (one line)

*"We are the only product that treats the sandwich-generation caregiver group as the user — and automates the second shift they were never paid for."*

### Why a US/Western copycat can't take this

- **SEA-language-native voice:** Mandarin / Hokkien / Malay / Tamil voice messages (MVP is Mandarin; others on phase-2 roadmap) are not a retrofit for a US-first product
- **Cultural-specific:** filial-piety pressure + dual-income working-mother context differs fundamentally from Western eldercare (more family-centred, less nursing-home-centred)
- **SG polyclinic workflow:** briefing-document format tuned to SG public-health norms (2-min consults, standardised discharge notes) requires local medical-system understanding

---

## Evidence-of-demand plan

Target: 6–10 interviews by Fri 24 Apr.

| Archetype | Target count | Where to find | Key questions |
|---|---|---|---|
| **Sandwich-generation default caregiver** | 3–4 | SG-based, 35–50, dual-income household, kids + ageing parent; NTU/NUS Alumni network; parent FB groups; friends-of-friends. Data will likely skew female — don't filter. | "What broke last week? What did you drop — your work, your kids, or your parent? Who else should have been doing it?" |
| **Spouse / sibling who helps less** | 2 | Honest counterparts of above; ask the first group for introductions; be explicit you want the OTHER family member | "What stops you from doing more? Is it refusal, invisibility, or genuinely not knowing what to do?" |
| **Overseas adult child** (secondary case) | 1–2 | SG-origin, based abroad; LinkedIn; SG diaspora Reddit | "When your SG-based sibling is carrying the load, what do you feel you can contribute remotely?" |
| **Family GP / polyclinic doctor** | 1 | Via Wanting's NHG network if possible, or LinkedIn | "If a patient's family gave you a structured briefing before the visit, what would you do differently?" |

**Output:** 3 verbatim quotes per archetype. The single strongest slide is usually: *"Three things every default caregiver said about their parent"* — with the demographic data (e.g. "8 of 10 were women") surfaced alongside, not as the headline.

**What to listen for specifically:**

- Concrete moments of dropped balls ("I forgot mum's polyclinic appointment because my kid had a school thing")
- The emotional-labor tell ("I'm the one who texts the group chat")
- The fair-share frustration ("he says he'll help if I ask, but I shouldn't have to ask")
- Guilt-coping strategies ("I bring her tingkat dinner on Wednesdays so I feel less guilty about missing Sunday lunch")

These quotes are the demo-day emotional hook.

---

## Roadmap (phase 1 / 2 / 3)

Putting this on a roadmap slide signals to Bing Wen that we understand the CPF / CareShield / MediSave lens even though we scoped it out of the hackathon MVP. The message: *"We prioritised the behavioural layer because that's where the AI wedge is. Financial integration is planned; we know the ecosystem."*

### Phase 1 — Hackathon MVP (this week)

- **Medical workflow:** medication confirmation tracking, daily symptom diary, pattern detection (adherence + symptom-diary recurrences), next-visit briefing for GP
- **Coordination:** sibling rotation, load dashboard, agent-drafted nudges, weekly digest
- **Financial:** bill tracking + anomaly detection
- **Admin:** signed receipts, escalation ladder, human-professional handoffs
- **Persona:** Aunty May voice agent (Mandarin + English primary for demo)

### Phase 2 — First 6 months post-hackathon

- **CareShield Life claims** filing automation
- **MediSave top-up** management + CHAS eligibility tracking
- **CPF Silver Support** screening for eligible households
- **Polyclinic / HealthHub** deeper integration (appointment API, discharge note ingestion)
- **Multilingual voice expansion** — Hokkien, Malay, Tamil (see voice-model options below)
- **Hired-caregiver marketplace handoff** (Homage / CareConnect) for families with in-person needs
- **Family emergency protocol** — when agent detects a high-severity signal, escalate to the family's designated on-call sibling + pre-selected polyclinic

### Phase 3 — 12+ months

- **Predictive signals** — "Mdm Lim has had 4 missed evening doses in 3 weeks; this correlates with cognitive decline patterns; consider escalating to an eldercare specialist"
- **Cross-SEA expansion** — Malaysia (EPF), Indonesia (BPJS), Thailand (SSO) — same model, different government program integrations
- **Multi-parent families** — caring for both sets of parents simultaneously; cross-family sibling graphs
- **Eldercare concierge marketplace** — connect families to vetted specialists (geriatrics, home-nursing, palliative) when the agent detects the need

---

## Pitch deck outline (3-min pitch)

10 slides, 18 seconds per slide average. Every slide must earn its time.

1. **Title** — product name + one-line pitch + team
2. **The caregiver problem** — Sarah in Bukit Timah with two kids and a job; lead with the human, not the tech
3. **The reframe** — "Every eldercare product talks to the patient. We talk to the caregiver — and automate the second shift."
4. **Hero demo (video, 60s)** — the scene above
5. **What it covers** — 4 surfaces, 1 agent, visual map
6. **Architecture** — the AI pipeline diagram, call out load-bearing primitives
7. **Roadmap** — phase 1 (today's demo) / phase 2 (CareShield, MediSave, CPF, multilingual) / phase 3 (cross-SEA) — signals to Bing Wen we understand the financial-programs lens
8. **Evidence of demand** — 3 verbatim quotes from 6 interviews
9. **Market + edge** — why incumbents won't build this; one-line edge
10. **Ask** — "We want to build this post-hackathon. Here's our BM, moat, and 6-month roadmap."

**Cut ruthlessly.** If a slide doesn't directly support Challenge-Solution Fit or Technological Execution (67% of score), question it.

---

## Net assessment

Projected panel score: **7.0–8.5 / 9** if execution holds and interviews happen. Two deliberate scope choices brought the ceiling down slightly but raised the floor meaningfully: (1) the clinical scope trim removed Wanting + Bing Wen risks, (2) the de-gendering positioning shift removed defensibility risk at the cost of AIF-tailwind strength.

Trade-offs made:

- **Scope trim (polypharmacy + CPF/CareShield/MediSave out):** lost Wanting's RAG-depth lens and Bing Wen's financial-programs lens; gained much lower risk of "AI doctor" flags and a cleaner demo.
- **De-gender positioning (product is gender-neutral, data reveals the disparity):** lost the women-first AIF tailwind (Janet + Hester move from 🟢🟢 → 🟢); gained broader TAM, more VC-defensible framing, and the more honest "data speaks" move.
- **Net:** ceiling dropped from original 8–9 to ~7.0–8.5, but floor is ~7 and the pitch is structurally safer. Still contender-tier.

Where the score now comes from:

- **AIF relevance via data, not branding.** The "Second Shift" name is legible to Janet + Hester; the Aunty May persona preserves elderly dignity; the load-transparency layer surfaces the gendered load disparity without the product being women-targeted. Softer AIF story than a women-first product, but more defensible under VC scrutiny and more honest about what the product actually does.
- **Sandy's governance story** is stronger with persona + disclosure discipline as exemplar.
- **Wanting's workflow lens** replaces the clinical-depth lens — safer, supportive rather than conditional.
- **Nishith's infra bar** still cleared via voice agent + anomaly reasoning + persona-consistent TTS + tool use.

Main dependency: **discipline**. The hackathon version is one 60-second scene that shows Aunty May + fair-share + next-visit pattern + bill anomaly. If scope widens past that, the demo gets diffuse.

**All product decisions are locked. Only remaining item is the interview schedule (in progress).** Start building Monday AM.
