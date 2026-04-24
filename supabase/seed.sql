-- AI care — demo seed (Mdm Lim's family)
-- Run AFTER schema.sql.
--
-- After running this, set in .env:
--   DEMO_FAMILY_ID=11111111-1111-1111-1111-111111111111
--
-- Family is NOT active until three things happen:
--   1. A caregiver messages the bot (fills in their telegram_user_id / chat_id)
--   2. Caregiver adds bot to a Telegram group and runs /linkfamily <setup_code>
--      → populates families.group_chat_id
--   3. Parent completes the handshake (tapping the deep link + replying "yes")
--      → populates parent.telegram_user_id and families.parent_user_id stays set
--
-- Until then, @requires_active_family guards skip all scheduled jobs.

BEGIN;

-- Use fixed UUIDs so .env DEMO_FAMILY_ID stays stable across re-seeds.
INSERT INTO families (id, languages, symptom_diary_time)
VALUES (
    '11111111-1111-1111-1111-111111111111',
    'zh+en',
    '20:00'
);

-- Caregivers (telegram fields null until they interact with the bot)
INSERT INTO users (id, family_id, display_name, role)
VALUES
    ('22222222-2222-2222-2222-222222222222',
     '11111111-1111-1111-1111-111111111111',
     'Sarah',
     'caregiver'),
    ('33333333-3333-3333-3333-333333333333',
     '11111111-1111-1111-1111-111111111111',
     'Marcus',
     'caregiver');

-- Parent row (telegram fields null until handshake completes)
INSERT INTO users (id, family_id, display_name, role)
VALUES
    ('44444444-4444-4444-4444-444444444444',
     '11111111-1111-1111-1111-111111111111',
     'Mdm Lim',
     'parent');

-- Wire the family's FKs now that user rows exist
UPDATE families
SET parent_user_id            = '44444444-4444-4444-4444-444444444444',
    primary_caregiver_user_id = '22222222-2222-2222-2222-222222222222'
WHERE id = '11111111-1111-1111-1111-111111111111';

-- Demo medication: Lisinopril 10mg at 08:45 daily
INSERT INTO medication (family_id, name, dose, times)
VALUES (
    '11111111-1111-1111-1111-111111111111',
    'Lisinopril',
    '10mg',
    ARRAY['08:45']::time[]
);

-- Rotation: Marcus on Tuesday (day_of_week = 2)
INSERT INTO rotation (family_id, day_of_week, user_id)
VALUES (
    '11111111-1111-1111-1111-111111111111',
    2,
    '33333333-3333-3333-3333-333333333333'
);

COMMIT;

-- To activate the family for end-to-end demo without real Telegram handshake, patch:
--   UPDATE users SET telegram_user_id = <sarah_tg_id>, telegram_chat_id = <sarah_tg_id>
--     WHERE id = '22222222-2222-2222-2222-222222222222';
--   UPDATE users SET telegram_user_id = <marcus_tg_id>, telegram_chat_id = <marcus_tg_id>
--     WHERE id = '33333333-3333-3333-3333-333333333333';
--   UPDATE users SET telegram_user_id = <parent_tg_id>, telegram_chat_id = <parent_tg_id>
--     WHERE id = '44444444-4444-4444-4444-444444444444';
--   UPDATE families SET group_chat_id = <group_chat_id>
--     WHERE id = '11111111-1111-1111-1111-111111111111';
