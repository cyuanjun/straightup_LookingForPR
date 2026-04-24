-- AI care — Supabase schema
-- Run this once in the Supabase SQL Editor, then run seed.sql for demo data.
--
-- Design notes:
-- * Service-role key bypasses RLS. Backend code enforces family_id scoping.
--   RLS policies here are defense-in-depth for future anon/user-scoped clients.
-- * Mutually-referential FKs on families (parent_user_id, primary_caregiver_user_id)
--   are added AFTER users is created. Both are nullable at schema level;
--   application logic enforces the "active family" invariant:
--     parent_user_id + primary_caregiver_user_id + group_chat_id all SET.

BEGIN;

--------------------------------------------------------------------------------
-- Extensions
--------------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;

--------------------------------------------------------------------------------
-- Enums
--------------------------------------------------------------------------------
CREATE TYPE user_role AS ENUM ('parent', 'caregiver');

CREATE TYPE event_type AS ENUM (
    'med_reminder_sent',
    'parent_reply_transcribed',
    'med_confirmed',
    'partial_confirm',
    'symptom_entry',
    'clinical_question_deferred',
    'distress_escalated',
    'urgent_symptom_escalated',
    'med_missed',
    'escalation_posted',
    'nudge_sent_by_caregiver',
    'check_back_sent',
    'appointment_reminder_sent',
    'weekly_digest_sent',
    'briefing_generated',
    'parent_optout'
);

CREATE TYPE speaker_role AS ENUM ('parent', 'aunty_may', 'system');

CREATE TYPE token_purpose AS ENUM ('parent_handshake', 'group_linking');
CREATE TYPE token_status  AS ENUM ('pending_confirm', 'confirmed', 'expired');

--------------------------------------------------------------------------------
-- families
--------------------------------------------------------------------------------
CREATE TABLE families (
    id                         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    group_chat_id              bigint,                             -- populated via /linkfamily
    parent_user_id             uuid,                               -- FK added below
    primary_caregiver_user_id  uuid,                               -- FK added below
    timezone                   text        DEFAULT 'Asia/Singapore',
    languages                  text,                               -- e.g. 'zh+en'
    symptom_diary_time         time        DEFAULT '20:00',
    paused                     boolean     DEFAULT false,
    created_at                 timestamptz DEFAULT now()
);

--------------------------------------------------------------------------------
-- users
--------------------------------------------------------------------------------
CREATE TABLE users (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id         uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    telegram_user_id  bigint,
    telegram_chat_id  bigint,
    telegram_username text,
    display_name      text NOT NULL,
    role              user_role NOT NULL
);

-- Partial unique index: only uniqueness-enforced when telegram_user_id is present
CREATE UNIQUE INDEX users_telegram_user_id_unique
    ON users (telegram_user_id)
    WHERE telegram_user_id IS NOT NULL;

CREATE INDEX users_family_role_idx ON users (family_id, role);

--------------------------------------------------------------------------------
-- Circular FKs on families, added after users is created
--------------------------------------------------------------------------------
ALTER TABLE families
    ADD CONSTRAINT families_parent_user_id_fk
        FOREIGN KEY (parent_user_id) REFERENCES users(id) ON DELETE SET NULL,
    ADD CONSTRAINT families_primary_caregiver_user_id_fk
        FOREIGN KEY (primary_caregiver_user_id) REFERENCES users(id) ON DELETE SET NULL;

--------------------------------------------------------------------------------
-- medications
--------------------------------------------------------------------------------
CREATE TABLE medications (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id  uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    name       text NOT NULL,
    dose       text NOT NULL,
    times      time[] NOT NULL,                    -- fixed daily times only (MVP)
    active     boolean DEFAULT true
);

CREATE INDEX medications_family_active_idx ON medications (family_id, active);

--------------------------------------------------------------------------------
-- rotation
--------------------------------------------------------------------------------
CREATE TABLE rotation (
    family_id    uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    day_of_week  int  NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),  -- 0 = Sun
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (family_id, day_of_week)
);

--------------------------------------------------------------------------------
-- events (append-only log; feeds /digest, briefing, patterns)
--------------------------------------------------------------------------------
CREATE TABLE events (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id      uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    type           event_type NOT NULL,
    payload        jsonb DEFAULT '{}'::jsonb,
    attributed_to  uuid REFERENCES users(id) ON DELETE SET NULL,       -- actor
    medication_id  uuid REFERENCES medications(id) ON DELETE SET NULL,
    created_at     timestamptz DEFAULT now()
);

CREATE INDEX events_family_created_idx       ON events (family_id, created_at DESC);
CREATE INDEX events_family_type_created_idx  ON events (family_id, type, created_at DESC);
CREATE INDEX events_family_attributed_idx    ON events (family_id, attributed_to, type, created_at DESC);

--------------------------------------------------------------------------------
-- pending_tokens (parent handshake + group linking, single table)
--------------------------------------------------------------------------------
CREATE TABLE pending_tokens (
    token               text PRIMARY KEY,
    family_id           uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    purpose             token_purpose NOT NULL,
    setup_code          text,                    -- 6-digit, for group_linking only
    created_by_user_id  uuid REFERENCES users(id) ON DELETE SET NULL,
    claimed_by          bigint,                  -- telegram_user_id (parent flow only)
    status              token_status NOT NULL DEFAULT 'pending_confirm',
    expires_at          timestamptz NOT NULL,
    consumed_at         timestamptz,
    created_at          timestamptz DEFAULT now(),

    CONSTRAINT parent_handshake_requires_token
        CHECK (purpose <> 'parent_handshake' OR length(token) >= 22),
    CONSTRAINT group_linking_requires_setup_code
        CHECK (purpose <> 'group_linking' OR setup_code ~ '^[0-9]{6}$')
);

-- Prevent two live setup codes colliding; generator retries on conflict
CREATE UNIQUE INDEX pending_tokens_active_setup_code_unique
    ON pending_tokens (setup_code)
    WHERE setup_code IS NOT NULL AND status = 'pending_confirm';

CREATE INDEX pending_tokens_family_purpose_status_idx
    ON pending_tokens (family_id, purpose, status);

--------------------------------------------------------------------------------
-- appointments (from .ics upload)
--------------------------------------------------------------------------------
CREATE TABLE appointments (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id  uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    uid        text NOT NULL,                    -- from .ics, or sha256 fallback
    starts_at  timestamptz NOT NULL,
    title      text,
    location   text,
    UNIQUE (family_id, uid)
);

CREATE INDEX appointments_family_starts_idx ON appointments (family_id, starts_at);

--------------------------------------------------------------------------------
-- audio_cache (local filesystem paths)
--------------------------------------------------------------------------------
CREATE TABLE audio_cache (
    text_hash   text PRIMARY KEY,                -- sha256(text || voice_id)
    voice_id    text NOT NULL,
    file_path   text NOT NULL,                   -- local filesystem path
    created_at  timestamptz DEFAULT now()
);

--------------------------------------------------------------------------------
-- conversations (Aunty May ↔ parent memory)
--------------------------------------------------------------------------------
CREATE TABLE conversations (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id        uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    chat_id          bigint NOT NULL,
    speaker_role     speaker_role NOT NULL,      -- DISTINCT enum from users.role
    speaker_user_id  uuid REFERENCES users(id) ON DELETE SET NULL,
    text             text NOT NULL,
    language_code    text,
    created_at       timestamptz DEFAULT now()
);

CREATE INDEX conversations_family_chat_created_idx
    ON conversations (family_id, chat_id, created_at DESC);

--------------------------------------------------------------------------------
-- setup_sessions (persistent /setup wizard progress)
--------------------------------------------------------------------------------
CREATE TABLE setup_sessions (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id          uuid NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    caregiver_user_id  uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    state              jsonb DEFAULT '{}'::jsonb,
    updated_at         timestamptz DEFAULT now(),
    UNIQUE (family_id, caregiver_user_id)
);

--------------------------------------------------------------------------------
-- Row-level security (defense-in-depth; service-role key bypasses these)
-- Real policies can be added later if anon-keyed clients are introduced.
--------------------------------------------------------------------------------
ALTER TABLE families        ENABLE ROW LEVEL SECURITY;
ALTER TABLE users           ENABLE ROW LEVEL SECURITY;
ALTER TABLE medications     ENABLE ROW LEVEL SECURITY;
ALTER TABLE rotation        ENABLE ROW LEVEL SECURITY;
ALTER TABLE events          ENABLE ROW LEVEL SECURITY;
ALTER TABLE pending_tokens  ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments    ENABLE ROW LEVEL SECURITY;
ALTER TABLE audio_cache     ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations   ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup_sessions  ENABLE ROW LEVEL SECURITY;

COMMIT;
