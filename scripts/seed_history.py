"""Seed 30 days of realistic history for the demo family.

What it creates:
  - 2 medications: Atorvastatin (twice daily) + Metformin (three times daily)
  - Per-day dose_instances + matching med_reminder_sent / med_confirmed / med_missed
    events with realistic adherence (~88% on time, 5% early, 4% late recovery, 3% missed)
  - ~Daily symptom_entry events from the evening check-in, including:
      * Recurring "Knee pain when walking" (appears across the whole window)
      * New-onset "Feeling dizzy when standing up" (only last 14 days)
      * Background varied symptoms
  - Conversation turns (parent ↔ Aunty May) for every confirm + symptom event,
    so the Logs page → Conversations tab has lived-in content. Skipped if the
    parent user has no telegram_chat_id (no DM thread to attach turns to).

Usage:
    python scripts/seed_history.py                # add to existing data
    python scripts/seed_history.py --clear        # wipe events + doses + meds + convos first

Reads DEMO_FAMILY_ID from .env. Won't run if the family doesn't exist.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from tqdm import tqdm

from app.config import settings
from app.db import doses as doses_repo
from app.db import events as events_repo
from app.db import families as families_repo
from app.db import medication as medication_repo
from app.db import users as users_repo
from app.db.client import get_client

LOCAL_TZ = ZoneInfo("Asia/Singapore")
DAYS = 30

MEDS = [
    {
        "name": "Atorvastatin",
        "dose": "20mg",
        "times": ["08:00", "20:00"],
    },
    {
        "name": "Metformin",
        "dose": "500mg",
        "times": ["08:00", "13:00", "19:00"],
    },
]

# Symptom pool. (text, language) — text mirrors what STT would have transcribed.
RECURRING = [
    "Knee pain when walking up stairs again today.",
    "My right knee is hurting when I walk.",
    "Knee bothering me again, especially after sitting too long.",
    "Walking is uncomfortable, knee is sore.",
    "Knee pain woke me up last night.",
]
NEW_ONSET = [
    "I felt a little dizzy when I stood up just now.",
    "Got a bit lightheaded standing up from the chair.",
    "Feeling dizzy when I get out of bed.",
    "Stood up too fast, head spun a little.",
]
BACKGROUND = [
    "Slept okay but feeling tired this morning.",
    "Slight headache on and off today.",
    "Lower back is a bit stiff today.",
    "Eyes feel dry, hard to focus on the TV.",
    "A bit constipated, drank more water.",
    "Cold feet at night, used extra blanket.",
    "Appetite was fine, ate proper rice and soup.",
    "Hand felt a bit shaky when holding the cup this morning.",
    "Took a short walk around the void deck, weather was good.",
    "Watched my drama, no problems.",
    "Felt fine today, nothing to report.",
]

# --- Conversation seed material ---
# Parent's turn when confirming a med (mix of Mandarin + English code-switch).
PARENT_CONFIRM_ON_TIME = [
    "吃了, 早餐也吃了.",
    "Ate already lah.",
    "Took it just now.",
    "Yes yes, drank with my coffee.",
    "已经吃了, 谢谢.",
]
PARENT_CONFIRM_LATE = [
    "Ate just now, sorry late.",
    "刚刚才记得, 不好意思.",
    "Took it already, my fault forgot.",
    "Eaten lah, sibei busy this morning.",
]
PARENT_CONFIRM_EARLY = [
    "Took it earlier with breakfast.",
    "Already ate lah, I take very early today.",
    "Done already, took it with my porridge.",
]

# Aunty May's reply pool — warm, brief, sometimes Mandarin, never clinical.
AUNTY_ON_TIME = [
    "Good Auntie, well done. 记得喝多点水, ok?",
    "好棒 Auntie! Glad you remembered.",
    "Nice nice, on time today. 我帮你记下来了.",
    "Got it, Auntie — noted. 继续保持哦.",
    "Perfect, marked it down. Have a good day, Auntie.",
]
AUNTY_LATE = [
    "Aiyo no problem Auntie, glad you remembered. 我告诉 Sarah 一声.",
    "Okay okay, took it is good. Don't worry, I'll let your daughter know.",
    "好的 Auntie, recorded. Next time set alarm together, ok?",
    "Noted. Better late than skip, Auntie. Take care.",
]
AUNTY_EARLY = [
    "Took early ah Auntie, no problem this time. 下次最好等到 8 点哦.",
    "Okay noted. Try to take around the same time daily, ok?",
    "Got it Auntie. Just be careful not to take too early next round.",
]
AUNTY_SYMPTOM_GENERIC = [
    "I hear you Auntie, I'll note this down for the next polyclinic visit.",
    "Okay Auntie, noted. 我告诉 Sarah, see what Dr Tan says.",
    "Thank you for telling me, Auntie. I'll keep track for you.",
    "Got it. Rest a bit, drink some warm water, ok?",
]
AUNTY_SYMPTOM_RECURRING_KNEE = [
    "Knee acting up again ah Auntie. I'll add this to the notes for Dr Tan — that's a few times now.",
    "Aiyo your knee. 我帮你记下来, also tell Sarah so she can mention at the GP.",
    "Noted Auntie, knee pain again. Better to bring this up at the next visit.",
]
AUNTY_SYMPTOM_NEW_ONSET_DIZZY = [
    "Dizzy when standing — okay Auntie, I'll flag this for Sarah and the GP. Be careful when getting up, hold on to something first.",
    "Thanks for telling me Auntie. Take it slow when standing up, and I'll let your daughter know about the dizziness.",
    "Important to mention, Auntie. 头晕站起来 — 我帮你 note down 给 Dr Tan.",
]


def _utc_iso(dt_local: datetime) -> str:
    """Convert a tz-aware local datetime to UTC ISO."""
    return dt_local.astimezone(timezone.utc).isoformat()


async def _insert_event(
    family_id: str,
    type_: str,
    payload: dict,
    *,
    medication_id: str | None,
    created_at: datetime,
) -> dict:
    """Insert an event with an explicit created_at (for backfill)."""
    client = await get_client()
    row = {
        "id": str(uuid4()),
        "family_id": str(family_id),
        "type": type_,
        "payload": payload,
        "created_at": _utc_iso(created_at),
    }
    if medication_id is not None:
        row["medication_id"] = str(medication_id)
    resp = await client.table("events").insert(row).execute()
    return resp.data[0]


async def _insert_dose(
    family_id: str,
    medication_id: str,
    *,
    scheduled_at: datetime,
    slot: str,
    status: str,
    timing: str | None,
    reminder_event_id: str | None,
    confirm_event_id: str | None,
    miss_event_id: str | None,
    confirmed_at: datetime | None,
    missed_at: datetime | None,
) -> dict:
    client = await get_client()
    row = {
        "id": str(uuid4()),
        "family_id": str(family_id),
        "medication_id": str(medication_id),
        "scheduled_at": _utc_iso(scheduled_at),
        "slot": slot,
        "status": status,
        "created_at": _utc_iso(scheduled_at),
        "updated_at": _utc_iso(scheduled_at),
    }
    if timing:
        row["timing"] = timing
    if reminder_event_id:
        row["reminder_event_id"] = reminder_event_id
    if confirm_event_id:
        row["confirm_event_id"] = confirm_event_id
    if miss_event_id:
        row["miss_event_id"] = miss_event_id
    if confirmed_at:
        row["confirmed_at"] = _utc_iso(confirmed_at)
    if missed_at:
        row["missed_at"] = _utc_iso(missed_at)
    resp = await client.table("dose_instances").insert(row).execute()
    return resp.data[0]


async def _insert_conversation(
    family_id: str,
    chat_id: int,
    speaker_role: str,
    text: str,
    *,
    speaker_user_id: str | None,
    language_code: str | None,
    created_at: datetime,
) -> None:
    """Insert a conversation turn with explicit created_at (for backfill)."""
    client = await get_client()
    row: dict = {
        "id": str(uuid4()),
        "family_id": str(family_id),
        "chat_id": chat_id,
        "speaker_role": speaker_role,
        "text": text,
        "created_at": _utc_iso(created_at),
    }
    if speaker_user_id is not None:
        row["speaker_user_id"] = str(speaker_user_id)
    if language_code is not None:
        row["language_code"] = language_code
    await client.table("conversations").insert(row).execute()


async def _seed_exchange(
    family_id: str,
    chat_id: int | None,
    parent_user_id: str | None,
    parent_text: str,
    aunty_text: str,
    *,
    when: datetime,
    language_code: str = "en",
) -> None:
    """Helper: parent turn at `when`, Aunty May reply 30s later. No-op if no chat_id."""
    if not chat_id or not parent_user_id:
        return
    await _insert_conversation(
        family_id,
        chat_id,
        "parent",
        parent_text,
        speaker_user_id=parent_user_id,
        language_code=language_code,
        created_at=when,
    )
    await _insert_conversation(
        family_id,
        chat_id,
        "aunty_may",
        aunty_text,
        speaker_user_id=None,
        language_code=language_code,
        created_at=when + timedelta(seconds=30),
    )


async def _clear_family(family_id: str) -> None:
    """Wipe conversations + events + dose_instances + medications for a clean re-seed."""
    client = await get_client()
    print("clearing existing conversations / events / doses / medications…")
    await client.table("conversations").delete().eq("family_id", str(family_id)).execute()
    await client.table("dose_instances").delete().eq("family_id", str(family_id)).execute()
    await client.table("events").delete().eq("family_id", str(family_id)).execute()
    await client.table("medication").delete().eq("family_id", str(family_id)).execute()


def _pick_dose_outcome(rng: random.Random) -> tuple[str, str | None]:
    """Return (status, timing) sampled from realistic adherence distribution."""
    r = rng.random()
    if r < 0.88:
        return "confirmed", "on_time"
    if r < 0.93:
        return "confirmed", "early"
    if r < 0.97:
        return "missed_resolved", "late"  # missed window, took it after
    return "missed_unresolved", None


def _pick_symptom(rng: random.Random, day_idx_from_today: int) -> str | None:
    """Returns a symptom transcript or None for a quiet day. Newer days more likely
    to surface the new-onset signal."""
    if rng.random() < 0.30:
        return None  # quiet day — no symptom check-in entry
    weights = [
        ("recurring", 25),
        ("background", 65),
        # New-onset only appears in the last 14 days (today is day 0)
        ("new_onset", 10 if day_idx_from_today < 14 else 0),
    ]
    bucket = rng.choices(
        [w[0] for w in weights], weights=[w[1] for w in weights], k=1
    )[0]
    if bucket == "recurring":
        return rng.choice(RECURRING)
    if bucket == "new_onset":
        return rng.choice(NEW_ONSET)
    return rng.choice(BACKGROUND)


async def main(clear: bool, seed: int) -> None:
    family_id = settings.demo_family_id
    if not family_id:
        print("ERROR: DEMO_FAMILY_ID not set in .env", file=sys.stderr)
        sys.exit(1)
    family = await families_repo.get(family_id)
    if not family:
        print(f"ERROR: family {family_id} not found", file=sys.stderr)
        sys.exit(1)

    rng = random.Random(seed)

    if clear:
        await _clear_family(family_id)

    # Look up the parent — needed for conversations.speaker_user_id + chat_id.
    # If the parent isn't linked yet (no chat_id), conversation seeding is skipped
    # but everything else still runs.
    parent_user_id: str | None = None
    parent_chat_id: int | None = None
    if family.get("parent_user_id"):
        parent = await users_repo.by_id(family["parent_user_id"])
        if parent:
            parent_user_id = parent["id"]
            parent_chat_id = parent.get("telegram_chat_id")
    if not parent_chat_id:
        print(
            "  note: parent has no telegram_chat_id — skipping conversation seeding"
        )

    # Create the 2 medications
    print("creating medications…")
    meds = []
    for spec in MEDS:
        m = await medication_repo.create(
            family_id, spec["name"], spec["dose"], spec["times"]
        )
        meds.append(m)
        print(f"  + {m['name']} {m['dose']} @ {', '.join(spec['times'])}")

    today_local = datetime.now(LOCAL_TZ).replace(microsecond=0)
    confirmation_window_min = settings.confirmation_window_min

    dose_count = 0
    symptom_count = 0
    convo_count = 0
    progress = tqdm(range(DAYS, 0, -1), desc="seeding", unit="day")
    for d in progress:
        # day 1 = yesterday, day DAYS = ~30 days ago
        day_local = (today_local - timedelta(days=d)).replace(
            hour=0, minute=0, second=0
        )
        day_idx_from_today = d  # for symptom new-onset gating
        progress.set_postfix_str(day_local.strftime("%a %d %b"))

        # --- Doses for each med slot on this day ---
        for med in meds:
            for slot in med["times"]:
                # DB roundtrips time[] as 'HH:MM:SS' — split and take the first two parts.
                parts = str(slot).split(":")
                hh, mm = int(parts[0]), int(parts[1])
                slot_hhmm = f"{hh:02d}:{mm:02d}"
                scheduled_at = day_local.replace(hour=hh, minute=mm)

                # Reminder event (always logged when reminder fires)
                reminder_evt = await _insert_event(
                    family_id,
                    "med_reminder_sent",
                    {
                        "medication_id": med["id"],
                        "scheduled_time": _utc_iso(scheduled_at),
                    },
                    medication_id=med["id"],
                    created_at=scheduled_at,
                )

                status, timing = _pick_dose_outcome(rng)

                if status == "confirmed":
                    # Confirmed within window. Pick a delta based on timing bucket.
                    if timing == "on_time":
                        offset_min = rng.randint(-3, 12)
                    elif timing == "early":
                        offset_min = rng.randint(-90, -65)
                    else:  # late (rare without going through missed flow)
                        offset_min = rng.randint(70, 110)
                    confirmed_at = scheduled_at + timedelta(minutes=offset_min)
                    confirm_evt = await _insert_event(
                        family_id,
                        "med_confirmed",
                        {
                            "medication_id": med["id"],
                            "transcript": "(seeded) ate already",
                            "confidence": 1.0,
                            "source": "parent_voice",
                            "timing": timing,
                            "slot": slot_hhmm,
                            "delta_min": offset_min,
                        },
                        medication_id=med["id"],
                        created_at=confirmed_at,
                    )
                    await _insert_dose(
                        family_id,
                        med["id"],
                        scheduled_at=scheduled_at,
                        slot=slot_hhmm,
                        status="confirmed",
                        timing=timing,
                        reminder_event_id=reminder_evt["id"],
                        confirm_event_id=confirm_evt["id"],
                        miss_event_id=None,
                        confirmed_at=confirmed_at,
                        missed_at=None,
                    )
                    if parent_chat_id:
                        if timing == "early":
                            parent_text = rng.choice(PARENT_CONFIRM_EARLY)
                            aunty_text = rng.choice(AUNTY_EARLY)
                        else:
                            parent_text = rng.choice(PARENT_CONFIRM_ON_TIME)
                            aunty_text = rng.choice(AUNTY_ON_TIME)
                        await _seed_exchange(
                            family_id,
                            parent_chat_id,
                            parent_user_id,
                            parent_text,
                            aunty_text,
                            when=confirmed_at,
                        )
                        convo_count += 2

                elif status == "missed_resolved":
                    # Window closed → miss logged → escalation → parent took it within ~2h
                    missed_at = scheduled_at + timedelta(minutes=confirmation_window_min)
                    miss_evt = await _insert_event(
                        family_id,
                        "med_missed",
                        {
                            "medication_id": med["id"],
                            "reminder_event_id": reminder_evt["id"],
                            "window_min": confirmation_window_min,
                        },
                        medication_id=med["id"],
                        created_at=missed_at,
                    )
                    # Escalation post (group-side; we just log the event for completeness)
                    await _insert_event(
                        family_id,
                        "escalation_posted",
                        {
                            "reminder_event_id": reminder_evt["id"],
                            "group_message_id": 0,
                            "pattern_count": 1,
                        },
                        medication_id=med["id"],
                        created_at=missed_at + timedelta(seconds=2),
                    )
                    confirmed_at = missed_at + timedelta(
                        minutes=rng.randint(20, 90)
                    )
                    confirm_evt = await _insert_event(
                        family_id,
                        "med_confirmed",
                        {
                            "medication_id": med["id"],
                            "transcript": "(seeded) ate just now",
                            "confidence": 1.0,
                            "source": "parent_voice",
                            "timing": "late",
                            "slot": slot_hhmm,
                            "delta_min": int(
                                (confirmed_at - scheduled_at).total_seconds() / 60
                            ),
                        },
                        medication_id=med["id"],
                        created_at=confirmed_at,
                    )
                    await _insert_dose(
                        family_id,
                        med["id"],
                        scheduled_at=scheduled_at,
                        slot=slot_hhmm,
                        status="missed_resolved",
                        timing="late",
                        reminder_event_id=reminder_evt["id"],
                        confirm_event_id=confirm_evt["id"],
                        miss_event_id=miss_evt["id"],
                        confirmed_at=confirmed_at,
                        missed_at=missed_at,
                    )
                    if parent_chat_id:
                        await _seed_exchange(
                            family_id,
                            parent_chat_id,
                            parent_user_id,
                            rng.choice(PARENT_CONFIRM_LATE),
                            rng.choice(AUNTY_LATE),
                            when=confirmed_at,
                        )
                        convo_count += 2

                else:  # missed_unresolved
                    missed_at = scheduled_at + timedelta(minutes=confirmation_window_min)
                    miss_evt = await _insert_event(
                        family_id,
                        "med_missed",
                        {
                            "medication_id": med["id"],
                            "reminder_event_id": reminder_evt["id"],
                            "window_min": confirmation_window_min,
                        },
                        medication_id=med["id"],
                        created_at=missed_at,
                    )
                    await _insert_event(
                        family_id,
                        "escalation_posted",
                        {
                            "reminder_event_id": reminder_evt["id"],
                            "group_message_id": 0,
                            "pattern_count": 1,
                        },
                        medication_id=med["id"],
                        created_at=missed_at + timedelta(seconds=2),
                    )
                    await _insert_dose(
                        family_id,
                        med["id"],
                        scheduled_at=scheduled_at,
                        slot=slot_hhmm,
                        status="missed_unresolved",
                        timing=None,
                        reminder_event_id=reminder_evt["id"],
                        confirm_event_id=None,
                        miss_event_id=miss_evt["id"],
                        confirmed_at=None,
                        missed_at=missed_at,
                    )
                dose_count += 1

        # --- Symptom from evening check-in (~70% of days) ---
        symptom_text = _pick_symptom(rng, day_idx_from_today)
        if symptom_text:
            symptom_at = day_local.replace(hour=20, minute=rng.randint(0, 30))
            await _insert_event(
                family_id,
                "symptom_entry",
                {
                    "symptom_text": symptom_text,
                    "transcript": symptom_text,
                    "language_code": "en",
                    "confidence": 0.95,
                },
                medication_id=None,
                created_at=symptom_at,
            )
            symptom_count += 1
            if parent_chat_id:
                if symptom_text in RECURRING:
                    aunty_text = rng.choice(AUNTY_SYMPTOM_RECURRING_KNEE)
                elif symptom_text in NEW_ONSET:
                    aunty_text = rng.choice(AUNTY_SYMPTOM_NEW_ONSET_DIZZY)
                else:
                    aunty_text = rng.choice(AUNTY_SYMPTOM_GENERIC)
                await _seed_exchange(
                    family_id,
                    parent_chat_id,
                    parent_user_id,
                    symptom_text,
                    aunty_text,
                    when=symptom_at,
                )
                convo_count += 2

    print(
        f"\nseeded {dose_count} dose_instances + {symptom_count} symptoms "
        f"+ {convo_count} conversation turns across {DAYS} days"
    )
    print(
        "tip: open /admin/<family_id>/logs to see the timeline + adherence cards "
        "and /admin/<family_id>/medications for the new meds"
    )
    print(
        "  → restart the app (or hit Settings → Reset history) so cron jobs sync "
        "with the new medication rows"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "--clear",
        action="store_true",
        help="Wipe existing events + dose_instances + medications for the family before seeding",
    )
    p.add_argument(
        "--seed", type=int, default=42, help="RNG seed for reproducible runs"
    )
    args = p.parse_args()
    asyncio.run(main(clear=args.clear, seed=args.seed))
