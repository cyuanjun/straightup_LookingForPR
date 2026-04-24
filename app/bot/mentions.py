"""Telegram HTML mention helper. Works for users with or without @username."""

from __future__ import annotations

from html import escape


def mention(display_name: str, telegram_user_id: int | None = None) -> str:
    """Return an HTML mention fragment.

    If telegram_user_id is known, emit a tg://user?id=... link (tappable mention,
    works without @username). Otherwise return plain escaped display_name.
    """
    safe_name = escape(display_name)
    if telegram_user_id:
        return f'<a href="tg://user?id={telegram_user_id}">{safe_name}</a>'
    return safe_name
