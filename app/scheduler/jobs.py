"""Scheduled job handlers. All are gated by the unified active-family guard.

NOTE: APScheduler runs these in the same asyncio loop as the PTB Application.
They must be picklable, so they take only simple ID args and re-acquire clients
internally.
"""

from __future__ import annotations

import functools
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.bot.app import build_application
from app.bot.group_post import post_escalation
from app.config import settings
from app.db import events as events_repo
from app.db import families as families_repo
from app.db import medications as medications_repo
from app.voice.send import send_to_parent

log = logging.getLogger(__name__)


def requires_active_family(fn):
    """Decorator: check families state; only run fn if 'active'. Log skip otherwise."""

    @functools.wraps(fn)
    async def wrapper(family_id, *args, **kwargs):
        state = await families_repo.state(family_id)
        if state != "active":
            log.info(
                "Skipping %s for family %s — state=%s",
                fn.__name__,
                family_id,
                state,
            )
            return
        return await fn(family_id, *args, **kwargs)

    return wrapper


@requires_active_family
async def med_reminder_due(family_id: str, medication_id: str) -> None:
    """Voice reminder + schedule the confirmation-window close.

    Auto-cancel: if the parent has already confirmed this medication within the last
    60 minutes (e.g. they took it slightly early), suppress the reminder entirely so
    we don't nag them right after they just confirmed.
    """
    med = await medications_repo.by_id(medication_id)
    family = await families_repo.get(family_id)
    if not med or not family:
        return

    # Skip-if-already-confirmed guard (covers the "they ate it before we pinged them" case)
    recent = await events_repo.most_recent_confirmation(family_id, medication_id)
    if recent:
        last_ts = datetime.fromisoformat(recent["created_at"].replace("Z", "+00:00"))
        age_min = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60
        if age_min < 60:
            log.info(
                "med_reminder_due: skipping %s — parent confirmed %.1f min ago",
                medication_id,
                age_min,
            )
            return

    parent_user_id = family["parent_user_id"]
    from app.db import users as users_repo

    parent = await users_repo.by_id(parent_user_id)
    if not parent or not parent.get("telegram_chat_id"):
        log.warning("med_reminder_due: parent's telegram_chat_id not set for family %s", family_id)
        return

    # Reminder text — Mandarin if the family uses zh+en, else English
    languages = family.get("languages") or "zh+en"
    if "zh" in languages:
        text = f"早安啊 Auntie, 吃了早餐和{med['name']}吗?"
    else:
        text = f"Good morning Auntie, have you had your breakfast and {med['name']}?"

    app = build_application()
    await send_to_parent(app.bot, parent["telegram_chat_id"], text)

    reminder_event = await events_repo.insert(
        family_id,
        "med_reminder_sent",
        payload={
            "medication_id": medication_id,
            "scheduled_time": datetime.now(timezone.utc).isoformat(),
        },
        medication_id=medication_id,
    )

    # Schedule window-close
    window_min = 1 if settings.demo_mode_fast_forward else settings.confirmation_window_min
    from app.scheduler.scheduler import get_scheduler

    scheduler = get_scheduler()
    run_at = datetime.now(timezone.utc) + timedelta(minutes=window_min)
    scheduler.add_job(
        confirmation_window_close,
        "date",
        run_date=run_at,
        args=[family_id, medication_id, reminder_event["id"]],
        id=f"win_close:{reminder_event['id']}",
        replace_existing=True,
    )


@requires_active_family
async def confirmation_window_close(
    family_id: str, medication_id: str, reminder_event_id: str
) -> None:
    """If no med_confirmed event logged in the window, escalate to the family group."""
    # Look back to the reminder's timestamp
    reminder = await events_repo.by_id(reminder_event_id)
    if not reminder:
        return
    reminder_ts = datetime.fromisoformat(reminder["created_at"].replace("Z", "+00:00"))

    confirmed = await events_repo.had_confirmation_within_window(
        family_id, medication_id, since=reminder_ts
    )
    if confirmed:
        log.info("Confirmation present — no escalation for reminder %s", reminder_event_id)
        return

    med = await medications_repo.by_id(medication_id)
    if not med:
        return

    miss_count = await events_repo.count_misses_this_week(family_id, medication_id) + 1

    await events_repo.insert(
        family_id,
        "med_missed",
        payload={
            "medication_id": medication_id,
            "reminder_event_id": reminder_event_id,
            "window_min": settings.confirmation_window_min,
        },
        medication_id=medication_id,
    )

    app = build_application()
    await post_escalation(app.bot, family_id, med, reminder_event_id, miss_count)

    # Schedule Aunty May's check-back
    offset_min = 1 if settings.demo_mode_fast_forward else settings.check_back_offset_min
    from app.scheduler.scheduler import get_scheduler

    scheduler = get_scheduler()
    run_at = datetime.now(timezone.utc) + timedelta(minutes=offset_min)
    scheduler.add_job(
        check_back_due,
        "date",
        run_date=run_at,
        args=[family_id, medication_id],
        id=f"check_back:{reminder_event_id}",
        replace_existing=True,
    )


@requires_active_family
async def check_back_due(family_id: str, medication_id: str) -> None:
    """Aunty May follows up gently with the parent."""
    from app.db import users as users_repo

    family = await families_repo.get(family_id)
    med = await medications_repo.by_id(medication_id)
    if not family or not med:
        return

    parent = await users_repo.by_id(family["parent_user_id"])
    if not parent or not parent.get("telegram_chat_id"):
        return

    languages = family.get("languages") or "zh+en"
    if "zh" in languages:
        text = f"Auntie, {med['name']} 吃了吗?"
    else:
        text = f"Auntie, have you taken your {med['name']}?"

    app = build_application()
    await send_to_parent(app.bot, parent["telegram_chat_id"], text)

    await events_repo.insert(
        family_id,
        "check_back_sent",
        payload={"medication_id": medication_id},
        medication_id=medication_id,
    )


async def sync_jobs_for_medication(medication_id: str) -> None:
    """After add / edit / deactivate, re-register cron jobs for a medication.

    Removes any existing med_reminder:{medication_id}:* jobs, then (if active) adds fresh ones.
    """
    from app.scheduler.scheduler import get_scheduler

    scheduler = get_scheduler()
    prefix = f"med_reminder:{medication_id}:"

    # Remove stale
    for job in list(scheduler.get_jobs()):
        if job.id.startswith(prefix):
            job.remove()

    med = await medications_repo.by_id(medication_id)
    if not med or not med.get("active"):
        return

    from apscheduler.triggers.cron import CronTrigger

    for time_str in med["times"] or []:
        # time_str may be 'HH:MM:SS' or 'HH:MM' — normalize
        hh, mm = time_str.split(":")[0:2]
        scheduler.add_job(
            med_reminder_due,
            CronTrigger(hour=int(hh), minute=int(mm)),
            args=[med["family_id"], medication_id],
            id=f"{prefix}{hh}{mm}",
            replace_existing=True,
        )


@requires_active_family
async def symptom_diary_due(family_id: str) -> None:
    """Evening check-in: Aunty May asks how the parent is feeling.

    The parent's reply flows through the normal voice pipeline → classify →
    symptom_entry / clinical_question_deferred / off_topic / etc. No escalation
    is scheduled from here; the classifier handles the downstream routing.
    """
    from app.db import users as users_repo

    family = await families_repo.get(family_id)
    if not family:
        return
    parent = await users_repo.by_id(family["parent_user_id"])
    if not parent or not parent.get("telegram_chat_id"):
        return

    languages = family.get("languages") or "zh+en"
    if "zh" in languages:
        text = "Auntie Lim, 今天身体怎么样?"
    else:
        text = "Auntie Lim, how are you feeling today?"

    app = build_application()
    await send_to_parent(app.bot, parent["telegram_chat_id"], text)
    # No event logged here — a parent reply will create the symptom_entry or
    # parent_reply_transcribed event through the voice handler.


async def register_all_medication_jobs() -> None:
    """Called at FastAPI startup — idempotent; re-register all active med cron jobs."""
    meds = await medications_repo.list_all_active_across_families()
    for med in meds:
        await sync_jobs_for_medication(med["id"])


# ---------------------------------------------------------------------------
# Daily morning report (06:00 local) + weekly digest (Fri 18:00 local)
# ---------------------------------------------------------------------------


@requires_active_family
async def daily_report(family_id: str) -> None:
    """06:00 morning post to the family group.

    Contents:
      - Today's on-duty caregiver (mentioned)
      - Yesterday's adherence snapshot (confirmed / missed counts)
      - Upcoming appointments in the next 7 days
      - Any urgent flags in the last 24h
    """
    from html import escape
    from zoneinfo import ZoneInfo

    from app.bot.app import build_application
    from app.bot.mentions import mention
    from app.config import settings
    from app.db import appointments as appt_repo
    from app.db import rotation as rotation_repo
    from app.db import users as users_repo

    tz = ZoneInfo(settings.tz)
    family = await families_repo.get(family_id)
    if not family or not family.get("group_chat_id"):
        return

    now_local = datetime.now(tz)
    today_dow = (now_local.weekday() + 1) % 7

    # Today's on-duty
    on_duty_id = await rotation_repo.on_duty(family_id, today_dow)
    on_duty = await users_repo.by_id(on_duty_id) if on_duty_id else None

    # Yesterday's events (local-day window)
    yesterday_start_local = (now_local - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start_utc = yesterday_start_local.astimezone(timezone.utc)

    all_events = await events_repo.recent_for_briefing(family_id, window_days=2)
    yesterday_events = [
        e
        for e in all_events
        if yesterday_start_utc
        <= datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
        < today_start_local.astimezone(timezone.utc)
    ]
    confirmed = sum(1 for e in yesterday_events if e["type"] == "med_confirmed")
    missed = sum(1 for e in yesterday_events if e["type"] == "med_missed")
    urgent_24h = sum(
        1
        for e in all_events
        if e["type"] == "urgent_symptom_escalated"
        and (datetime.now(timezone.utc) - datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))).total_seconds()
        < 24 * 60 * 60
    )

    # Upcoming appointments (next 7 days)
    upcoming = await appt_repo.list_upcoming(family_id, limit=10)
    cutoff = now_local + timedelta(days=7)
    nearby = [
        a
        for a in upcoming
        if datetime.fromisoformat(a["starts_at"].replace("Z", "+00:00")).astimezone(tz) <= cutoff
    ]

    # Compose HTML
    lines = [f"🌅 <b>Good morning — {now_local.strftime('%A %d %b')}</b>", ""]

    if on_duty:
        lines.append(
            f"📍 On duty today: {mention(on_duty['display_name'], on_duty.get('telegram_user_id'))}"
        )
    else:
        lines.append("📍 <i>Nobody on duty today — assign in the admin dashboard</i>")

    # Yesterday's adherence
    if confirmed or missed:
        bar = "✓" * confirmed + "✗" * missed
        lines.append("")
        lines.append(f"💊 Yesterday: {confirmed} confirmed, {missed} missed  <code>{bar}</code>")
    else:
        lines.append("")
        lines.append("💊 No medication activity logged yesterday.")

    # Upcoming appointments
    if nearby:
        lines.append("")
        lines.append("🗓 <b>Upcoming (next 7 days):</b>")
        for a in nearby:
            starts = datetime.fromisoformat(a["starts_at"].replace("Z", "+00:00")).astimezone(tz)
            label = starts.strftime("%a %d %b %H:%M")
            title = escape(a.get("title") or "Appointment")
            loc = a.get("location")
            loc_str = f" @ {escape(loc)}" if loc else ""
            lines.append(f"  • <b>{label}</b> — {title}{loc_str}")

    if urgent_24h:
        lines.append("")
        lines.append(
            f"🚨 <b>{urgent_24h} urgent-symptom flag{'s' if urgent_24h != 1 else ''} in the last 24h</b> — please follow up."
        )

    msg = "\n".join(lines)
    app = build_application()
    await app.bot.send_message(
        chat_id=family["group_chat_id"],
        text=msg,
        parse_mode="HTML",
    )


@requires_active_family
async def weekly_digest(family_id: str) -> None:
    """Friday 18:00 — post the coverage digest to the family group."""
    from app.bot.app import build_application
    from app.bot.digest import compute as compute_digest

    family = await families_repo.get(family_id)
    if not family or not family.get("group_chat_id"):
        return

    text = await compute_digest(family_id)
    app = build_application()
    await app.bot.send_message(
        chat_id=family["group_chat_id"],
        text=text,
        parse_mode="HTML",
    )
    await events_repo.insert(family_id, "weekly_digest_sent", payload={})


async def register_all_family_crons() -> None:
    """Register daily_report (06:00) + weekly_digest (Fri 18:00) per family.

    Called at FastAPI startup alongside register_all_medication_jobs.
    Idempotent — replace_existing=True on stable job IDs.
    """
    from apscheduler.triggers.cron import CronTrigger

    from app.db.client import get_client
    from app.scheduler.scheduler import get_scheduler

    scheduler = get_scheduler()
    client = await get_client()
    resp = await client.table("families").select("id").execute()
    families = resp.data or []

    for fam in families:
        fid = fam["id"]
        scheduler.add_job(
            daily_report,
            CronTrigger(hour=6, minute=0),
            args=[fid],
            id=f"daily_report:{fid}",
            replace_existing=True,
        )

        # Evening symptom-diary check-in at families.symptom_diary_time (default 20:00)
        raw_time = fam.get("symptom_diary_time") or "20:00"
        hh, mm = str(raw_time).split(":")[0:2]
        scheduler.add_job(
            symptom_diary_due,
            CronTrigger(hour=int(hh), minute=int(mm)),
            args=[fid],
            id=f"symptom_diary:{fid}",
            replace_existing=True,
        )

        scheduler.add_job(
            weekly_digest,
            CronTrigger(day_of_week="fri", hour=18, minute=0),
            args=[fid],
            id=f"weekly_digest:{fid}",
            replace_existing=True,
        )
