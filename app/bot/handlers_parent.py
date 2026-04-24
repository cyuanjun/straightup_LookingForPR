"""Parent-facing handlers: guarded voice pipeline (and text pipeline when VOICE_DISABLED) + /help + /stop.

Voice-guard (all must hold):
  1. filters.ChatType.PRIVATE (set in app.py)
  2. update.effective_user.id → matches a `users` row with role='parent'
  3. That users.id == families.parent_user_id for that family

Rejects group voice and caregivers sending voice DMs.

When settings.voice_disabled=True, the same pipeline accepts text messages from
the linked parent instead of voice — saves ElevenLabs credits during testing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from html import escape

# Double-dose dedup is now slot-aware (see events.confirmations_today + payload.slot).
# A confirmation is a duplicate iff another today's confirmation for the same medication
# points at the same scheduled slot. Handles single-daily, twice-daily, 4x-daily, etc.
# correctly — morning and evening slots are tracked independently.

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.group_post import post_resolution
from app.bot.med_timing import classify_timing, closest_slot
from app.bot.mentions import mention
from app.config import settings
from app.db import doses as doses_repo
from app.db import events as events_repo
from app.db import families as families_repo
from app.db import medication as medication_repo
from app.db import rotation as rotation_repo
from app.db import users as users_repo
from app.llm import classify as classify_mod
from app.llm import decide as decide_mod
from app.llm import memory as memory_mod
from app.voice import stt as stt_mod
from app.voice.send import send_to_parent

log = logging.getLogger(__name__)


async def _resolve_parent(update: Update) -> tuple[dict, dict] | None:
    """Guards 1–3. Returns (parent_user_row, family_row) or None if rejected."""
    if update.effective_chat is None or update.effective_chat.type != "private":
        return None
    if update.effective_user is None:
        return None
    parent = await users_repo.find_parent_by_telegram_id(update.effective_user.id)
    if parent is None:
        return None
    family = await families_repo.get(parent["family_id"])
    if not family or family.get("parent_user_id") != parent["id"]:
        return None
    return parent, family


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.message.voice is None:
        return
    resolved = await _resolve_parent(update)
    if resolved is None:
        return
    parent, family = resolved

    voice_file = await update.message.voice.get_file()
    audio_bytes = bytes(await voice_file.download_as_bytearray())
    transcription = await stt_mod.transcribe(audio_bytes)
    transcript = transcription.get("text") or ""
    language_code = transcription.get("language_code")

    await _process_parent_reply(update, context, parent, family, transcript, language_code)


async def handle_text_from_parent(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """VOICE_DISABLED mode: treat text messages from the linked parent as replies.

    Called from onboarding.handle_yes_no_confirmation after it checks there's no
    pending handshake — so yes/no still works during onboarding.
    """
    if not settings.voice_disabled:
        return
    if update.message is None or not update.message.text:
        return
    resolved = await _resolve_parent(update)
    if resolved is None:
        return
    parent, family = resolved

    await _process_parent_reply(
        update, context, parent, family, update.message.text, language_code=None
    )


async def _process_parent_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    parent: dict,
    family: dict,
    transcript: str,
    language_code: str | None,
) -> None:
    """Shared pipeline: log turn → classify → decide → side-effects → TTS/text reply."""
    if update.effective_chat is None:
        return
    family_id = family["id"]
    chat_id = update.effective_chat.id

    await memory_mod.record_turn(
        family_id,
        chat_id,
        "parent",
        transcript,
        speaker_user_id=parent["id"],
        language_code=language_code,
    )
    await events_repo.insert(
        family_id,
        "parent_reply_transcribed",
        payload={"transcript": transcript, "language_code": language_code, "confidence": 1.0},
    )

    intent = await classify_mod.classify(transcript)

    # Today's on-duty caregiver for deferral-script interpolation
    day_of_week = (datetime.now().weekday() + 1) % 7  # Python Mon=0 → Sun=0
    on_duty_id = await rotation_repo.on_duty(family_id, day_of_week)
    on_duty = await users_repo.by_id(on_duty_id) if on_duty_id else None
    caregiver_name = (on_duty or {}).get("display_name") or "your caregiver"

    # Pre-match a medication name for the decide prompt (confirm_med path)
    matched_med_name: str | None = None
    if intent.get("intent") == "confirm_med":
        meds = await medication_repo.list_active(family_id)
        nm = intent.get("medication_name")
        matched = next(
            (m for m in meds if nm and nm.lower() in m["name"].lower()),
            meds[0] if meds else None,
        )
        if matched:
            matched_med_name = matched["name"]

    memory = await memory_mod.fetch_recent(family_id, chat_id, n=12)
    decision = await decide_mod.decide(
        intent,
        memory_turns=memory,
        caregiver_name=caregiver_name,
        parent_language_hint=language_code or family.get("languages"),
        matched_medication_name=matched_med_name,
    )

    kind = intent.get("intent")
    if kind == "confirm_med":
        med_name = intent.get("medication_name")
        meds = await medication_repo.list_active(family_id)
        matched = next(
            (m for m in meds if med_name and med_name.lower() in m["name"].lower()),
            meds[0] if meds else None,
        )
        if matched:
            # --- Timing classification FIRST: which slot is this confirmation for? ---
            now_local = datetime.now()
            slot_time, delta_min = closest_slot(matched["times"], now_local)
            timing = classify_timing(delta_min)
            slot_str = slot_time.strftime("%H:%M")

            # --- Slot-aware double-dose guard ---
            # A confirmation today for the SAME slot = duplicate, regardless of time gap.
            # Correctly handles single-daily and multi-daily schedules: morning 08:45
            # and evening 20:00 confirmations are tracked independently.
            confirmations = await events_repo.confirmations_today(family_id, matched["id"])
            dup = next(
                (
                    c
                    for c in confirmations
                    if (c.get("payload") or {}).get("slot") == slot_str
                ),
                None,
            )
            if dup:
                last_ts = datetime.fromisoformat(
                    dup["created_at"].replace("Z", "+00:00")
                )
                await _possible_double_dose(
                    context.bot,
                    family_id,
                    parent,
                    medication=matched,
                    last_confirmed_at=last_ts,
                    transcript=transcript,
                    language_code=language_code,
                )
                return

            confirm_event = await events_repo.insert(
                family_id,
                "med_confirmed",
                payload={
                    "medication_id": matched["id"],
                    "transcript": transcript,
                    "confidence": intent.get("confidence", 1.0),
                    "source": "parent_voice" if not settings.voice_disabled else "parent_text",
                    "timing": timing,        # on_time | early | late
                    "slot": slot_str,
                    "delta_min": delta_min,
                },
                medication_id=matched["id"],
            )

            # Update dose_instance lifecycle (canonical adherence state).
            #   1. Pending dose (from an active reminder) → confirm with this timing
            #   2. Missed_unresolved dose within last 4h → resolve as late
            #   3. Neither → standalone confirmed dose (e.g. took it before reminder fired)
            resolution_window = timedelta(hours=4)
            now_utc = datetime.now(timezone.utc)
            pending = await doses_repo.find_pending_for_med(
                family_id, matched["id"], since=now_utc - resolution_window
            )
            if pending:
                await doses_repo.mark_confirmed(
                    pending["id"], timing=timing, confirm_event_id=confirm_event["id"]
                )
            else:
                unresolved = await doses_repo.find_missed_unresolved_for_med(
                    family_id, matched["id"], since=now_utc - resolution_window
                )
                if unresolved:
                    await doses_repo.resolve_miss(
                        unresolved["id"], confirm_event_id=confirm_event["id"]
                    )
                else:
                    await doses_repo.create_standalone_confirmed(
                        family_id,
                        matched["id"],
                        scheduled_at=now_utc,
                        slot=slot_str,
                        timing=timing,
                        confirm_event_id=confirm_event["id"],
                    )

            await post_resolution(context.bot, family_id, matched, datetime.now())

            # Early/late → send the timing-specific warning to parent AND skip the
            # LLM-generated on-time ack (we already sent the warning as the reply).
            if timing in ("early", "late"):
                await _send_timing_warning(
                    context.bot,
                    parent,
                    medication=matched,
                    timing=timing,
                    slot_str=slot_str,
                    family=family,
                )
                return  # skip the LLM decide/TTS reply below

    elif kind == "symptom_entry":
        await events_repo.insert(
            family_id,
            "symptom_entry",
            payload={
                "symptom_text": intent.get("symptom_text") or transcript,
                "transcript": transcript,
                "language_code": language_code,
                "confidence": intent.get("confidence", 1.0),
            },
        )

    elif kind == "clinical_question":
        await events_repo.insert(
            family_id,
            "clinical_question_deferred",
            payload={
                "transcript": transcript,
                "question_text": intent.get("question_text") or transcript,
                "language_code": language_code,
            },
        )
        await _ping_on_duty(
            context.bot,
            family,
            body=f"Aunty May noted a concern for the next GP visit (from {escape(parent['display_name'])}).",
        )

    elif kind == "distress":
        await events_repo.insert(
            family_id,
            "distress_escalated",
            payload={"transcript": transcript, "language_code": language_code},
        )
        await _ping_on_duty(
            context.bot,
            family,
            body=f"Aunty May flagged emotional distress from {escape(parent['display_name'])}. Please check in.",
        )

    elif kind == "urgent_symptom":
        await _urgent_escalation(
            context.bot,
            family_id,
            parent,
            transcript=transcript,
            symptom_text=intent.get("symptom_text") or transcript,
            language_code=language_code,
        )

    reply_text = decision.get("aunty_reply_text")
    if reply_text:
        await send_to_parent(context.bot, chat_id, reply_text)
        await memory_mod.record_turn(
            family_id,
            chat_id,
            "aunty_may",
            reply_text,
            language_code=language_code,
        )


async def _ping_on_duty(bot, family: dict, body: str) -> None:
    group_chat_id = family.get("group_chat_id")
    if not group_chat_id:
        return
    day_of_week = (datetime.now().weekday() + 1) % 7
    on_duty_id = await rotation_repo.on_duty(family["id"], day_of_week)
    on_duty = await users_repo.by_id(on_duty_id) if on_duty_id else None
    if on_duty:
        head = mention(on_duty["display_name"], on_duty.get("telegram_user_id"))
    else:
        head = "Family"
    await bot.send_message(
        chat_id=group_chat_id,
        text=f"{head} — {body}",
        parse_mode=ParseMode.HTML,
    )


async def _send_timing_warning(
    bot,
    parent: dict,
    medication: dict,
    timing: str,       # 'early' | 'late'
    slot_str: str,     # HH:MM
    family: dict,
) -> None:
    """Gentle language-aware warning when parent confirms >60 min off-schedule."""
    from app.voice.send import send_to_parent

    languages = (family.get("languages") or "en")
    name = medication["name"]
    if "zh" in languages:
        if timing == "early":
            text = (
                f"Auntie, 现在还没到时间 hor — {name} 的时间是 {slot_str}. "
                "不要紧, 我记下来了."
            )
        else:  # late
            text = (
                f"Auntie, 有点晚了哦 — {name} 的时间是 {slot_str}. "
                "明天记得准时吃 ah. 我记下来了."
            )
    else:
        if timing == "early":
            text = (
                f"Auntie, it's a bit early — {name} is scheduled for {slot_str}. "
                "It's fine, I've noted it."
            )
        else:
            text = (
                f"Auntie, that was a bit late — {name} was due at {slot_str}. "
                "Try to catch it on time tomorrow. I've noted it."
            )
    await send_to_parent(bot, parent["telegram_chat_id"], text)


async def _possible_double_dose(
    bot,
    family_id,
    parent,
    medication: dict,
    last_confirmed_at: datetime,
    transcript: str,
    language_code: str | None,
) -> None:
    """Parent may be confirming the same dose twice (or taking a second dose too soon).

    We do NOT log this as `med_confirmed` — the earlier confirmation stands.
    Instead: warn the parent gently, DM every caregiver with the transcript + timestamps,
    and log `events.type=partial_confirm` with a flag payload so briefing/digest surface it.
    """
    # Warn the parent (language-aware)
    languages = (await families_repo.get(family_id)).get("languages") or "en"
    local_last = last_confirmed_at.astimezone().strftime("%H:%M")
    if "zh" in languages:
        warn_text = (
            f"哎, Auntie, 我记得 {local_last} 已经吃过 {medication['name']} 了. "
            "先不要再吃, 我告诉你家人看看好吗?"
        )
    else:
        warn_text = (
            f"Auntie, I already noted {medication['name']} at {local_last}. "
            "Best not to take another dose yet — I'll check with your family."
        )
    from app.voice.send import send_to_parent

    await send_to_parent(bot, parent["telegram_chat_id"], warn_text)

    # DM all caregivers with full context
    caregivers = await users_repo.list_caregivers(family_id)
    for c in caregivers:
        chat_id = c.get("telegram_chat_id")
        if not chat_id:
            continue
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚠️ <b>Possible double dose</b> — {escape(parent['display_name'])} "
                    f"just told Aunty May they took {escape(medication['name'])}, "
                    f"but we already logged that at {local_last}. "
                    f"Please check in with her in person before she takes another.\n\n"
                    f"Transcript: <i>{escape(transcript)}</i>"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            log.exception("Failed double-dose DM to caregiver %s", c.get("id"))

    # Log a flagged event (not med_confirmed — doesn't count toward adherence)
    await events_repo.insert(
        family_id,
        "partial_confirm",
        payload={
            "medication_id": medication["id"],
            "transcript": transcript,
            "language_code": language_code,
            "reason": "possible_double_dose",
            "previous_confirmation_at": last_confirmed_at.isoformat(),
        },
        medication_id=medication["id"],
    )


async def _urgent_escalation(
    bot, family_id, parent, transcript: str, symptom_text: str, language_code: str | None
) -> None:
    """DM all caregivers with the full transcript + log urgent_symptom_escalated."""
    caregivers = await users_repo.list_caregivers(family_id)
    dmed = []
    for c in caregivers:
        chat_id = c.get("telegram_chat_id")
        if not chat_id:
            continue
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🚨 <b>Urgent</b> — {escape(parent['display_name'])} reported:\n"
                    f"<i>{escape(symptom_text)}</i>\n\n"
                    f"Full transcript: <i>{escape(transcript)}</i>\n\n"
                    f"Aunty May advised 995. Please check on her now."
                ),
                parse_mode=ParseMode.HTML,
            )
            dmed.append(c["id"])
        except Exception:
            log.exception("Failed urgent DM to caregiver %s", c.get("id"))

    await events_repo.insert(
        family_id,
        "urgent_symptom_escalated",
        payload={
            "transcript": transcript,
            "symptom_text": symptom_text,
            "language_code": language_code,
            "caregivers_dmed": dmed,
        },
    )


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    await update.effective_chat.send_message(
        "Hello Auntie — I'm Aunty May, an AI. "
        "I remind you about your medicine and ask how you're feeling. "
        "I tell your family if I think something's not right. "
        "You can talk to me by voice anytime, in Mandarin or English. "
        "If you ever want me to stop, reply /stop."
    )


async def handle_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_user is None:
        return
    parent = await users_repo.find_parent_by_telegram_id(update.effective_user.id)
    if parent is None:
        return

    family_id = parent["family_id"]
    await families_repo.set_paused(family_id, True)
    await events_repo.insert(
        family_id,
        "parent_optout",
        payload={"reason": "parent used /stop"},
    )

    caregivers = await users_repo.list_caregivers(family_id)
    for c in caregivers:
        chat_id = c.get("telegram_chat_id")
        if chat_id:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"{escape(parent['display_name'])} asked Aunty May to stop. "
                        f"Reminders are paused. Use /resume in the group when ready."
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                log.exception("Failed to DM caregiver on /stop")

    await update.effective_chat.send_message(
        "OK Auntie — I'll stop messaging. Your family has been told. Take care. 🤍"
    )
