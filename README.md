# AI care

Agentic Telegram bot for Singapore sandwich-generation eldercare coordination. The user is the **adult child and their siblings**, not the elderly parent — the product redistributes invisible caregiver work across the family.

Three surfaces, one agent backbone:

- **Parent DM (Aunty May)** — voice persona, Mandarin + English. Med reminders, evening check-ins, distress / urgent-symptom safety paths.
- **Family group** — escalation posts with on-duty @-mention + ✓ Sent button, daily 06:00 morning report, weekly Friday digest with coverage stats.
- **GP briefing** — one-page PDF + QR, generated on demand from 6 weeks of dose outcomes + symptom events.

Spec: [plan.md](plan.md). Constraints + agent guardrails: [CLAUDE.md](CLAUDE.md).

---

## Prerequisites

- Python 3.11+ (tested on 3.14)
- A [Supabase](https://supabase.com) project (free tier is fine)
- A Telegram bot (talk to [@BotFather](https://t.me/BotFather))
- An [OpenAI API key](https://platform.openai.com)
- An [ElevenLabs API key](https://elevenlabs.io) + a chosen voice ID (free tier covers demo-scale usage)
- [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (named tunnel for a stable webhook hostname)

## Setup

```bash
# 1. Install deps (uv recommended, pip works fine too)
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Fill in .env
cp .env.example .env
# edit .env — see "Environment variables" below

# 3. Set up the database
# In Supabase SQL Editor, run:
#   supabase/schema.sql   (creates all tables + enums + indexes + RLS)
#   supabase/seed.sql     (one demo family — optional but useful)

# 4. Stable webhook URL via cloudflared
cloudflared tunnel create aicare
cloudflared tunnel route dns aicare aicare.your-domain.com
# Set WEBHOOK_URL in .env to https://aicare.your-domain.com/telegram

# 5. Telegram bot config
# In @BotFather, /setprivacy → Disable (so the bot can read group messages)
```

## Commands

All commands assume you're in the repo root with the venv activated.

### Run the app

```bash
# Activate venv (do this once per terminal)
source .venv/bin/activate

# Terminal 1 — Cloudflare tunnel (gives Telegram a stable HTTPS URL pointing at localhost:8000)
cloudflared tunnel --url http://localhost:8000
or
cloudflared tunnel run aicare --url http://localhost:8000

# Terminal 2 — FastAPI app (owns the PTB Application + APScheduler lifecycle)
uvicorn main:app --reload --port 8000
```

On startup the app: initializes the Telegram Application → starts APScheduler with the SQLAlchemy job store → re-registers cron jobs for every active medication and every active family's weekly Monday update + daily check-in + Friday digest → idempotently registers the webhook with Telegram. Open `http://localhost:8000/admin/<family_id>` for the admin dashboard.

### Cloudflare tunnel (one-time setup)

```bash
# Auth + create the named tunnel (only needed once per machine)
cloudflared tunnel login
cloudflared tunnel create aicare

# Bind a stable hostname (also one-time)
cloudflared tunnel route dns aicare aicare.your-domain.com

# Set WEBHOOK_URL in .env to https://aicare.your-domain.com/telegram
```

After that, `cloudflared tunnel run aicare --url http://localhost:8000` is the only command you need on each session.

### Demo + dev scripts

```bash
# Spine smoke test — fires the full reminder → miss → escalation → check-back loop
# without wall-clock waits. Stop the main app first or run separately.
python scripts/fire_demo.py --fast --missed     # missed-confirmation path (full escalation)
python scripts/fire_demo.py --fast              # happy path (parent confirms before window)
python scripts/fire_demo.py                     # real timings (~15 + 12 min, slow)

# Pre-warm TTS cache — writes ~10 demo phrases to cache/audio/<sha256>.ogg
# so demo day has zero live ElevenLabs calls. Run the night before.
python scripts/prewarm_audio.py

# Seed 30 days of fake history — 2 medications (twice + thrice daily),
# realistic adherence distribution, recurring + new-onset symptom patterns.
# Useful for screenshots and for making the GP briefing have something to say.
python scripts/seed_history.py                  # add to existing data
python scripts/seed_history.py --clear          # wipe meds + events + doses first
python scripts/seed_history.py --seed 7         # different RNG seed (default 42)
```

### Live debugging cheats

- **Reset history** (Settings → Danger zone) — wipes events + conversations + dose history + cached briefing PDFs for the current family. Config (caregivers, meds, rotation, tokens) untouched. Useful between rehearsals.
- **`DEMO_MODE_FAST_FORWARD=true`** in `.env` — shrinks confirmation window (15 min → 1 min) and check-back offset (12 min → 1 min) so the full loop fits in <5 minutes. Restart after changing.
- **`VOICE_DISABLED=true`** in `.env` — skips ElevenLabs entirely. Aunty May sends and accepts plain text. Saves quota during dev.

## Onboarding a real family

Two things must be true before the agent will fire reminders:

1. **Parent handshake done** — caregiver clicks "Generate handshake" in Settings, parent taps the deep link, replies *yes* to "Are you Mdm Lim?". This sets `families.parent_user_id`.
2. **Family group linked** — caregiver adds the bot to the family group, runs `/linkfamily <6-digit-code>` (code generated alongside the handshake). This sets `families.group_chat_id`.

Without both, the family is `inactive_missing_fields` and all scheduled jobs early-return.

For demo setups skipping the real handshake, you can patch the rows directly in the Supabase SQL Editor — see `scripts/fire_demo.py` docstring for the exact columns to set.

## Adding appointments

Settings page → **Appointments** section → **Upload .ics calendar file**. Anything RFC-5545 compliant works (HealthHub export, Google Calendar export, Outlook export). Each VEVENT is upserted by UID, so re-uploading the same file is idempotent. Past events are skipped automatically. All future appointments show up in the next Monday-morning weekly update + can be deleted individually from the UI.

## Demo prep checklist

The night before:

```bash
python scripts/prewarm_audio.py                 # cache TTS → no live ElevenLabs calls on stage
python scripts/seed_history.py --clear          # populate the dashboard with realistic history
python scripts/fire_demo.py --fast --missed     # confirm the spine still works end-to-end
```

What the smoke test covers:
- Reminder voice/text → parent DM
- Window close (1 min in `--fast` mode) → miss logged → escalation post in group
- Check-back voice/text → parent DM
- `/digest` output

What it doesn't cover:
- ✓ Sent callback (needs the live webhook running — restart the app and tap the button manually)

## Environment variables

```
# Telegram
TELEGRAM_BOT_TOKEN=     # from @BotFather
BOT_USERNAME=           # your bot's username, without the @
WEBHOOK_URL=            # https://your-tunnel.com/telegram
WEBHOOK_SECRET_TOKEN=   # any random string; Telegram echoes it back so we can reject spoofed updates

# LLM + voice
OPENAI_API_KEY=
ELEVENLABS_API_KEY=
AUNTY_MAY_VOICE_ID=     # pick from elevenlabs.io/voice-library

# Data
SUPABASE_URL=
SUPABASE_SERVICE_KEY=                    # service-role key, NOT anon
DATABASE_URL=                            # postgresql+psycopg://… port 5432 (Session, NOT pooler 6543)

# Behaviour
TZ=Asia/Singapore
CONFIRMATION_WINDOW_MIN=15               # how long to wait before logging a miss
CHECK_BACK_OFFSET_MIN=12                 # delay after escalation before Aunty May follows up
DEMO_MODE_FAST_FORWARD=false             # set true to shrink windows to ~1 min for rehearsal
VOICE_DISABLED=false                     # set true to skip ElevenLabs entirely (text in/out instead)

# Demo seeds
DEMO_FAMILY_ID=                          # family uuid for fire_demo.py + the / route on /admin
```

## Architecture

```
Telegram (webhook) ─┐
                    ├─► FastAPI (main.py)
cloudflared tunnel ─┘    │
                         ├─► python-telegram-bot Application
                         │     - parent voice / text handler  (handlers_parent.py)
                         │     - group ✓ Sent callback         (group_post.py)
                         │     - /setup, /linkfamily wizard    (onboarding.py)
                         │
                         ├─► APScheduler (SQLAlchemyJobStore on Postgres)
                         │     - med_reminder_due
                         │     - confirmation_window_close
                         │     - check_back_due
                         │     - weekly_report (Mon 06:00 → group, configurable)
                         │     - symptom_diary_due (20:00 → parent)
                         │     - weekly_digest (Fri 18:00)
                         │
                         ├─► OpenAI: classify (gpt-4o-mini) + decide (gpt-4o) + briefing (gpt-4o)
                         ├─► ElevenLabs: STT (Scribe) + TTS (Multilingual v2)
                         └─► Supabase: 11 tables, family_id-scoped, service-role key
```

**Adherence is computed from `dose_instances`, not events.** Each scheduled slot creates a dose row when the reminder fires; lifecycle is `pending → confirmed | missed_unresolved → missed_resolved` (the last when a parent confirms after the window closed). Events stay as the append-only audit log + briefing source.

## Repo layout

```
main.py                 # uvicorn entry → FastAPI app
supabase/schema.sql     # full schema, run once
supabase/seed.sql       # demo family
scripts/                # fire_demo.py + prewarm_audio.py + seed_history.py
app/
  config.py             # pydantic-settings
  server/
    webhook.py          # FastAPI app + PTB lifecycle
    admin.py            # admin dashboard (Home / Medications / Logs / Settings)
  bot/
    app.py              # PTB Application + handler registration
    onboarding.py       # /setup, /linkfamily, atomic token claim
    handlers_parent.py  # guarded voice/text pipeline + urgent-symptom safety
    group_post.py       # escalation + ✓ Sent callback with JIT user link
    digest.py           # weekly Friday digest
    med_timing.py       # closest_slot / classify_timing
    ics_ingest.py       # parse .ics → appointment dicts (UTF-8 + Win-1252 fallback,
                        #   all-day events, sha256 UID fallback)
  voice/
    tts.py              # ElevenLabs Multilingual v2 + audio_cache
    stt.py              # ElevenLabs Scribe
    send.py             # send_to_parent abstraction (voice or text mode)
  llm/
    classify.py         # gpt-4o-mini intent classifier
    decide.py           # gpt-4o response planner
    prompts.py          # all system prompts
    memory.py           # last-N turns from conversations table
  scheduler/
    scheduler.py        # AsyncIOScheduler + SQLAlchemyJobStore
    jobs.py             # 7 cron handlers
  briefing/
    compile.py          # 6-week event window + dose_outcomes → markdown
    render.py           # markdown → PDF via reportlab
    storage.py          # local cache, served at /briefings/<token>.pdf
  db/                   # one repo module per table
    families.py
    users.py
    medication.py       # singular — table renamed post-MVP
    rotation.py
    events.py
    doses.py            # canonical adherence state
    conversations.py
    tokens.py
    appointments.py
    setup_sessions.py
```

## Troubleshooting

- **Bot doesn't reply** — check the bot is added to the group, privacy mode is disabled in BotFather, and `WEBHOOK_URL` matches the cloudflared tunnel hostname (with `/telegram` suffix).
- **`set_webhook failed`** in startup logs — usually means the URL or secret token is wrong. Hit `https://api.telegram.org/bot<TOKEN>/getWebhookInfo` to see what Telegram has stored.
- **`column daily_report_time does not exist`** — your DB pre-dates that column. Run `ALTER TABLE families ADD COLUMN IF NOT EXISTS daily_report_time time DEFAULT '06:00';` then restart. (The column name is now legacy: it controls the *weekly* Monday-morning report time. Renaming the column would just trigger another migration; the UI label already reads "Weekly report time".)
- **Stale `daily_report:*` jobs from before the weekly rename** — auto-cleaned at startup by `register_all_family_crons`. If you see duplicates, just restart the app once.
- **.ics file won't parse** — the parser handles single VEVENTs with UTF-8 or Windows-1252 encoding. RRULE expansion is not implemented yet — recurring events will only register the master event date. If a polyclinic export fails, share the file and we'll diagnose.
- **Adherence shows weird counts** — Settings → Reset history wipes events + conversations + doses for the current family without touching config.
- **TTS fails on demo day** — pre-warm runs out of date if you change voice ID or text. Re-run `prewarm_audio.py`. Cache files live at `cache/audio/<sha256>.ogg`.
- **APScheduler complains about prepared statements** — your `DATABASE_URL` is pointing at the PgBouncer pooler (port 6543). Switch to the Session DSN (port 5432).
