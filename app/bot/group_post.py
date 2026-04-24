"""Family-group escalation post + ✓ Sent callback with JIT caregiver linking.

Escalation flow:
  1. confirmation_window_close job detects a missed med.
  2. post_escalation() builds the HTML message, @-mentions today's on-duty caregiver,
     attaches the canned nudge as a quoted block + a ✓ Sent button.
  3. When any family member taps ✓ Sent, handle_sent_callback() edits the message,
     logs nudge_sent_by_caregiver attributed to the tapper (creating a users row
     for them if they were unlinked).

Resolution posts (when the parent confirms later) come from post_resolution().
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape
from uuid import UUID

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.mentions import mention
from app.db import events as events_repo
from app.db import families as families_repo
from app.db import rotation as rotation_repo
from app.db import users as users_repo

log = logging.getLogger(__name__)

# Canned nudge templates per language — on-duty person copies + sends privately.
NUDGE_TEMPLATES = {
    "zh+en": "妈, 吃药了吗?",
    "zh": "妈, 吃药了吗?",
    "en": "Ma, have you taken your meds yet?",
}


def _nudge_for(languages: str | None) -> str:
    if not languages:
        return NUDGE_TEMPLATES["zh+en"]
    return NUDGE_TEMPLATES.get(languages, NUDGE_TEMPLATES["zh+en"])


async def post_escalation(
    bot,
    family_id: UUID | str,
    medication: dict,
    reminder_event_id: str,
    miss_count_this_week: int,
) -> int | None:
    """Post the @-mention + drafted nudge + ✓ Sent button to the family group.

    Returns the group message_id on success, or None if no group linked yet.
    """
    family = await families_repo.get(family_id)
    if not family or not family.get("group_chat_id"):
        log.warning("post_escalation: family %s has no group_chat_id", family_id)
        return None

    # Today's on-duty caregiver
    day_of_week = (datetime.now(timezone.utc).weekday() + 1) % 7  # Python Mon=0; we want Sun=0
    on_duty_user_id = await rotation_repo.on_duty(family_id, day_of_week)
    on_duty_user = await users_repo.by_id(on_duty_user_id) if on_duty_user_id else None

    on_duty_mention = (
        mention(on_duty_user["display_name"], on_duty_user.get("telegram_user_id"))
        if on_duty_user
        else "no one on duty today"
    )

    nudge_text = _nudge_for(family.get("languages"))
    med_name = escape(medication.get("name") or "medication")

    msg_html = (
        f"Aunty May's check-in: <b>morning meds unconfirmed</b> ({med_name}).\n"
        f"{on_duty_mention} — you're on-duty today. "
        f"{miss_count_this_week}{'st' if miss_count_this_week == 1 else 'nd' if miss_count_this_week == 2 else 'rd' if miss_count_this_week == 3 else 'th'} unconfirmed this week — logging for the next GP visit.\n\n"
        f"<i>Draft below ⬇️</i>\n"
        f"<blockquote>{escape(nudge_text)}</blockquote>"
    )

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✓ Sent", callback_data=f"nudge_sent:{reminder_event_id}")]]
    )

    sent = await bot.send_message(
        chat_id=family["group_chat_id"],
        text=msg_html,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )

    await events_repo.insert(
        family_id,
        "escalation_posted",
        payload={
            "reminder_event_id": reminder_event_id,
            "group_message_id": sent.message_id,
            "pattern_count": miss_count_this_week,
            "on_duty_user_id": str(on_duty_user_id) if on_duty_user_id else None,
        },
        medication_id=medication["id"],
    )
    return sent.message_id


async def handle_sent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """✓ Sent button tap. Edit the message + log attribution (JIT-link tapper if needed)."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data or ""
    if not data.startswith("nudge_sent:"):
        return
    reminder_event_id = data.split(":", 1)[1]

    # Identify which family this is for from the reminder event
    reminder_event = await events_repo.by_id(reminder_event_id)
    if not reminder_event:
        log.warning("handle_sent_callback: reminder event %s not found", reminder_event_id)
        return
    family_id = reminder_event["family_id"]

    # JIT-link the tapper if they don't have a users row yet
    tapper_tg = query.from_user
    user = await users_repo.upsert_caregiver_from_telegram(
        family_id,
        telegram_user_id=tapper_tg.id,
        telegram_chat_id=tapper_tg.id,  # private chat id == user id for 1:1 DMs
        telegram_username=tapper_tg.username,
        display_name=tapper_tg.full_name or tapper_tg.username or str(tapper_tg.id),
    )

    # Log attribution
    await events_repo.insert(
        family_id,
        "nudge_sent_by_caregiver",
        payload={
            "reminder_event_id": reminder_event_id,
            "draft_text": "",  # templates already visible in the original message
        },
        attributed_to=user["id"],
        medication_id=reminder_event.get("medication_id"),
    )

    # Edit the original message — append a "sent by X at HH:MM" line
    now_str = datetime.now().strftime("%H:%M")
    name_mention = mention(user["display_name"], user.get("telegram_user_id"))
    try:
        await query.edit_message_text(
            text=(query.message.text_html or "")
            + f"\n\n✓ {name_mention} sent the nudge at {now_str}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:  # noqa: BLE001 — message may already have been edited
        log.exception("Failed to edit escalation message")


async def post_resolution(
    bot,
    family_id: UUID | str,
    medication: dict,
    when: datetime,
) -> None:
    """Post a resolution line to the family group when the parent confirms later."""
    family = await families_repo.get(family_id)
    if not family or not family.get("group_chat_id"):
        return
    med_name = escape(medication.get("name") or "meds")
    await bot.send_message(
        chat_id=family["group_chat_id"],
        text=f"✓ {med_name} confirmed at {when.strftime('%H:%M')}. Logged for GP briefing.",
        parse_mode=ParseMode.HTML,
    )
