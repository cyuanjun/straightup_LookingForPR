"""FastAPI app — owns the full PTB + APScheduler lifecycle.

Lifecycle (startup):
  application.initialize() → application.start() → scheduler.start() →
  register existing med cron jobs → set_webhook (idempotent)

Lifecycle (shutdown): reverse.

We deliberately do NOT use application.run_webhook() or run_polling() — FastAPI
owns the HTTP server; PTB is driven manually via application.process_update().
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Header, HTTPException, Request
from telegram import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, Update

from app.bot.app import build_application
from app.config import settings
from app.scheduler.jobs import register_all_family_crons, register_all_medication_jobs
from app.scheduler.scheduler import get_scheduler
from app.server.admin import router as admin_router

# Commands shown in Telegram's / autocomplete menu.
# All admin config (meds, rotation, pause, family settings) lives in the web dashboard.
# Telegram is for agent interaction + the few commands that only make sense there.
_PRIVATE_COMMANDS = [
    BotCommand("setup", "Generate parent handshake link + /linkfamily code"),
    BotCommand("digest", "Show the weekly coverage digest"),
    BotCommand("help", "What Aunty May does"),
    BotCommand("stop", "Stop receiving messages (parent)"),
]

# Group-chat menu: only what can't be done in the web UI (group_chat_id linking)
# plus consumption commands (digest).
_GROUP_COMMANDS = [
    BotCommand("linkfamily", "Link this group to your family (requires setup_code)"),
    BotCommand("digest", "Show the weekly coverage digest"),
]

log = logging.getLogger(__name__)
app = FastAPI(title="AI care bot")
app.include_router(admin_router)


@app.on_event("startup")
async def startup() -> None:
    tg_app = build_application()
    await tg_app.initialize()
    await tg_app.start()

    scheduler = get_scheduler()
    scheduler.start()
    tg_app.bot_data["scheduler"] = scheduler

    # Register persistent cron jobs for every active medication
    try:
        await register_all_medication_jobs()
    except Exception:
        log.exception("Failed to register medication jobs — continuing anyway")

    # Register per-family daily report (06:00) + weekly digest (Fri 18:00)
    try:
        await register_all_family_crons()
    except Exception:
        log.exception("Failed to register family cron jobs — continuing anyway")

    # Idempotent webhook registration
    try:
        await tg_app.bot.set_webhook(
            url=settings.webhook_url,
            secret_token=settings.webhook_secret_token,
            allowed_updates=Update.ALL_TYPES,
        )
        log.info("Webhook registered at %s", settings.webhook_url)
    except Exception:
        log.exception("set_webhook failed — continuing (may already be set)")

    # Register the / autocomplete menu (scoped separately for DMs vs groups)
    try:
        await tg_app.bot.set_my_commands(
            _PRIVATE_COMMANDS, scope=BotCommandScopeAllPrivateChats()
        )
        await tg_app.bot.set_my_commands(
            _GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats()
        )
        log.info("Registered Telegram /command menus (private + group scopes)")
    except Exception:
        log.exception("set_my_commands failed — continuing")


@app.on_event("shutdown")
async def shutdown() -> None:
    scheduler = get_scheduler()
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        log.exception("Scheduler shutdown errored")

    tg_app = build_application()
    try:
        await tg_app.stop()
        await tg_app.shutdown()
    except Exception:
        log.exception("PTB shutdown errored")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    # Validate the secret — rejects spoofed updates from anyone who learns the URL
    if x_telegram_bot_api_secret_token != settings.webhook_secret_token:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    tg_app = build_application()
    payload = await request.json()
    update = Update.de_json(payload, tg_app.bot)
    if update is None:
        return {"ok": True}
    await tg_app.process_update(update)
    return {"ok": True}
