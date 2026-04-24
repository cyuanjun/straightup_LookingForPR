"""Weekly digest — on-duty coverage + overflow signal (Option B).

Measures *whether the rotation held up*, not *how many times the parent forgot*:

  - on-duty days per caregiver (from `rotation` for each of the last 7 days)
  - covered: escalations where the on-duty person tapped ✓ Sent
  - missed:  escalations where someone else tapped ✓, or nobody tapped
  - overflow: escalations where someone NOT on-duty stepped up

Output is framed around the rotation commitment, not raw nudge counts, so a
"bad week for the parent" doesn't inflate any caregiver's numbers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
from uuid import UUID

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.db import events as events_repo
from app.db import rotation as rotation_repo
from app.db import users as users_repo


async def compute(family_id: UUID | str) -> str:
    """Build the Option-B digest. Returns HTML string for Telegram (parse_mode=HTML)."""

    # --- Gather last-7-days events ---
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=7)
    week_events = [
        e
        for e in await events_repo.recent_for_briefing(family_id, window_days=7)
        if datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")) >= cutoff
    ]

    escalations = [e for e in week_events if e["type"] == "escalation_posted"]
    taps = [e for e in week_events if e["type"] == "nudge_sent_by_caregiver"]

    # reminder_event_id -> tapper_user_id
    tap_map: dict[str, str] = {}
    for t in taps:
        rid = (t.get("payload") or {}).get("reminder_event_id")
        if rid:
            tap_map[rid] = t.get("attributed_to") or ""

    # --- Per-user tallies ---
    covered_own: dict[str, int] = {}
    missed_own: dict[str, int] = {}          # on-duty that day, but someone else tapped or nobody did
    picked_up_overflow: dict[str, int] = {}  # not on-duty, but they stepped up

    for esc in escalations:
        payload = esc.get("payload") or {}
        reminder_id = payload.get("reminder_event_id")
        on_duty_uid = payload.get("on_duty_user_id")
        tapper_uid = tap_map.get(reminder_id)

        if on_duty_uid and tapper_uid == on_duty_uid:
            covered_own[on_duty_uid] = covered_own.get(on_duty_uid, 0) + 1
        elif tapper_uid:
            # Overflow: someone not on-duty picked it up
            picked_up_overflow[tapper_uid] = picked_up_overflow.get(tapper_uid, 0) + 1
            if on_duty_uid:
                missed_own[on_duty_uid] = missed_own.get(on_duty_uid, 0) + 1
        else:
            # Nobody tapped — counts against on-duty
            if on_duty_uid:
                missed_own[on_duty_uid] = missed_own.get(on_duty_uid, 0) + 1

    # --- On-duty days per caregiver (last 7 local days) ---
    on_duty_days: dict[str, int] = {}
    today_local = datetime.now().date()
    for i in range(7):
        day = today_local - timedelta(days=i)
        # Python weekday: Mon=0..Sun=6 → our rotation: Sun=0..Sat=6
        dow = (day.weekday() + 1) % 7
        uid = await rotation_repo.on_duty(family_id, dow)
        if uid:
            on_duty_days[uid] = on_duty_days.get(uid, 0) + 1

    # --- Compose ---
    caregivers = await users_repo.list_caregivers(family_id)
    if not caregivers:
        return "No caregivers on file yet — run /setup to add the family."

    total_esc = len(escalations)
    if total_esc == 0:
        # Quiet week — no escalations. Still show on-duty commitment.
        lines = ["<b>Last 7 days</b> — quiet week, no missed meds 🌿"]
        for c in caregivers:
            days = on_duty_days.get(c["id"], 0)
            if days:
                lines.append(f"• {escape(c['display_name'])}: on-duty {days} days ✓")
        return "\n".join(lines)

    header = f"<b>Last 7 days</b> — {total_esc} escalation{'s' if total_esc != 1 else ''}."

    # Sort caregivers: most on-duty days first, then most activity
    def activity(c: dict) -> tuple[int, int]:
        uid = c["id"]
        return (
            on_duty_days.get(uid, 0),
            covered_own.get(uid, 0) + picked_up_overflow.get(uid, 0),
        )

    rows: list[str] = []
    for c in sorted(caregivers, key=activity, reverse=True):
        uid = c["id"]
        name = escape(c["display_name"])
        days = on_duty_days.get(uid, 0)
        covered = covered_own.get(uid, 0)
        missed = missed_own.get(uid, 0)
        picked = picked_up_overflow.get(uid, 0)

        if days == 0 and covered == 0 and missed == 0 and picked == 0:
            continue  # inactive — don't clutter

        parts: list[str] = []
        if days:
            if covered == days - missed and missed == 0 and covered > 0:
                parts.append(f"on-duty {days} days, covered all ✓")
            elif covered > 0 and missed > 0:
                parts.append(
                    f"on-duty {days} days, covered {covered}, family picked up {missed}"
                )
            elif covered > 0:
                parts.append(f"on-duty {days} days, covered {covered}")
            elif missed > 0:
                parts.append(
                    f"on-duty {days} days, family picked up all {missed} for them"
                )
            else:
                parts.append(f"on-duty {days} days")

        if picked > 0:
            if parts:
                parts.append(f"picked up {picked} extra for others")
            else:
                parts.append(f"picked up {picked} for others (not on rotation)")

        if parts:
            rows.append(f"• {name}: " + "; ".join(parts))

    return header + "\n" + "\n".join(rows) if rows else header


async def handle_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/digest command — in family group or caregiver DM."""
    chat = update.effective_chat
    if chat is None:
        return

    # Look up family_id from chat context
    family_id: str | None = None
    if chat.type in ("group", "supergroup"):
        from app.db.client import get_client

        client = await get_client()
        resp = (
            await client.table("families")
            .select("id")
            .eq("group_chat_id", chat.id)
            .maybe_single()
            .execute()
        )
        if resp and resp.data:
            family_id = resp.data["id"]
    else:
        if update.effective_user:
            from app.db.client import get_client

            client = await get_client()
            resp = (
                await client.table("users")
                .select("family_id")
                .eq("telegram_user_id", update.effective_user.id)
                .maybe_single()
                .execute()
            )
            if resp and resp.data:
                family_id = resp.data["family_id"]

    if not family_id:
        await chat.send_message("I'm not linked to a family yet.")
        return

    text = await compute(family_id)
    await chat.send_message(text, parse_mode=ParseMode.HTML)
    await events_repo.insert(family_id, "weekly_digest_sent", payload={})
