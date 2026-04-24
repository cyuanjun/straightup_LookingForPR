"""Parent handshake (/start <token>) + group linking (/linkfamily <setup_code>) + /setup stub.

Full conversational /setup wizard is deferred (see todo); for the spine smoke test
we only need /start + /linkfamily + a minimal /setup that issues a pending token.
"""

from __future__ import annotations

import logging
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.config import settings
from app.db import families as families_repo
from app.db import tokens as tokens_repo
from app.db import users as users_repo

log = logging.getLogger(__name__)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start or /start <token>. If a token is present, try the parent-handshake soft-claim."""
    if update.effective_user is None or update.effective_chat is None:
        return

    args = context.args or []
    if not args:
        await update.effective_chat.send_message(
            "Hi! I'm the AI care bot. A caregiver will share a setup link when they're ready."
        )
        # Populate telegram_chat_id if this user already exists as a caregiver
        await _touch_user_chat_id(
            update.effective_user.id, update.effective_chat.id, update.effective_user.username
        )
        return

    token = args[0]
    claim = await tokens_repo.atomic_claim_parent(token, update.effective_user.id)
    if claim is None:
        await update.effective_chat.send_message(
            "That link is invalid, already used, or expired. Ask the caregiver for a fresh one."
        )
        return

    # Stash the token in user_data so /yes or /no can finalize
    context.user_data["pending_parent_handshake"] = {
        "token": token,
        "family_id": claim["family_id"],
    }

    await update.effective_chat.send_message(
        "Hi! Are you Mdm Lim? Your family added me to help you with daily care. "
        "Reply <b>yes</b> or <b>no</b>.",
        parse_mode=ParseMode.HTML,
    )


async def handle_yes_no_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Free-text private-chat messages. Routes:
      - If a parent-handshake is pending → yes/no logic
      - Else if VOICE_DISABLED + sender is the linked parent → parent text pipeline
      - Else → ignore
    """
    if update.effective_user is None or update.effective_chat is None or update.message is None:
        return
    pending = context.user_data.get("pending_parent_handshake")
    if not pending:
        # Fall through to parent text pipeline (dev-mode text replies)
        from app.bot.handlers_parent import handle_text_from_parent

        await handle_text_from_parent(update, context)
        return

    reply = (update.message.text or "").strip().lower()
    if reply not in {"yes", "y", "no", "n", "是", "不是", "是的"}:
        return  # not a yes/no answer; ignore

    token = pending["token"]
    family_id = pending["family_id"]

    if reply in {"no", "n", "不是"}:
        await tokens_repo.release_parent(token)
        context.user_data.pop("pending_parent_handshake", None)
        await update.effective_chat.send_message(
            "No worries — let your family know and they'll send a new link if needed."
        )
        return

    # YES → finalize: upsert parent users row + set families.parent_user_id + consume token
    family = await families_repo.get(family_id)
    existing_parent_id = (family or {}).get("parent_user_id")

    parent_user = await users_repo.upsert_parent_from_handshake(
        family_id=family_id,
        existing_user_id=existing_parent_id,
        telegram_user_id=update.effective_user.id,
        telegram_chat_id=update.effective_chat.id,
        telegram_username=update.effective_user.username,
        display_name=update.effective_user.full_name or "Parent",
    )
    await families_repo.set_parent_user_id(family_id, parent_user["id"])
    await tokens_repo.confirm_parent(token)
    context.user_data.pop("pending_parent_handshake", None)

    await update.effective_chat.send_message(
        f"Thanks Auntie — I'm Aunty May, an AI. I'll check in on you gently. "
        f"I'll remind you about your medicine, and if you'd like, I can talk with you anytime. "
        f"Say /help if you want to know more."
    )

    # Post to family group
    if family and family.get("group_chat_id"):
        try:
            await context.bot.send_message(
                chat_id=family["group_chat_id"],
                text=f"✓ Setup complete. {escape(parent_user['display_name'])} acknowledged.",
            )
        except Exception:
            log.exception("Failed to post setup-complete to group")


async def handle_linkfamily(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/linkfamily <setup_code> in a family group — registers group_chat_id for the family."""
    chat = update.effective_chat
    if chat is None or chat.type not in ("group", "supergroup"):
        if chat:
            await chat.send_message("Run this command in your family's Telegram group.")
        return
    if update.effective_user is None:
        return

    args = context.args or []
    if not args:
        await chat.send_message("Usage: <code>/linkfamily 123456</code>", parse_mode=ParseMode.HTML)
        return

    setup_code = args[0].strip()
    row = await tokens_repo.find_active_group_linking(setup_code)
    if row is None:
        await chat.send_message(
            "That setup code is invalid, already used, or expired. Run /setup again in DM."
        )
        return

    # Authorization: the sender must be the caregiver who created this code
    created_by_user_id = row.get("created_by_user_id")
    creator = await users_repo.by_id(created_by_user_id) if created_by_user_id else None
    if (
        creator is None
        or creator.get("telegram_user_id") != update.effective_user.id
    ):
        await chat.send_message(
            "That setup code was created by a different caregiver. Please ask them to run /linkfamily here."
        )
        return

    family_id = row["family_id"]
    await families_repo.set_group_chat_id(family_id, chat.id)
    await tokens_repo.confirm_group_linking(setup_code)
    await chat.send_message("✓ Linked. I'll post updates here.")


async def handle_setup_stub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Minimal /setup — generates both a parent handshake token AND a group setup_code.

    Full conversational wizard is a later step. For the spine smoke test, /setup against
    a seeded demo family just issues fresh tokens the caregiver can use.
    """
    if update.effective_chat is None or update.effective_chat.type != "private":
        if update.effective_chat:
            await update.effective_chat.send_message("Run /setup in a DM with me, not in a group.")
        return
    if update.effective_user is None:
        return

    # Attach telegram_user_id to this caregiver (or use DEMO_FAMILY_ID fallback)
    demo_family_id = settings.demo_family_id
    if not demo_family_id:
        await update.effective_chat.send_message(
            "DEMO_FAMILY_ID is not set — full /setup wizard not yet implemented. "
            "For the demo, seed the family in Supabase first."
        )
        return

    # Look up the caregiver, or create/link one
    user = await users_repo.by_telegram_id(demo_family_id, update.effective_user.id)
    if user is None:
        # Match by name first; if still no match, create
        from app.db.client import get_client

        client = await get_client()
        resp = (
            await client.table("users")
            .select("*")
            .eq("family_id", demo_family_id)
            .eq("role", "caregiver")
            .is_("telegram_user_id", "null")
            .limit(1)
            .execute()
        )
        if resp.data:
            unlinked = resp.data[0]
            user = await users_repo.link_telegram(
                unlinked["id"],
                update.effective_user.id,
                update.effective_chat.id,
                update.effective_user.username,
                update.effective_user.full_name,
            )
        else:
            user = await users_repo.upsert_caregiver_from_telegram(
                demo_family_id,
                update.effective_user.id,
                update.effective_chat.id,
                update.effective_user.username,
                update.effective_user.full_name or "Caregiver",
            )

    # Ensure primary_caregiver_user_id is set
    family = await families_repo.get(demo_family_id)
    if family and not family.get("primary_caregiver_user_id"):
        await families_repo.set_primary_caregiver(demo_family_id, user["id"])

    # Issue fresh tokens
    parent_token = await tokens_repo.create_parent_handshake(demo_family_id, user["id"])
    _, setup_code = await tokens_repo.create_group_linking(demo_family_id, user["id"])

    parent_link = f"https://t.me/{settings.bot_username}?start={parent_token}"

    await update.effective_chat.send_message(
        "Setup (demo):\n\n"
        f"1. <b>Link this group</b> — add me to your family Telegram group, then run there:\n"
        f"   <code>/linkfamily {setup_code}</code>\n\n"
        f"2. <b>Parent handshake</b> — send this link to your parent (or tap it on their phone):\n"
        f"   {parent_link}\n\n"
        "Both expire in 24h.",
        parse_mode=ParseMode.HTML,
    )


async def _touch_user_chat_id(
    telegram_user_id: int, telegram_chat_id: int, username: str | None
) -> None:
    """When any user DMs us for the first time, link their telegram_chat_id if we can match them."""
    from app.db.client import get_client

    client = await get_client()
    resp = (
        await client.table("users")
        .update(
            {
                "telegram_chat_id": telegram_chat_id,
                "telegram_username": username,
            }
        )
        .eq("telegram_user_id", telegram_user_id)
        .is_("telegram_chat_id", "null")
        .execute()
    )
    _ = resp  # no-op if nothing matched
