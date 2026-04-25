"""Scheduled job handlers. All are gated by the unified active-family guard.

NOTE: APScheduler runs these in the same asyncio loop as the PTB Application.
They must be picklable, so they take only simple ID args and re-acquire clients
internally.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.bot.app import build_application
from app.bot.group_post import post_escalation
from app.bot.med_timing import closest_slot
from app.config import settings
from app.db import doses as doses_repo
from app.db import events as events_repo
from app.db import families as families_repo
from app.db import medication as medication_repo
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
    med = await medication_repo.by_id(medication_id)
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
    languages = family.get("languages") or "zh+en"
    lang_code = "zh" if "zh" in languages else "en"
    await send_to_parent(
        app.bot,
        parent["telegram_chat_id"],
        text,
        family_id=family_id,
        language_code=lang_code,
    )

    now_utc = datetime.now(timezone.utc)
    reminder_event = await events_repo.insert(
        family_id,
        "med_reminder_sent",
        payload={
            "medication_id": medication_id,
            "scheduled_time": now_utc.isoformat(),
        },
        medication_id=medication_id,
    )

    # Dose instance — canonical adherence state; starts as 'pending'
    slot_time, _ = closest_slot(med["times"], datetime.now())
    dose = await doses_repo.create_pending(
        family_id,
        medication_id,
        scheduled_at=now_utc,
        slot=slot_time.strftime("%H:%M"),
        reminder_event_id=reminder_event["id"],
    )

    # Schedule window-close
    window_min = 1 if settings.demo_mode_fast_forward else settings.confirmation_window_min
    from app.scheduler.scheduler import get_scheduler

    scheduler = get_scheduler()
    run_at = datetime.now(timezone.utc) + timedelta(minutes=window_min)
    await asyncio.to_thread(
        scheduler.add_job,
        confirmation_window_close,
        "date",
        run_date=run_at,
        args=[family_id, medication_id, reminder_event["id"], dose["id"]],
        id=f"win_close:{reminder_event['id']}",
        replace_existing=True,
    )


@requires_active_family
async def confirmation_window_close(
    family_id: str,
    medication_id: str,
    reminder_event_id: str,
    dose_id: str | None = None,
) -> None:
    """If no med_confirmed event logged in the window, escalate to the family group.

    If a dose_instance for this reminder is still 'pending', flip it to
    'missed_unresolved'. If it's already been confirmed, the dose is no longer pending
    and we skip escalation.
    """
    # Dose-first check when we have a dose_id (new path). Fall back to event check
    # for any in-flight window_close jobs scheduled before the dose-instance rollout.
    if dose_id:
        dose = await doses_repo.by_id(dose_id)
        if not dose or dose["status"] != "pending":
            log.info(
                "window_close: dose %s status=%s — skip escalation",
                dose_id,
                dose and dose["status"],
            )
            return

    reminder = await events_repo.by_id(reminder_event_id)
    if not reminder:
        return
    reminder_ts = datetime.fromisoformat(reminder["created_at"].replace("Z", "+00:00"))

    if not dose_id:
        # Legacy path: fall back to the event-based check
        confirmed = await events_repo.had_confirmation_within_window(
            family_id, medication_id, since=reminder_ts
        )
        if confirmed:
            log.info("Confirmation present — no escalation for reminder %s", reminder_event_id)
            return

    med = await medication_repo.by_id(medication_id)
    if not med:
        return

    miss_count = await events_repo.count_misses_this_week(family_id, medication_id) + 1

    miss_event = await events_repo.insert(
        family_id,
        "med_missed",
        payload={
            "medication_id": medication_id,
            "reminder_event_id": reminder_event_id,
            "window_min": settings.confirmation_window_min,
        },
        medication_id=medication_id,
    )
    if dose_id:
        await doses_repo.mark_missed(dose_id, miss_event_id=miss_event["id"])

    app = build_application()
    await post_escalation(app.bot, family_id, med, reminder_event_id, miss_count)

    # Schedule Aunty May's check-back
    offset_min = 1 if settings.demo_mode_fast_forward else settings.check_back_offset_min
    from app.scheduler.scheduler import get_scheduler

    scheduler = get_scheduler()
    run_at = datetime.now(timezone.utc) + timedelta(minutes=offset_min)
    await asyncio.to_thread(
        scheduler.add_job,
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
    med = await medication_repo.by_id(medication_id)
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
    lang_code = "zh" if "zh" in languages else "en"
    await send_to_parent(
        app.bot,
        parent["telegram_chat_id"],
        text,
        family_id=family_id,
        language_code=lang_code,
    )

    await events_repo.insert(
        family_id,
        "check_back_sent",
        payload={"medication_id": medication_id},
        medication_id=medication_id,
    )


async def sync_jobs_for_medication(medication_id: str) -> None:
    """After add / edit / deactivate, re-register cron jobs for a medication.

    Removes any existing med_reminder:{medication_id}:* jobs, then (if active) adds fresh ones.
    APScheduler's SQLAlchemyJobStore is sync — wrap each store-touching call in
    `asyncio.to_thread` so we don't freeze the event loop during startup.
    """
    from app.scheduler.scheduler import get_scheduler

    scheduler = get_scheduler()
    prefix = f"med_reminder:{medication_id}:"

    # Remove stale
    all_jobs = await asyncio.to_thread(scheduler.get_jobs)
    for job in all_jobs:
        if job.id.startswith(prefix):
            await asyncio.to_thread(job.remove)

    med = await medication_repo.by_id(medication_id)
    if not med or not med.get("active"):
        return

    from apscheduler.triggers.cron import CronTrigger

    for time_str in med["times"] or []:
        # time_str may be 'HH:MM:SS' or 'HH:MM' — normalize
        hh, mm = time_str.split(":")[0:2]
        trigger = CronTrigger(hour=int(hh), minute=int(mm))
        await asyncio.to_thread(
            scheduler.add_job,
            med_reminder_due,
            trigger,
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
    lang_code = "zh" if "zh" in languages else "en"
    await send_to_parent(
        app.bot,
        parent["telegram_chat_id"],
        text,
        family_id=family_id,
        language_code=lang_code,
    )
    # No event logged here — a parent reply will create the symptom_entry or
    # parent_reply_transcribed event through the voice handler.


async def register_all_medication_jobs() -> None:
    """Called at FastAPI startup — idempotent; re-register all active med cron jobs."""
    meds = await medication_repo.list_all_active_across_families()
    for med in meds:
        await sync_jobs_for_medication(med["id"])


async def sync_jobs_for_family(family_id: str) -> None:
    """Drop every medication cron for this family + re-register from current DB state.

    Called by Settings → Reset history so a wipe leaves no stale jobs pointing at
    deleted med ids, and any meds added during the reset transaction get fresh
    cron registrations.
    """
    from app.scheduler.scheduler import get_scheduler

    scheduler = get_scheduler()
    all_jobs = await asyncio.to_thread(scheduler.get_jobs)
    for job in all_jobs:
        if not job.id.startswith("med_reminder:"):
            continue
        # job.args = [family_id, medication_id]
        if (job.args or [None])[0] == family_id:
            await asyncio.to_thread(job.remove)

    meds = await medication_repo.list_active(family_id)
    for med in meds:
        await sync_jobs_for_medication(med["id"])


# ---------------------------------------------------------------------------
# Weekly Monday update (group) + weekly digest (Fri 18:00 local)
# ---------------------------------------------------------------------------


@requires_active_family
async def weekly_report(family_id: str) -> None:
    """Monday-morning post to the family group setting up the week ahead.

    Contents:
      - On-duty rotation for the week
      - Last 7 days' adherence snapshot (confirmed / missed counts)
      - Upcoming appointments in the next 14 days (from .ics ingest)
      - Any urgent flags in the last 7 days
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

    # Rotation for the week — Mon..Sun
    rotation_rows = await rotation_repo.list_for_family(family_id)
    by_dow = {r["day_of_week"]: r["user_id"] for r in rotation_rows}
    rotation_user_ids = list({uid for uid in by_dow.values() if uid})
    rotation_users: dict[str, dict] = {}
    for uid in rotation_user_ids:
        u = await users_repo.by_id(uid)
        if u:
            rotation_users[uid] = u

    # Past 7-day events
    week_start_local = (now_local - timedelta(days=7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_start_utc = week_start_local.astimezone(timezone.utc)

    all_events = await events_repo.recent_for_briefing(family_id, window_days=8)
    week_events = [
        e
        for e in all_events
        if datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")) >= week_start_utc
    ]
    confirmed = sum(1 for e in week_events if e["type"] == "med_confirmed")
    missed = sum(1 for e in week_events if e["type"] == "med_missed")
    urgent_7d = sum(1 for e in week_events if e["type"] == "urgent_symptom_escalated")

    # Upcoming appointments (next 14 days)
    upcoming = await appt_repo.list_upcoming(family_id, limit=20)
    cutoff = now_local + timedelta(days=14)
    nearby = [
        a
        for a in upcoming
        if datetime.fromisoformat(a["starts_at"].replace("Z", "+00:00")).astimezone(tz) <= cutoff
    ]

    # Compose HTML
    lines = [
        f"📅 <b>Week ahead — {now_local.strftime('%a %d %b')}</b>",
        "",
    ]

    # Rotation
    if rotation_users:
        lines.append("📍 <b>This week's rotation</b>")
        day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        for dow in [1, 2, 3, 4, 5, 6, 0]:  # display Mon-first
            uid = by_dow.get(dow)
            if uid and (u := rotation_users.get(uid)):
                lines.append(
                    f"  • {day_names[dow]}: {mention(u['display_name'], u.get('telegram_user_id'))}"
                )
            else:
                lines.append(f"  • {day_names[dow]}: <i>unassigned</i>")
    else:
        lines.append("📍 <i>No rotation set — assign in the admin dashboard</i>")

    # Last 7 days' adherence
    lines.append("")
    if confirmed or missed:
        total = confirmed + missed
        pct = round(100 * confirmed / total) if total else 0
        lines.append(
            f"💊 Last 7 days: {confirmed}/{total} doses confirmed ({pct}%)"
        )
    else:
        lines.append("💊 No medication activity logged in the past 7 days.")

    # Upcoming appointments
    if nearby:
        lines.append("")
        lines.append("🗓 <b>Upcoming (next 14 days):</b>")
        for a in nearby:
            starts = datetime.fromisoformat(a["starts_at"].replace("Z", "+00:00")).astimezone(tz)
            label = starts.strftime("%a %d %b %H:%M")
            title = escape(a.get("title") or "Appointment")
            loc = a.get("location")
            loc_str = f" @ {escape(loc)}" if loc else ""
            lines.append(f"  • <b>{label}</b> — {title}{loc_str}")
    else:
        lines.append("")
        lines.append("🗓 <i>No appointments in the next 14 days.</i>")

    if urgent_7d:
        lines.append("")
        lines.append(
            f"🚨 <b>{urgent_7d} urgent-symptom flag{'s' if urgent_7d != 1 else ''} this past week</b> — please follow up."
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
    resp = await client.table("families").select("*").execute()
    families = resp.data or []

    # Clean up stale `daily_report:*` jobs from before the rename (one-time migration)
    existing = await asyncio.to_thread(scheduler.get_jobs)
    for job in existing:
        if job.id.startswith("daily_report:"):
            await asyncio.to_thread(job.remove)

    for fam in families:
        fid = fam["id"]

        # Weekly Monday report at families.daily_report_time (default 06:00) — posts to the group.
        # Column name kept for backward compat; UI label says "Weekly report time".
        dr_time = fam.get("daily_report_time") or "06:00"
        drh, drm = str(dr_time).split(":")[0:2]
        await asyncio.to_thread(
            scheduler.add_job,
            weekly_report,
            CronTrigger(day_of_week="mon", hour=int(drh), minute=int(drm)),
            args=[fid],
            id=f"weekly_report:{fid}",
            replace_existing=True,
        )

        # Evening symptom-diary check-in at families.symptom_diary_time (default 20:00) — parent DM
        raw_time = fam.get("symptom_diary_time") or "20:00"
        hh, mm = str(raw_time).split(":")[0:2]
        await asyncio.to_thread(
            scheduler.add_job,
            symptom_diary_due,
            CronTrigger(hour=int(hh), minute=int(mm)),
            args=[fid],
            id=f"symptom_diary:{fid}",
            replace_existing=True,
        )

        await asyncio.to_thread(
            scheduler.add_job,
            weekly_digest,
            CronTrigger(day_of_week="fri", hour=18, minute=0),
            args=[fid],
            id=f"weekly_digest:{fid}",
            replace_existing=True,
        )
