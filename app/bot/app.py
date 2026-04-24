"""Build the PTB Application with all handlers registered. FastAPI owns the lifecycle."""

from __future__ import annotations

from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.bot import group_post, handlers_parent, onboarding
from app.bot.digest import handle_digest
from app.config import settings

_app: Application | None = None


def build_application() -> Application:
    global _app
    if _app is not None:
        return _app

    app = ApplicationBuilder().token(settings.telegram_bot_token).build()

    # Commands
    app.add_handler(CommandHandler("start", onboarding.handle_start))
    app.add_handler(CommandHandler("setup", onboarding.handle_setup_stub))
    app.add_handler(CommandHandler("linkfamily", onboarding.handle_linkfamily))
    app.add_handler(CommandHandler("help", handlers_parent.handle_help))
    app.add_handler(CommandHandler("stop", handlers_parent.handle_stop))
    app.add_handler(CommandHandler("digest", handle_digest))

    # Parent voice (guarded further in the handler)
    app.add_handler(
        MessageHandler(filters.VOICE & filters.ChatType.PRIVATE, handlers_parent.handle_voice)
    )

    # Inline buttons (✓ Sent etc.)
    app.add_handler(CallbackQueryHandler(group_post.handle_sent_callback, pattern=r"^nudge_sent:"))

    # Free-text yes/no for parent handshake (must come after command handlers so /commands don't match)
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
            onboarding.handle_yes_no_confirmation,
        )
    )

    _app = app
    return app
